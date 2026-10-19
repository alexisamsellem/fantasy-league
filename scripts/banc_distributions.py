#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Distributions simulées contre espérance seule et trois scénarios (CRPS).

    python3 scripts/banc_distributions.py    # → calibrations/banc-distributions.md

Chaque contrat figé (version 1.0) est migré EN MÉMOIRE vers 1.1 : le
calendrier de la journée (connu avant la deadline) vient de
`resultats-observes/`, les λ se relisent dans les composantes figées, et les
distributions sont simulées sans rien recalculer du moteur. Le fichier figé
n'est jamais réécrit.

Trois prévisions, notées par CRPS sur les points réels :
  - espérance seule : un point, CRPS = erreur absolue ;
  - trois scénarios : prudent, central, favorable, à poids égaux ;
  - distribution simulée : 1 000 tirages, buts d'équipe partagés.
Et un test de la corrélation : sur la somme des 11 meilleurs EP de chaque
équipe, buts partagés contre buts tirés indépendamment par joueur.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from calibrer_en_attente import figeages                          # noqa: E402
from fpl_advisor.evaluation import benchmark as bm                # noqa: E402
from fpl_advisor.forecasting import distribution as dsim          # noqa: E402
from fpl_advisor.forecasting.contract import migrate_1_0          # noqa: E402

TAILLE_GROUPE = 11


def lignes_archive(dossier_figeages, dossier_resultats, n=dsim.N_TIRAGES):
    joueurs, equipes = {}, {}
    for _, c in figeages(dossier_figeages):
        res = bm.charger_resultats(c.gw, dossier_resultats)
        if res is None:
            continue
        g = c.gw
        migrate_1_0(c, {g: [(f["team_h"], f["team_a"]) for f in res["fixtures"]]}, n=n)
        tir = c.simulate(g, n=n)
        tir_ind = c.simulate(g, n=n, partage=False)
        obs = res["players"]
        rows = [r for r in c.rows if r.gw == g and r.n_fixtures
                and str(r.player_id) in obs]
        joueurs[g] = []
        for r in rows:
            y = obs[str(r.player_id)]["total_points"]
            joueurs[g].append({
                "gw": g, "team": c.players[str(r.player_id)]["team"], "y": y,
                "sim": dsim.crps(tir[r.player_id], y),
                "scenarios": dsim.crps(list(r.scenarios.values()), y),
                "point": abs(r.ep - y)})
        par_eq = {}
        for r in rows:
            par_eq.setdefault(c.players[str(r.player_id)]["team"], []).append(r)
        equipes[g] = []
        for t, rs in par_eq.items():
            top = sorted(rs, key=lambda r: -r.ep)[:TAILLE_GROUPE]
            y = sum(obs[str(r.player_id)]["total_points"] for r in top)
            somme = lambda tt: [sum(tt[r.player_id][k] for r in top) for k in range(n)]
            equipes[g].append({
                "gw": g, "team": t, "y": y,
                "sim": dsim.crps(somme(tir), y),
                "independant": dsim.crps(somme(tir_ind), y),
                "scenarios": dsim.crps([sum(r.scenarios[s] for r in top)
                                        for s in c.scenario_names], y),
                "point": abs(sum(r.ep for r in top) - y)})
    return joueurs, equipes


def comparer(lignes, a, b, nb=bm.B_DEFAUT):
    stat = lambda ls: sum(l[a] - l[b] for l in ls) / len(ls)
    toutes = [l for ls in lignes.values() for l in ls]
    ic = bm.bootstrap_grappes(toutes, stat, b=nb)
    dm = bm.diebold_mariano([stat(ls) for ls in lignes.values()])
    return {"a": sum(l[a] for l in toutes) / len(toutes),
            "b": sum(l[b] for l in toutes) / len(toutes),
            "delta": stat(toutes), "ic": ic, "dm": dm,
            "par_gw": {g: stat(ls) for g, ls in lignes.items()},
            "verdict": bm.verdict(ic, dm), "n": len(toutes)}


