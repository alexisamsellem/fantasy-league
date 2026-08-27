#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Note toutes les journées figées qui ont été jouées et pas encore notées.

Le conseiller fige ses projections AVANT chaque deadline, sous
`projections-figees/`. Une fois la journée jouée, ces prédictions peuvent être
confrontées aux minutes réellement passées sur le terrain. C'est la seule
mesure qui dit si le moteur vaut quelque chose ; tout le reste dit seulement
qu'il tourne.

    python3 scripts/calibrer_en_attente.py

Le script est idempotent : une journée déjà notée n'est pas re-notée. Il ne
note jamais une journée non jouée — `observed_minutes` rend {} tant que le
fichier live n'a que des zéros, et la calibration refuse alors de conclure.

Les rapports partent sous `calibrations/`, versionné : ils ne contiennent
aucune donnée personnelle, et leur intérêt est justement de s'accumuler.
"""

import argparse
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from fpl_advisor.collect import observed_minutes                  # noqa: E402
from fpl_advisor.evaluation import calibration                    # noqa: E402
from fpl_advisor.forecasting import ProjectionSet                 # noqa: E402
from fpl_advisor.report import write_calibration                  # noqa: E402

FIGEAGES = "projections-figees"
SORTIES = "calibrations"


def figeages(dossier):
    """Contrats figés, du plus ancien au plus récent, un seul par GW.

    Plusieurs figeages d'une même journée peuvent coexister (un témoin du
    mercredi, l'officiel du vendredi). Le DERNIER connu avant la deadline est
    celui qui compte : c'est celui qui portait le plus d'information."""
    par_gw = {}
    for p in sorted(Path(dossier).glob("projections-*.json*")):
        if p.suffix not in (".json", ".gz"):
            continue
        try:
            c = ProjectionSet.load(p)
        except (ValueError, OSError, KeyError) as e:
            print(f"  {p.name} : illisible ({e}) — ignoré")
            continue
        garde = par_gw.get(c.gw)
        if garde is None or str(c.as_of) > str(garde[1].as_of):
            par_gw[c.gw] = (p, c)
    return [par_gw[g] for g in sorted(par_gw)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--figeages", default=FIGEAGES)
    ap.add_argument("--sorties", default=SORTIES)
    ap.add_argument("--refaire", action="store_true",
                    help="re-note même les journées déjà notées")
    args = ap.parse_args(argv)

    sorties = RACINE / args.sorties
    sorties.mkdir(parents=True, exist_ok=True)
    trouves = figeages(args.figeages)
    if not trouves:
        print(f"Aucun contrat figé sous {args.figeages}/ — rien à noter.")
        return 0

    notes = 0
    for chemin, contrat in trouves:
        cible = sorties / f"GW{contrat.gw}-calibration.md"
        if cible.exists() and not args.refaire:
            print(f"GW{contrat.gw} : déjà notée ({cible.name}).")
            continue
        mins = observed_minutes(args.data_dir, contrat.gw)
        if not mins:
            print(f"GW{contrat.gw} : pas encore jouée, ou snapshot sans "
                  f"`event-{contrat.gw}-live` rempli — non notée.")
            continue
        res = calibration.assess(contrat, mins, contrat.gw)
        provisoire = write_calibration(res, args.data_dir)
        shutil.copyfile(provisoire, cible)
        notes += 1
        print(f"\nGW{contrat.gw} — figée le {contrat.as_of} ({chemin.name})")
        for m in res["metriques"].values():
            if m["competence"] is None:
                print(f"  {m['label']} : non calculable ({m['n']} joueurs)")
            else:
                print(f"  {m['label']} : Brier {m['brier']:.4f} "
                      f"(référence {m['brier_reference']:.4f}) — "
                      f"compétence {m['competence']:+.3f} sur {m['n']} joueurs")
        print(f"  {res['conclusion']}")
        print(f"  Rapport : {cible}")

    print(f"\n{notes} journée(s) notée(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
