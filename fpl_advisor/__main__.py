# -*- coding: utf-8 -*-
"""CLI du conseiller FPL V0.

  python3 -m fpl_advisor collect        # collecte + snapshot immuable + DuckDB
  python3 -m fpl_advisor advise         # recommandation depuis le dernier snapshot
  python3 -m fpl_advisor run            # collect puis advise (rituel de deadline)
  python3 -m fpl_advisor demo           # bout-en-bout sur données synthétiques
  python3 -m fpl_advisor initial-squad  # effectif initial 15 joueurs (sans config)
"""

import argparse
import sys

from .advise import build_recommendation
from .api import load_config
from .collect import (collect_all, collect_public, latest_snapshot_dir,
                      load_duckdb, load_public_snapshot, load_snapshot)
from .initial import build_initial_recommendation
from .report import write_initial_report, write_report


def _advise(parsed, data_dir):
    rec = build_recommendation(parsed)
    path = write_report(rec, data_dir)
    band = rec["armband"]
    print(f"Rapport : {path}")
    print(f"GW{rec['gw']} — capitaine {band['captain']['web_name']}, "
          f"vice {band['vice']['web_name']} ; transfert : {rec['transfer']['decision']}")
    return 0


def _initial(parsed, data_dir):
    rec = build_initial_recommendation(parsed)
    path = write_initial_report(rec, data_dir)
    band = rec["armband"]
    print(f"Rapport : {path}")
    print(f"GW{rec['gw']} — effectif initial : {rec['cost'] / 10:.1f} M£ utilisés "
          f"(banque {rec['bank'] / 10:.1f} M£) ; capitaine {band['captain']['web_name']}, "
          f"vice {band['vice']['web_name']}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fpl_advisor")
    ap.add_argument("command",
                    choices=["collect", "advise", "run", "demo", "initial-squad"])
    ap.add_argument("--config", default="config.local.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--demo", action="store_true",
                    help="initial-squad : jeu synthétique hors ligne, aucun réseau")
    args = ap.parse_args(argv)

    if args.command == "demo":
        from .demo import build_parsed
        return _advise(build_parsed(), args.data_dir)

    if args.command == "initial-squad":
        if args.demo:
            from .demo import build_parsed_initial
            return _initial(build_parsed_initial(), args.data_dir)
        run_dir = collect_public(args.data_dir)
        print(f"Snapshot : {run_dir}")
        return _initial(load_public_snapshot(run_dir), args.data_dir)

    cfg = load_config(args.config)
    if args.command in ("collect", "run"):
        run_dir = collect_all(cfg, args.data_dir)
        print(f"Snapshot : {run_dir}")
        parsed = load_snapshot(run_dir, cfg)
        print(load_duckdb(parsed, f"{args.data_dir}/fpl.duckdb"))
        if args.command == "collect":
            return 0
        return _advise(parsed, args.data_dir)

    run_dir = latest_snapshot_dir(args.data_dir)
    if run_dir is None:
        raise SystemExit("Aucun snapshot : lancer d'abord `python3 -m fpl_advisor collect`.")
    return _advise(load_snapshot(run_dir, cfg), args.data_dir)


if __name__ == "__main__":
    sys.exit(main())
