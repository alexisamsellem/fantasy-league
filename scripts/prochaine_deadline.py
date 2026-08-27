#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Combien d'heures avant la prochaine deadline FPL ? Un seul GET public.

Sert de portier au conseiller automatique : une collecte complète coûte ~616
requêtes et quelques minutes. Les lancer tous les jours de la semaine pour une
deadline située à cinq jours ne sert à rien, et remplit une boîte mail.

    python3 scripts/prochaine_deadline.py --seuil 60

Écrit sur la sortie standard, et dans $GITHUB_OUTPUT quand la variable existe :

    gw=2
    heures=25
    agir=true        # heures <= seuil

Code de sortie 0 dans tous les cas où la question a une réponse ; 1 si le
calendrier est illisible. « Pas de deadline à venir » (saison finie) est une
réponse, pas une erreur : `agir=false`.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor.api import get_json           # noqa: E402


def prochaine(events, maintenant):
    """(gw, deadline, heures) de la première GW dont la deadline est future."""
    futures = []
    for e in events or []:
        ts = e.get("deadline_time")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > maintenant:
            futures.append((dt, e.get("id")))
    if not futures:
        return None, None, None
    dt, gw = min(futures)
    return gw, dt, (dt - maintenant).total_seconds() / 3600.0


def _sortie(**kv):
    for k, v in kv.items():
        print(f"{k}={v}")
    chemin = os.environ.get("GITHUB_OUTPUT")
    if chemin:
        with open(chemin, "a", encoding="utf-8") as fh:
            for k, v in kv.items():
                fh.write(f"{k}={v}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seuil", type=float, default=60.0,
                    help="heures en dessous desquelles il faut agir (défaut 60)")
    args = ap.parse_args(argv)

    boot, err = get_json("/bootstrap-static/")
    if boot is None:
        raise SystemExit(f"Calendrier illisible : {err}")
    gw, dt, heures = prochaine(boot.get("events"), datetime.now(timezone.utc))
    if gw is None:
        _sortie(gw="", heures="", agir="false")
        print("Aucune deadline à venir : saison terminée ou calendrier vide.")
        return 0
    _sortie(gw=gw, heures=f"{heures:.0f}", deadline=dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            agir="true" if heures <= args.seuil else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
