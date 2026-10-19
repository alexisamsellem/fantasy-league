#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Le programme exact contre le scan historique, sur l'archive figée.

    python3 scripts/banc_optimiseur.py      # → calibrations/banc-optimiseur.md

Pour chaque contrat figé de `projections-figees/` et chaque effectif de test,
les deux optimiseurs reçoivent les MÊMES lignes (scénario central), le même
effectif, la même banque, le même nombre de transferts gratuits. Chacun rend
un plan ; les deux plans sont jugés par la même fonction
(`milp.evaluer` : meilleur XI + meilleur capitaine de chaque GW, moins les
hits, plus la valeur des gratuits restés en banque).

Le plan du scan : l'échange qu'il recommande à la GW de décision (ou aucun),
puis l'effectif figé sur l'horizon — c'est exactement ce qu'il propose.

Effectifs de test : tirés au hasard (graine fixe), légaux, à 100,0 M£ au
plus, parmi les joueurs à P(60+) > 40 %. Aucune donnée personnelle : les
effectifs réels d'un manager se passent avec --entry (sortie non versionnée).
"""

import argparse
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from calibrer_en_attente import figeages                          # noqa: E402
from fpl_advisor.optimization import milp                         # noqa: E402
from fpl_advisor.optimization import weekly as opt_weekly         # noqa: E402

N_EFFECTIFS = 8
GRAINE = 20261019
TOLERANCE = 1e-6


def effectif_aleatoire(rows, rng, budget=1000):
    by_id = {r["id"]: r for r in rows}
    while True:
        sq, clubs = [], {}
        for et, q in milp.QUOTAS.items():
            cand = [r for r in rows if r["element_type"] == et and r["p60"] > 0.4]
            rng.shuffle(cand)
            for r in cand:
                if sum(1 for p in sq if by_id[p]["element_type"] == et) == q:
                    break
                if clubs.get(r["team"], 0) < milp.PAR_CLUB:
                    sq.append(r["id"])
                    clubs[r["team"]] = clubs.get(r["team"], 0) + 1
        cout = sum(by_id[p]["now_cost"] for p in sq)
        if len(sq) == 15 and cout <= budget:
            return sq, budget - cout


def plan_du_scan(rows, squad, bank, gws, ft0):
    """Ce que propose le scan, sous la forme d'un plan évaluable."""
    d = opt_weekly.weekly_decision(rows, squad, bank, gws, optimiseur="scan")
    apres = list(squad)
    n = 0
    if d["swap"]:
        o, i = d["swap"]
        apres = [i if p == o else p for p in squad]
        n = 1
    effectifs = {g: apres for g in gws}
    hits = {gws[0]: max(0, n - ft0)}
    f = milp.ft_suivant(ft0, n)
    for _ in gws[1:]:
        f = milp.ft_suivant(f, 0)
    return effectifs, hits, f, d["swap"]


def comparer(contract, squad, bank, ft0, ft_value):
    rows = contract.rows_for("central")
    by_id = {r["id"]: r for r in rows}
    gws = list(contract.horizon)
    eff, hits, f, swap = plan_du_scan(rows, squad, bank, gws, ft0)
    v_scan, vb_scan = milp.evaluer(by_id, eff, gws, hits, f, ft_value)
    pl = milp.plan_transferts(rows, squad, bank, gws, free_transfers=ft0,
                              ft_value=ft_value)
    return {"gw": contract.gw, "ft0": ft0, "ft_value": ft_value,
            "scan": vb_scan, "milp": pl["valeur_banque"],
            "scan_sans_banque": v_scan, "milp_sans_banque": pl["valeur"],
            "ecart": pl["valeur_banque"] - vb_scan, "swap_scan": swap,
            "transferts_milp": {g: len(pl["achats"][g]) for g in gws},
            "hits_milp": sum(pl["hits"].values())}


