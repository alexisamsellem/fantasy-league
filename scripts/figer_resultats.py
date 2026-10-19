#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fige les résultats réels d'une journée validée par FPL.

Les projections sont figées AVANT la deadline (`projections-figees/`). Pour que
le banc d'essai soit rejouable sans réseau, les résultats doivent l'être aussi,
APRÈS la validation officielle des points (`data_checked`). Un fichier par
journée, sous `resultats-observes/` :

    python3 scripts/figer_resultats.py            # toutes les GW validées manquantes
    python3 scripts/figer_resultats.py --gw 6     # une seule

Source : `GET /api/event/{gw}/live/` (points et minutes par joueur) et
`GET /api/fixtures/` (scores des matchs). Données publiques, aucune donnée
personnelle. Une journée non validée (`data_checked` faux) est refusée : des
points provisoires changeraient après coup, et le banc d'essai avec eux.
"""

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from fpl_advisor.api import get_json                              # noqa: E402


def _get(path):
    obj, err = get_json(path)
    if err:
        raise SystemExit(err)
    return obj

SORTIES = "resultats-observes"
# Ce que le banc d'essai lit. Le reste du live (ICT, BPS…) ne sert à rien ici.
CHAMPS = ("minutes", "total_points", "starts", "goals_scored", "assists",
          "clean_sheets", "goals_conceded", "saves", "bonus",
          "defensive_contribution", "yellow_cards", "red_cards")


def resultats(gw, live, fixtures, fetched_at):
    """Live + fixtures bruts → résultat compact d'une journée."""
    joueurs = {}
    for el in live.get("elements", []):
        st = el.get("stats") or {}
        joueurs[str(el["id"])] = {k: int(st.get(k) or 0) for k in CHAMPS}
    matchs = [{"id": f["id"], "team_h": f["team_h"], "team_a": f["team_a"],
               "team_h_score": f.get("team_h_score"),
               "team_a_score": f.get("team_a_score"),
               "kickoff_time": f.get("kickoff_time"),
               "finished": bool(f.get("finished"))}
              for f in fixtures if f.get("event") == gw]
    return {"gw": gw, "fetched_at": fetched_at,
            "source": f"GET /api/event/{gw}/live/ + GET /api/fixtures/",
            "players": joueurs, "fixtures": matchs}




def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gw", type=int)
    ap.add_argument("--sorties", default=SORTIES)
    args = ap.parse_args(argv)

    sorties = RACINE / args.sorties
    sorties.mkdir(parents=True, exist_ok=True)
    events = _get("/bootstrap-static/")["events"]
    valides = [e["id"] for e in events if e.get("data_checked")]
    cibles = [args.gw] if args.gw else valides
    fixtures = None
    for gw in cibles:
        cible = sorties / f"resultats-GW{gw}.json.gz"
        if gw not in valides:
            print(f"GW{gw} : points non validés par FPL (data_checked) — refusé")
            continue
        if cible.exists() and not args.gw:
            continue
        fixtures = fixtures if fixtures is not None else _get("/fixtures/")
        live = _get(f"/event/{gw}/live/")
        res = resultats(gw, live, fixtures,
                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        if not all(f["finished"] for f in res["fixtures"]):
            print(f"GW{gw} : un match n'est pas terminé — refusé")
            continue
        with gzip.open(cible, "wt", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"GW{gw} figée → {cible.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
