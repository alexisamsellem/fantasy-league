# -*- coding: utf-8 -*-
"""CLI du conseiller FPL V0.

  python3 -m fpl_advisor collect        # collecte + snapshot immuable + DuckDB
  python3 -m fpl_advisor advise         # recommandation depuis le dernier snapshot
  python3 -m fpl_advisor run            # collect puis advise (rituel de deadline)
  python3 -m fpl_advisor demo           # bout-en-bout sur données synthétiques
  python3 -m fpl_advisor initial-squad  # effectif initial 15 joueurs (sans config)
  python3 -m fpl_advisor initial-bench  # banc d'essai : interne vs baseline publique
"""

import argparse
import sys

from .advise import build_recommendation
from .api import load_config
from .collect import (collect_all, collect_public, latest_snapshot_dir,
                      load_duckdb, load_public_snapshot, load_snapshot)
from .bench import build_bench, write_bench
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
                    choices=["collect", "advise", "run", "demo", "initial-squad",
                             "initial-bench"])
    ap.add_argument("--config", default="config.local.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--demo", action="store_true",
                    help="initial-squad/initial-bench : jeu synthétique hors "
                         "ligne, aucun réseau — invariants seulement, ne vaut "
                         "aucune validation de qualité")
    ap.add_argument("--with-history", action="store_true",
                    help="initial-squad : collecte aussi les saisons passées "
                         "(un GET public par joueur, long mais c'est la source "
                         "qui rend un top 15 de pré-saison défendable)")
    args = ap.parse_args(argv)

    if args.command == "demo":
        from .demo import build_parsed
        return _advise(build_parsed(), args.data_dir)

    if args.command in ("initial-squad", "initial-bench"):
        if args.demo:
            from .demo import build_parsed_initial
            parsed = build_parsed_initial()
        else:
            run_dir = collect_public(args.data_dir, with_history=args.with_history)
            print(f"Snapshot : {run_dir}")
            parsed = load_public_snapshot(run_dir)
        if args.command == "initial-bench":
            bench = build_bench(parsed)
            path = write_bench(bench, args.data_dir)
            print(f"Banc d'essai figé : {path}")
            print(f"Baseline : {bench['baseline_field']} — {bench['baseline_reason']}")
            print(f"Recouvrement interne/baseline : {bench['recouvrement']}/15 ; "
                  f"confiance projections : {bench['confiance_projections']}")
            if bench["synthetic"]:
                print("ATTENTION : données synthétiques — invariants seulement, "
                      "aucune validation de qualité.")
            return 0
        return _initial(parsed, args.data_dir)

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
