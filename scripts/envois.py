#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Portier des envois : faut-il écrire au manager pendant CE passage ?

Le workflow passe toutes les heures ; ce script décide, en UNE requête
publique, s'il y a quelque chose à faire. Sinon le job s'arrête là.

    python3 scripts/envois.py planifier [--forcer]
    python3 scripts/envois.py noter --gw 7 --moment principal --envoye true \
        --decision data/reports/GW7-decision.json

`planifier` écrit sur la sortie standard, et dans $GITHUB_OUTPUT :

    conseil=principal|rappel|rien
    gw=7  heures=7  deadline=2026-10-17T17:30:00Z
    bilan_gw=6          # vide s'il n'y a pas de journée à analyser
    agir=true           # conseil != rien ou bilan_gw non vide
    force=false

L'API FPL injoignable n'est PAS une erreur : le passage suivant réessaiera
dans une heure. Échouer ici déclencherait un mail d'échec GitHub par heure —
exactement le bruit que ce portier existe pour supprimer.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import envois                     # noqa: E402
from fpl_advisor.api import get_json               # noqa: E402


def _paris(ts):
    if not ts:
        return "?"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(envois.PARIS).strftime("%a %d/%m %H:%M")


def planifier(args):
    boot, err = get_json("/bootstrap-static/")
    if boot is None:
        print(f"::warning::Calendrier FPL illisible ({err}) — rien à faire, "
              "nouvel essai au prochain passage.")
        envois.sortie(conseil="rien", gw="", heures="", deadline="",
                      bilan_gw="", agir="false", force="false")
        return 0
    journal = envois.charger(args.journal)
    plan = envois.planifier(boot.get("events"), journal,
                            datetime.now(timezone.utc), forcer=args.forcer)
    if plan["gw"] is not None:
        print(f"GW{plan['gw']} : deadline {_paris(plan['deadline'])} (Paris), "
              f"mail principal à {_paris(plan['principal_a'])}, rappel à "
              f"{_paris(plan['rappel_a'])}.")
    print(f"Conseil : {plan['conseil']} — {plan['raison']}.")
    print(f"Bilan : {'GW' + str(plan['bilan_gw']) if plan['bilan_gw'] else 'rien à analyser'}.")
    agir = plan["conseil"] != "rien" or plan["bilan_gw"] is not None
    envois.sortie(
        conseil=plan["conseil"], gw=plan["gw"],
        heures="" if plan["heures"] is None else f"{plan['heures']:.0f}",
        deadline=plan["deadline"], bilan_gw=plan["bilan_gw"],
        agir="true" if agir else "false",
        force="true" if plan["force"] else "false")
    return 0


def noter(args):
    journal = envois.charger(args.journal)
    dec = None
    if args.decision and Path(args.decision).exists():
        dec = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    envoye = args.envoye.lower() == "true"
    envois.noter(journal, args.gw, args.moment, envoye, dec)
    envois.sauver(journal, args.journal)
    print(f"Journal : GW{args.gw} {args.moment} "
          f"{'envoyé' if envoye else 'vérifié, rien à envoyer'}.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=envois.JOURNAL)
    sous = ap.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("planifier")
    p.add_argument("--forcer", action="store_true",
                   help="envoie le conseil de la prochaine deadline maintenant")
    n = sous.add_parser("noter")
    n.add_argument("--gw", type=int, required=True)
    n.add_argument("--moment", choices=["principal", "rappel", "bilan"],
                   required=True)
    n.add_argument("--envoye", default="true")
    n.add_argument("--decision", help="décision écrite par `advise --moment`")
    args = ap.parse_args(argv)
    return planifier(args) if args.commande == "planifier" else noter(args)


if __name__ == "__main__":
    sys.exit(main())
