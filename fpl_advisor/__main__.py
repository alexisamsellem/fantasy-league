# -*- coding: utf-8 -*-
"""CLI du conseiller FPL V0.

  python3 -m fpl_advisor collect   # collecte + snapshot immuable + DuckDB
  python3 -m fpl_advisor advise    # recommandation depuis le dernier snapshot
  python3 -m fpl_advisor run      # collect puis advise (rituel de deadline)
  python3 -m fpl_advisor demo     # bout-en-bout sur données synthétiques
"""

import argparse
import sys

from .advise import build_recommendation
from .api import load_config
from .collect import collect_all, latest_snapshot_dir, load_duckdb, load_snapshot
from .report import write_report


def _advise(parsed, data_dir):
    rec = build_recommendation(parsed)
    path = write_report(rec, data_dir)
    band = rec["armband"]
    print(f"Rapport : {path}")
    print(f"GW{rec['gw']} — capitaine {band['captain']['web_name']}, "
          f"vice {band['vice']['web_name']} ; transfert : {rec['transfer']['decision']}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fpl_advisor")
    ap.add_argument("command", choices=["collect", "advise", "run", "demo"])
    ap.add_argument("--config", default="config.local.json")
    ap.add_argument("--data-dir", default="data")
    args = ap.parse_args(argv)

    if args.command == "demo":
        from .demo import build_parsed
        return _advise(build_parsed(), args.data_dir)

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