def archive(dossier, n_effectifs=N_EFFECTIFS, graine=GRAINE, gws=None,
            ft_values=(0.0, milp.FT_VALUE)):
    out = []
    for _, c in figeages(dossier):
        if gws and c.gw not in gws:
            continue
        rows = c.rows_for("central")
        rng = random.Random(graine + c.gw)
        for k in range(n_effectifs):
            sq, bank = effectif_aleatoire(rows, rng)
            ft0 = 1 + k % 2
            for fv in ft_values:
                out.append(dict(comparer(c, sq, bank, ft0, fv), effectif=k))
    return out


def rendre(res):
    n = len(res)
    pire = min(r["ecart"] for r in res)
    lignes = [
        "# Programme exact contre scan historique — archive figée",
        "",
        f"Généré le {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC par "
        f"`scripts/banc_optimiseur.py`. {n} comparaisons : contrats figés "
        + ", ".join(f"GW{g}" for g in sorted({r['gw'] for r in res}))
        + f" × {N_EFFECTIFS} effectifs aléatoires (graine {GRAINE}) × deux "
        "valeurs du gratuit en banque (0 et "
        f"{milp.FT_VALUE:g} pt). Gratuits disponibles : 1 ou 2 en alternance.",
        "",
        "**Juge commun** : `milp.evaluer` — Σ par GW du meilleur XI et du "
        "meilleur capitaine, − 4 par hit, + valeur des gratuits restés en "
        "banque. Les deux plans sont recalculés par cette fonction, pas lus "
        "dans leur optimiseur.",
        "",
        "## Verdict",
        "",
        f"- Écart minimal (programme − scan) : **{pire:+.4f} pt** "
        + ("→ le programme n'a JAMAIS fait moins bien." if pire >= -TOLERANCE
           else "→ ÉCHEC : le programme a fait moins bien au moins une fois."),
        f"- Écart moyen : {sum(r['ecart'] for r in res) / n:+.2f} pt ; "
        f"strictement meilleur dans {sum(1 for r in res if r['ecart'] > 1e-6)}/{n} cas.",
        f"- Hits pris par le programme : {sum(r['hits_milp'] for r in res)} au total.",
        "",
        "| GW | Effectif | Gratuits | Valeur banque | Scan | Programme | Écart | "
        "Transferts du programme par GW |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in res:
        tr = " / ".join(str(v) for v in r["transferts_milp"].values())
        lignes.append(f"| {r['gw']} | {r['effectif']} | {r['ft0']} | {r['ft_value']:g} | "
                      f"{r['scan']:.2f} | {r['milp']:.2f} | {r['ecart']:+.2f} | {tr} |")
    lignes += [
        "",
        "## Ce que ce document ne prouve pas",
        "",
        "- « Jamais moins bien » porte sur l'objectif en points ESPÉRÉS. C'est "
        "une garantie de construction (le plan du scan est admissible pour le "
        "programme), vérifiée ici. Sur les points RÉELS, un meilleur plan "
        "espéré peut perdre une semaine donnée.",
        "- Effectifs aléatoires : souvent loin de l'optimum, ils exagèrent "
        "l'écart par rapport à un effectif réel déjà bien construit.",
        f"- La valeur d'un gratuit en banque ({milp.FT_VALUE:g} pt) est un "
        "[H], repris du seuil de bascule du scan ; elle n'est pas mesurée.",
        "",
    ]
    return "\n".join(lignes)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--figeages", default=str(RACINE / "projections-figees"))
    ap.add_argument("--sortie", default=str(RACINE / "calibrations" / "banc-optimiseur.md"))
    ap.add_argument("--n", type=int, default=N_EFFECTIFS)
    args = ap.parse_args(argv)
    if not milp.disponible():
        raise SystemExit("PuLP + HiGHS absents : pip install pulp highspy")
    res = archive(args.figeages, args.n)
    Path(args.sortie).write_text(rendre(res), encoding="utf-8")
    pire = min(r["ecart"] for r in res)
    print(f"{len(res)} comparaisons, écart minimal {pire:+.4f} pt — {args.sortie}")
    return 0 if pire >= -TOLERANCE else 1


if __name__ == "__main__":
    sys.exit(main())