def _ligne(nom, r, gws):
    return (f"| {nom} | {r['n']} | {r['a']:.3f} | {r['b']:.3f} | {r['delta']:+.3f} | "
            f"[{r['ic'][0]:+.3f} ; {r['ic'][1]:+.3f}] | {r['dm']['p']:.3f} | "
            f"**{r['verdict']}** | " + " | ".join(f"{r['par_gw'][g]:+.3f}" for g in gws) + " |")


def rendre(res, gws, n):
    entete = ("| Comparaison | n | CRPS simulé | CRPS référence | Δ | IC 95 % | DM p | "
              "Le simulé gagne ? | " + " | ".join(f"Δ GW{g}" for g in gws) + " |")
    sep = "|---|---|---|---|---|---|---|---|" + "---|" * len(gws)
    return "\n".join([
        "# Distributions simulées — CRPS sur les journées figées",
        "",
        f"Généré le {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC par "
        f"`scripts/banc_distributions.py` ({n} tirages par journée). Journées : "
        + ", ".join(f"GW{g}" for g in gws) + ".",
        "",
        "**CRPS** (continuous ranked probability score) : E|X − y| − ½ E|X − X'|, "
        "où X est tiré de la prévision et y le résultat. Plus bas est meilleur. "
        "Il récompense une distribution à la fois centrée et de la bonne "
        "largeur ; pour une prévision ponctuelle, il vaut l'erreur absolue — "
        "c'est ce qui rend les trois prévisions comparables sur la même échelle.",
        "",
        "Δ = CRPS(simulé) − CRPS(référence) : négatif = la distribution gagne. "
        "IC 95 % bootstrap apparié par grappes (GW, équipe) ; Diebold-Mariano "
        "sur les journées ; « oui » seulement si les deux concluent.",
        "",
        "## Par joueur",
        "",
        entete, sep,
        _ligne("simulé vs trois scénarios", res["j_sc"], gws),
        _ligne("simulé vs espérance seule", res["j_pt"], gws),
        "",
        f"## Par équipe — somme des {TAILLE_GROUPE} meilleurs EP",
        "",
        "C'est ici que l'aléa partagé se juge : sur un joueur seul, buts "
        "partagés ou non donnent la même loi ; sur une somme, la corrélation "
        "élargit la distribution.",
        "",
        entete, sep,
        _ligne("simulé vs trois scénarios", res["e_sc"], gws),
        _ligne("simulé vs espérance seule", res["e_pt"], gws),
        _ligne("buts partagés vs indépendants", res["e_ind"], gws),
        "",
        "## Ce que ce document ne dit pas",
        "",
        "- Les trois scénarios sont trois jeux de priors, pas trois issues de "
        "match : les battre en CRPS est attendu. L'espérance seule est la "
        "référence la plus dure ici, parce qu'elle porte toute l'information "
        "du moteur.",
        "- L'apport de l'aléa partagé n'est mesuré que sur des sommes par "
        "équipe ; 20 équipes × 5 journées, c'est 100 observations.",
        "- La simulation hérite des P(60+) figés (modèle 0.3.1, avant la "
        "recalibration A10) : elle juge la forme de la loi, pas la "
        "recalibration.",
        "",
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--figeages", default=str(RACINE / "projections-figees"))
    ap.add_argument("--resultats", default=str(RACINE / "resultats-observes"))
    ap.add_argument("--sortie", default=str(RACINE / "calibrations" / "banc-distributions.md"))
    ap.add_argument("--n", type=int, default=dsim.N_TIRAGES)
    ap.add_argument("--b", type=int, default=bm.B_DEFAUT)
    args = ap.parse_args(argv)
    j, e = lignes_archive(args.figeages, args.resultats, args.n)
    res = {"j_sc": comparer(j, "sim", "scenarios", args.b),
           "j_pt": comparer(j, "sim", "point", args.b),
           "e_sc": comparer(e, "sim", "scenarios", args.b),
           "e_pt": comparer(e, "sim", "point", args.b),
           "e_ind": comparer(e, "sim", "independant", args.b)}
    Path(args.sortie).write_text(rendre(res, sorted(j), args.n), encoding="utf-8")
    for k, r in res.items():
        print(f"{k} : Δ {r['delta']:+.3f} [{r['ic'][0]:+.3f} ; {r['ic'][1]:+.3f}] "
              f"DM p={r['dm']['p']:.3f} → {r['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
