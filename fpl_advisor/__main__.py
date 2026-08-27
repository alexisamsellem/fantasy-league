# -*- coding: utf-8 -*-
"""CLI du conseiller FPL V0.

  python3 -m fpl_advisor collect        # collecte + snapshot immuable + DuckDB
  python3 -m fpl_advisor advise         # décision de la semaine depuis le dernier snapshot
  python3 -m fpl_advisor run            # collect puis advise (rituel de deadline)
  python3 -m fpl_advisor demo           # bout-en-bout sur données synthétiques
  python3 -m fpl_advisor initial-squad  # effectif initial 15 joueurs (sans config)
  python3 -m fpl_advisor initial-bench  # banc d'essai : interne vs baseline publique
  python3 -m fpl_advisor audit-effectif # effectif détenu vs effectif reconstruit
  python3 -m fpl_advisor freeze         # fige les projections, sans config ni effectif
  python3 -m fpl_advisor calibrate      # probabilités figées vs résultats réels
"""

import argparse
import sys

from . import weekly
from .advise import build_recommendation
from .api import load_config
from .audit import build_audit
from .collect import (collect_all, collect_public, latest_snapshot_dir,
                      load_duckdb, load_public_snapshot, load_snapshot,
                      observed_minutes)
from .evaluation import calibration
from .evaluation.bench import build_bench, write_bench
from .forecasting import ProjectionSet
from .initial import build_contract, build_from_contract
from .report import (write_audit, write_calibration, write_initial_report,
                     write_report)
from .optimization.audit import PATH_WEEKS
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


def _audit(parsed, data_dir, weeks, freeze_to=None):
    rec = build_audit(parsed, freeze_to=freeze_to, weeks=weeks)
    path = write_audit(rec, data_dir)
    v = rec["verdict"]
    if rec.get("frozen_projections"):
        print(f"Projections figées : {rec['frozen_projections']}")
    print(f"Rapport : {path}")
    if rec["retard"] is None:
        print(f"GW{rec['gw']} — écart non calculable : effectif incomplet.")
    else:
        print(f"GW{rec['gw']}–GW{rec['horizon'][-1]} — retard de l'effectif "
              f"détenu : {rec['retard']:.1f} pts sur {len(rec['horizon'])} GW "
              f"({rec['recouvrement']}/15 joueurs en commun avec l'effectif "
              "reconstruit).")
        ch = rec["chemin"]
        if ch and ch["etapes"]:
            print(f"Chemin proposé : {len(ch['etapes'])} transfert(s) gratuit(s) "
                  f"sur {rec['semaines']} semaines, +{ch['gain_total']:.1f} pts.")
        else:
            print("Aucun échange un-pour-un n'améliore la valeur de l'effectif.")
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
                             "initial-bench", "audit-effectif", "freeze",
                             "calibrate"])
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
    ap.add_argument("--from-snapshot", metavar="DOSSIER",
                    help="freeze : réutilise un snapshot déjà collecté au lieu "
                         "d'en collecter un nouveau. La valeur `dernier` prend "
                         "le snapshot le plus récent de --data-dir")
    ap.add_argument("--semaines", type=int, default=PATH_WEEKS,
                    help="audit-effectif : longueur du chemin de transferts "
                         f"proposé (défaut {PATH_WEEKS}, un transfert gratuit "
                         "par semaine)")
    ap.add_argument("--gw", type=int,
                    help="calibrate : GW à noter (par défaut, la GW de décision "
                         "du contrat figé)")
    ap.add_argument("--with-history", action="store_true",
                    help="collect/run/initial-squad : collecte aussi les saisons "
                         "passées (un GET public par joueur, long). Nécessaire "
                         "tant que la saison en cours n'a pas assez de journées "
                         "jouées pour porter seule la hiérarchie entre joueurs")
    args = ap.parse_args(argv)

    if args.command == "freeze":
        # Figer les projections ne demande NI config, NI team ID, NI effectif :
        # le contrat est public par construction. C'est ce qui permet de
        # produire la trace point-in-time exigée par `calibrate` depuis
        # n'importe quelle machine, sans exposer la moindre donnée personnelle.
        if not args.freeze_projections:
            raise SystemExit(
                "freeze exige --freeze-projections FICHIER : la commande ne "
                "sert qu'à écrire la trace point-in-time des projections.\n"
                "  python3 -m fpl_advisor freeze --with-history "
                "--freeze-projections data/projections-GW<n>.json")
        if args.from_snapshot == "dernier":
            run_dir = latest_snapshot_dir(args.data_dir)
            if run_dir is None:
                raise SystemExit(
                    f"Aucun snapshot sous {args.data_dir}/snapshots : lancer "
                    "d'abord `python3 -m fpl_advisor collect`.")
        elif args.from_snapshot:
            run_dir = args.from_snapshot
        else:
            run_dir = collect_public(args.data_dir, with_history=args.with_history)
        print(f"Snapshot : {run_dir}")
        parsed = load_public_snapshot(run_dir)
        contract = weekly.build_contract(parsed)
        path = contract.save(args.freeze_projections)
        print(f"Projections figées : {path}")
        print(f"GW de décision {contract.gw} (horizon "
              f"{contract.horizon[0]}–{contract.horizon[-1]}), deadline "
              f"{contract.deadline}, connues au {contract.as_of}.")
        print(f"Contrat v{contract.contract_version}, modèle "
              f"{contract.model_version}, {len(contract.players)} joueurs — "
              "aucune donnée personnelle.")
        return 0

    if args.command == "calibrate":
        if not args.from_projections:
            raise SystemExit(
                "calibrate exige --from-projections FICHIER : on note des "
                "prédictions FIGÉES AVANT la deadline, jamais des projections "
                "recalculées après coup. Figer avec :\n"
                "  python3 -m fpl_advisor run --freeze-projections "
                "data/projections-GW<n>.json")
        contract = ProjectionSet.load(args.from_projections)
        gw = args.gw if args.gw is not None else contract.gw
        mins = observed_minutes(args.data_dir, gw)
        res = calibration.assess(contract, mins, gw)
        path = write_calibration(res, args.data_dir)
        print(f"Rapport : {path}")
        for m in res["metriques"].values():
            if m["competence"] is None:
                print(f"{m['label']} : non calculable ({m['n']} joueurs)")
            else:
                print(f"{m['label']} : Brier {m['brier']:.4f} "
                      f"(référence {m['brier_reference']:.4f}) — "
                      f"compétence {m['competence']:+.3f} sur {m['n']} joueurs")
        print(res["conclusion"])
        return 0

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
        run_dir = collect_all(cfg, args.data_dir, args.with_history)
        print(f"Snapshot : {run_dir}")
        parsed = load_snapshot(run_dir, cfg)
        print(load_duckdb(parsed, f"{args.data_dir}/fpl.duckdb"))
        if args.command == "collect":
            return 0
        return _advise(parsed, args.data_dir, args.freeze_projections)

    run_dir = latest_snapshot_dir(args.data_dir)
    if run_dir is None:
        raise SystemExit("Aucun snapshot : lancer d'abord `python3 -m fpl_advisor collect`.")
    parsed = load_snapshot(run_dir, cfg)
    if args.command == "audit-effectif":
        return _audit(parsed, args.data_dir, args.semaines, args.freeze_projections)
    return _advise(parsed, args.data_dir, args.freeze_projections)


if __name__ == "__main__":
    sys.exit(main())
