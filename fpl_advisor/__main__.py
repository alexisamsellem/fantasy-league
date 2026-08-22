# -*- coding: utf-8 -*-
"""CLI du conseiller FPL V0.

  python3 -m fpl_advisor collect        # collecte + snapshot immuable + DuckDB
  python3 -m fpl_advisor advise         # décision de la semaine depuis le dernier snapshot
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
from .evaluation.bench import build_bench, write_bench
from .forecasting import ProjectionSet
from .initial import build_contract, build_from_contract
from .report import write_initial_report, write_report
from .wiring import selection_backend


def _advise(parsed, data_dir, freeze_to=None):
    rec = build_recommendation(parsed, freeze_to=freeze_to)
    path = write_report(rec, data_dir)
    band, v = rec["armband"], rec["verdict"]
    if rec.get("frozen_projections"):
        print(f"Projections figées : {rec['frozen_projections']}")
    print(f"Rapport : {path}")
    print(f"GW{rec['gw']} — {v.label} : capitaine {band['captain']['web_name']}, "
          f"vice {band['vice']['web_name']} ; transfert : {rec['transfer']['decision']}")
    print(f"Contrôle qualité : {v.state.upper()} — {v.summary}")
    return 0


def _initial(contract, data_dir):
    rec = build_from_contract(contract)
    path = write_initial_report(rec, data_dir)
    band, v = rec["armband"], rec["verdict"]
    print(f"Rapport : {path}")
    print(f"GW{rec['gw']} — {v.label} : {rec['cost'] / 10:.1f} M£ utilisés "
          f"(banque {rec['bank'] / 10:.1f} M£) ; capitaine {band['captain']['web_name']}, "
          f"vice {band['vice']['web_name']}")
    print(f"Contrôle qualité : {v.state.upper()} — {v.summary}")
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
    ap.add_argument("--freeze-projections", metavar="FICHIER",
                    help="écrit le contrat de projections dans un fichier JSON "
                         "réutilisable sans le snapshot (initial-squad et "
                         "advise/run : trace auditable de la décision, sans "
                         "aucune donnée personnelle)")
    ap.add_argument("--from-projections", metavar="FICHIER",
                    help="repart d'un contrat de projections figé : aucune "
                         "collecte, aucun recalcul de prévision. Réservé à "
                         "initial-squad : le mode hebdomadaire a aussi besoin "
                         "de l'effectif détenu, qui reste hors du contrat")
    ap.add_argument("--with-history", action="store_true",
                    help="initial-squad : collecte aussi les saisons passées "
                         "(un GET public par joueur, long mais c'est la source "
                         "qui rend un top 15 de pré-saison défendable)")
    args = ap.parse_args(argv)

    if args.command == "demo":
        from .demo import build_parsed
        return _advise(build_parsed(), args.data_dir, args.freeze_projections)

    if args.command in ("initial-squad", "initial-bench"):
        if args.from_projections:
            contract = ProjectionSet.load(args.from_projections)
            print(f"Projections figées relues : {args.from_projections} "
                  f"(contrat v{contract.contract_version}, modèle "
                  f"{contract.model_version}, connues au {contract.as_of}) — "
                  "aucune donnée brute lue.")
        else:
            if args.demo:
                from .demo import build_parsed_initial
                parsed = build_parsed_initial()
            else:
                run_dir = collect_public(args.data_dir, with_history=args.with_history)
                print(f"Snapshot : {run_dir}")
                parsed = load_public_snapshot(run_dir)
            contract = build_contract(parsed)
            if args.freeze_projections:
                print(f"Projections figées : {contract.save(args.freeze_projections)}")
        if args.command == "initial-bench":
            bench = build_bench(contract, selection_backend())
            path = write_bench(bench, args.data_dir)
            print(f"Banc d'essai figé : {path}")
            print(f"Baseline : {bench['baseline_field']} — {bench['baseline_reason']}")
            print(f"Recouvrement interne/baseline : {bench['recouvrement']}/15 ; "
                  f"confiance projections : {bench['confiance_projections']}")
            print("Contrôle qualité (projections seules) : "
                  f"{bench['verdict_qualite_projections']['state'].upper()}")
            if bench["synthetic"]:
                print("ATTENTION : données synthétiques — invariants seulement, "
                      "aucune validation de qualité.")
            return 0
        return _initial(contract, args.data_dir)

    cfg = load_config(args.config)
    if args.command in ("collect", "run"):
        run_dir = collect_all(cfg, args.data_dir)
        print(f"Snapshot : {run_dir}")
        parsed = load_snapshot(run_dir, cfg)
        print(load_duckdb(parsed, f"{args.data_dir}/fpl.duckdb"))
        if args.command == "collect":
            return 0
        return _advise(parsed, args.data_dir, args.freeze_projections)

    run_dir = latest_snapshot_dir(args.data_dir)
    if run_dir is None:
        raise SystemExit("Aucun snapshot : lancer d'abord `python3 -m fpl_advisor collect`.")
    return _advise(load_snapshot(run_dir, cfg), args.data_dir,
                   args.freeze_projections)


if __name__ == "__main__":
    sys.exit(main())
