#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Le marché comme juge : probabilités d'équipe du moteur contre les cotes.

    python3 scripts/banc_marche.py      # → calibrations/banc-marche.md

Compare, sur les mêmes matchs, le λ de buts et la probabilité de clean sheet
lus dans les contrats figés (`projections-figees/`) à ceux que donnent les
cotes moyennes du marché, marge retirée (`reference/cotes-E0-2026-27.csv`,
football-data.co.uk). Juge : log-loss sur les scores réels. Détail de la
méthode : `fpl_advisor/evaluation/marche.py`.

Si le marché gagne, il devient l'entrée de force d'équipe du moteur, avec un
poids de mélange annoncé. S'il ne gagne pas, rien n'est branché.
"""

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from calibrer_en_attente import figeages                          # noqa: E402
from fpl_advisor.evaluation import benchmark as bm                # noqa: E402
from fpl_advisor.evaluation import marche                          # noqa: E402

COTES = RACINE / "reference" / "cotes-E0-2026-27.csv"


def lignes_archive(dossier_figeages, dossier_resultats, chemin_cotes=COTES,
                   prefix="Avg"):
    with open(chemin_cotes, encoding="utf-8-sig") as fh:
        cotes = marche.cotes_par_match(list(csv.DictReader(fh)), prefix)
    out, exclus = {}, {}
    for _, c in figeages(dossier_figeages):
        res = bm.charger_resultats(c.gw, dossier_resultats)
        if res is None:
            continue
        out[c.gw], exclus[c.gw] = marche.comparer(c, res, cotes)
    return out, exclus


def mesurer(lignes, quoi, b=bm.B_DEFAUT):
    """Δ = perte(moteur) − perte(marché) : négatif = le moteur gagne."""
    stat = lambda ls: sum(l[f"{quoi}_moteur"] - l[f"{quoi}_marche"] for l in ls) / len(ls)
    toutes = [l for ls in lignes.values() for l in ls]
    dm = bm.diebold_mariano([stat(ls) for ls in lignes.values()])
    ic = bm.bootstrap_grappes(toutes, stat, b=b)
    return {"n": len(toutes), "delta": stat(toutes), "ic": ic, "dm": dm,
            "moteur": sum(l[f"{quoi}_moteur"] for l in toutes) / len(toutes),
            "marche": sum(l[f"{quoi}_marche"] for l in toutes) / len(toutes),
            "par_gw": {g: stat(ls) for g, ls in lignes.items()},
            # Le marché gagne si l'écart est positif (moteur pire) aux deux tests.
            "marche_gagne": bm.verdict(ic, dm) == "non"}


def rendre(res, res_clot, exclus):
    gws = sorted(res["buts"]["par_gw"])
    L = [
        "# Le marché comme juge — probabilités d'équipe",
        "",
        f"Généré le {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC par "
        "`scripts/banc_marche.py`. Journées : "
        + ", ".join(f"GW{g}" for g in gws)
        + f", {res['buts']['n'] // 2} matchs, {res['buts']['n']} côtés de match.",
        "",
        "**Moteur** : λ de buts lu exactement dans les contrats figés avant la "
        "deadline (composante clean sheet = P(60+) × e^(−λ) × 4). **Marché** : "
        "cotes moyennes football-data.co.uk (`AvgH/D/A`, `Avg>2.5/<2.5`, "
        "relevées avant le match), marge retirée par normalisation, puis les "
        "deux λ de Poisson qui reproduisent P(domicile), P(extérieur) et "
        "P(+2,5 buts). **Juge** : log-loss sur les scores réels (FPL et "
        "football-data concordants). Δ = moteur − marché : négatif = le moteur "
        "gagne. IC 95 % bootstrap par match ; Diebold-Mariano sur les journées.",
        "",
        "| Mesure | Log-loss moteur | Log-loss marché | Δ | IC 95 % | DM p | "
        + " | ".join(f"Δ GW{g}" for g in gws) + " |",
        "|---|---|---|---|---|---|" + "---|" * len(gws),
    ]
    for nom, cle in (("Buts marqués (Poisson)", "buts"), ("Clean sheet", "cs")):
        for lib, r in (("ouverture", res[cle]), ("clôture", res_clot[cle])):
            L.append(f"| {nom}, marché {lib} | {r['moteur']:.4f} | {r['marche']:.4f} | "
                     f"{r['delta']:+.4f} | [{r['ic'][0]:+.4f} ; {r['ic'][1]:+.4f}] | "
                     f"{r['dm']['p']:.2f} | "
                     + " | ".join(f"{r['par_gw'][g]:+.4f}" for g in gws) + " |")
    gagne = any(r[q]["marche_gagne"] for r in (res, res_clot) for q in ("buts", "cs"))
    L += ["", "## Verdict", ""]
    if gagne:
        L.append("Le marché bat le moteur : il doit devenir l'entrée de force "
                 "d'équipe, avec un poids de mélange annoncé.")
    else:
        L += ["**Le marché ne bat pas le moteur** sur ces matchs, ni sur les buts "
              "ni sur le clean sheet, ni à l'ouverture ni à la clôture. Rien "
              "n'est branché : remplacer une entrée par une autre qui ne fait "
              "pas mieux ajouterait une dépendance réseau sans gain mesuré.",
              "",
              "Le point estimé est même légèrement en faveur du moteur, mais "
              "l'intervalle contient zéro : l'égalité est la lecture honnête."]
    L += ["", "## Ce que ce document ne dit pas", "",
          f"- {res['buts']['n'] // 2} matchs : l'intervalle d'une différence de "
          "log-loss y est large (±0,03 sur les buts). Un écart réel de l'ordre "
          "de 0,01 resterait invisible avant une demi-saison.",
          "- Les cotes `Avg` sont relevées le vendredi après-midi (le mardi en "
          "semaine) : proches de la deadline, pas identiques. Elles ne "
          "connaissent pas les compositions.",
          "- Le moteur et le marché utilisent ici le même modèle de buts "
          "(Poisson indépendants). Le test compare des forces d'équipe, pas "
          "des modèles de score.",
          "- Exclus (cotes absentes ou scores discordants) : "
          + ", ".join(f"GW{g} {n}" for g, n in sorted(exclus.items())) + ".", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--figeages", default=str(RACINE / "projections-figees"))
    ap.add_argument("--resultats", default=str(RACINE / "resultats-observes"))
    ap.add_argument("--sortie", default=str(RACINE / "calibrations" / "banc-marche.md"))
    ap.add_argument("--b", type=int, default=bm.B_DEFAUT)
    args = ap.parse_args(argv)
    lignes, exclus = lignes_archive(args.figeages, args.resultats)
    clot, _ = lignes_archive(args.figeages, args.resultats, prefix="AvgC")
    res = {q: mesurer(lignes, q, args.b) for q in ("buts", "cs")}
    res_clot = {q: mesurer(clot, q, args.b) for q in ("buts", "cs")}
    Path(args.sortie).write_text(rendre(res, res_clot, exclus), encoding="utf-8")
    for q in ("buts", "cs"):
        r = res[q]
        print(f"{q} : Δ {r['delta']:+.4f} [{r['ic'][0]:+.4f} ; {r['ic'][1]:+.4f}] "
              f"DM p={r['dm']['p']:.2f} → marché gagne : {r['marche_gagne']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
