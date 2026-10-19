#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Banc d'essai sur les POINTS : `ep` du moteur contre `ep_next` de FPL.

    python3 scripts/figer_resultats.py     # fige les journées validées
    python3 scripts/banc_points.py         # → calibrations/banc-points.md

Ne lit que `projections-figees/` (le dernier figeage avant chaque deadline,
comme `calibrer_en_attente.py`) et `resultats-observes/`. Aucun réseau, aucune
projection recalculée. Détail de la méthode : `fpl_advisor/evaluation/benchmark.py`.
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


def lignes_archive(dossier_figeages, dossier_resultats):
    """{gw: lignes} pour chaque journée figée ET jouée, plus les métadonnées."""
    lignes, meta = {}, {}
    for chemin, c in figeages(dossier_figeages):
        res = bm.charger_resultats(c.gw, dossier_resultats)
        if res is None:
            continue
        lignes[c.gw], exclus = bm.paires_points(c, res)
        meta[c.gw] = {"fichier": chemin.name, "as_of": c.as_of,
                      "deadline": c.deadline, "model": c.model_version,
                      "fetched_at": res["fetched_at"], "exclus": exclus}
    return lignes, meta


def _f(x, n=3):
    return "—" if x is None else f"{x:+.{n}f}" if n and x < 0 else f"{x:.{n}f}"


def _ic(ic):
    return f"[{ic[0]:+.3f} ; {ic[1]:+.3f}]"


def _table(res):
    out = ["| GW | Joueurs | MSE moteur | MSE ep_next | Δ MSE | IC 95 % Δ | "
           "MAE moteur | MAE ep_next | Biais moteur | Biais ep_next |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for g, r in res["par_gw"].items():
        out.append(f"| {g} | {r['n']} | {r['mse_ep']:.3f} | {r['mse_ep_next']:.3f} | "
                   f"{r['mse_ep'] - r['mse_ep_next']:+.3f} | {_ic(r['ic_dmse'])} | "
                   f"{r['mae_ep']:.3f} | {r['mae_ep_next']:.3f} | "
                   f"{r['biais_ep']:+.2f} | {r['biais_ep_next']:+.2f} |")
    gl = res["global"]
    out.append(f"| **toutes** | {gl['n']} | {gl['mse_ep']:.3f} | {gl['mse_ep_next']:.3f} | "
               f"**{gl['dmse']:+.3f}** | **{_ic(gl['ic_dmse'])}** | "
               f"{gl['mae_ep']:.3f} | {gl['mae_ep_next']:.3f} | "
               f"{gl['biais_ep']:+.2f} | {gl['biais_ep_next']:+.2f} |")
    return out


def _bloc_verdict(gl):
    dm, dma = gl["dm_mse"], gl["dm_mae"]
    return [
        f"- **Erreur quadratique** : Δ = {gl['dmse']:+.3f}, IC 95 % bootstrap par "
        f"grappes {_ic(gl['ic_dmse'])} ; Diebold-Mariano t = {dm['t']:+.2f} "
        f"({dm['ddl']} ddl), p = {dm['p']:.3f} → **{gl['verdict_mse']}**",
        f"- **Erreur absolue** : Δ = {gl['dmae']:+.3f}, IC 95 % {_ic(gl['ic_dmae'])} ; "
        f"DM t = {dma['t']:+.2f}, p = {dma['p']:.3f} → **{gl['verdict_mae']}**",
    ]


def rendre(tous, pert, meta, b):
    gws = sorted(meta)
    lignes = [
        "# Banc d'essai sur les points — moteur contre `ep_next`",
        "",
        f"Généré le {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC par "
        "`scripts/banc_points.py`. Journées notées : "
        + ", ".join(f"GW{g}" for g in gws) + ".",
        "",
        "**Ce qui est comparé.** Pour chaque journée, le dernier contrat figé "
        "AVANT la deadline porte deux prévisions de la même date : `ep` (le "
        "moteur, scénario central) et `ep_next` (FPL, stocké dans le même "
        "fichier). Les deux sont confrontées aux points FPL réels "
        "(`total_points` du live, journée validée `data_checked`).",
        "",
        "**Comment l'incertitude est mesurée.** Δ = perte(moteur) − "
        "perte(ep_next) : négatif = le moteur se trompe moins. IC 95 % par "
        f"bootstrap apparié ({b} répliques) qui rééchantillonne des couples "
        "(GW, équipe), parce que les joueurs d'un même match ne sont pas "
        "indépendants. Contre-épreuve : Diebold-Mariano sur la série des écarts "
        "par journée (Student, n−1 ddl). Verdict « oui » seulement si les deux "
        "concluent au seuil de 5 %.",
        "",
        "## Verdict — tous les joueurs ayant un match",
        "",
        *_bloc_verdict(tous["global"]),
        "",
        *_table(tous),
        "",
        f"## Joueurs envisageables (max(ep, ep_next) ≥ {bm.SEUIL_PERTINENT:g})",
        "",
        "Sous-population définie sur les prévisions, jamais sur le résultat : "
        "elle retire la masse des joueurs que personne n'alignerait et que les "
        "deux prévisions donnent à ~0.",
        "",
        *_bloc_verdict(pert["global"]),
        "",
        *_table(pert),
        "",
        "## Traçabilité",
        "",
        "| GW | Contrat | Figé le | Deadline | Modèle | Résultats lus le | Exclus |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in gws:
        m = meta[g]
        ex = ", ".join(f"{k} {v}" for k, v in m["exclus"].items())
        lignes.append(f"| {g} | `{m['fichier']}` | {m['as_of']} | {m['deadline']} | "
                      f"{m['model']} | {m['fetched_at']} | {ex} |")
    lignes += [
        "",
        "## Ce que ce document ne dit pas",
        "",
        f"- {len(gws)} journées seulement : Diebold-Mariano n'a que "
        f"{len(gws) - 1} degrés de liberté. Le bootstrap par grappes est plus "
        "puissant mais suppose les équipes indépendantes entre elles au sein "
        "d'une journée, ce qui est faux pour les deux équipes d'un même match.",
        "- `ep_next` est un repère grossier (forme récente). Le battre est le "
        "minimum, pas une preuve de qualité absolue.",
        "- L'erreur moyenne sur ~550 joueurs ne mesure pas directement la "
        "qualité des DÉCISIONS (capitaine, transfert), qui se jouent sur une "
        "dizaine de joueurs en haut du classement.",
        "",
    ]
    return "\n".join(lignes)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--figeages", default=str(RACINE / "projections-figees"))
    ap.add_argument("--resultats", default=str(RACINE / "resultats-observes"))
    ap.add_argument("--sortie", default=str(RACINE / "calibrations" / "banc-points.md"))
    ap.add_argument("--b", type=int, default=bm.B_DEFAUT)
    args = ap.parse_args(argv)

    lignes, meta = lignes_archive(args.figeages, args.resultats)
    if not lignes:
        print("Aucune journée figée et jouée — rien à noter.")
        return 0
    tous = bm.evaluer(lignes, b=args.b)
    pert = bm.evaluer(lignes, b=args.b, filtre=bm.pertinent)
    Path(args.sortie).write_text(rendre(tous, pert, meta, args.b), encoding="utf-8")
    gl = tous["global"]
    print(f"Δ MSE {gl['dmse']:+.3f} {_ic(gl['ic_dmse'])} DM p={gl['dm_mse']['p']:.3f} "
          f"→ {gl['verdict_mse']} — {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
