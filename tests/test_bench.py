# -*- coding: utf-8 -*-
"""Test d'acceptation : deux effectifs légaux issus du MÊME snapshot.

Ce fichier vérifie que la comparaison est bien POSÉE (deux effectifs légaux,
un protocole figé, des métriques exécutables). Il ne vérifie PAS — et ne peut
pas vérifier — que les projections internes sont meilleures que la baseline :
cela demande quatre GW réellement jouées.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import bench, initial                   # noqa: E402
from fpl_advisor.demo import build_parsed_initial        # noqa: E402


def _bench():
    if not hasattr(_bench, "cache"):
        _bench.cache = bench.build_bench(build_parsed_initial())
    return _bench.cache


class LegaliteDesDeuxEffectifsTests(unittest.TestCase):
    """Budget, quotas et limite de trois joueurs par club, des DEUX côtés."""

    def test_les_deux_effectifs_respectent_les_contraintes_fpl(self):
        for nom, sq in _bench()["squads"].items():
            legal = sq["legality"]
            with self.subTest(effectif=nom):
                self.assertTrue(legal["size_ok"], f"{nom} : {legal['size']} joueurs")
                self.assertTrue(legal["budget_ok"],
                                f"{nom} : {legal['cost']} > {legal['budget']}")
                self.assertTrue(legal["quota_ok"], f"{nom} : quotas {legal['quota']}")
                self.assertTrue(legal["club_ok"],
                                f"{nom} : {legal['max_per_club']} joueurs d'un même club")
                self.assertEqual(legal["quota"], initial.SQUAD_QUOTA)
                self.assertLessEqual(legal["max_per_club"], initial.MAX_PER_CLUB)

    def test_les_deux_effectifs_viennent_du_meme_snapshot(self):
        b = _bench()
        self.assertEqual(len(b["horizon"]), initial.INITIAL_HORIZON_GWS)
        for sq in b["squads"].values():
            self.assertEqual(sorted(int(g) for g in sq["decisions_par_gw"]),
                             b["horizon"])
            for p in sq["players"]:
                self.assertEqual(sorted(int(g) for g in p["eps"]), b["horizon"])

    def test_les_deux_effectifs_different_reellement(self):
        # Si les deux effectifs étaient identiques, la comparaison serait vide.
        b = _bench()
        self.assertLess(b["recouvrement"], 15)


class BaselinePubliqueTests(unittest.TestCase):
    """La baseline est publique, déterministe et choisie AVANT les résultats."""

    def test_ep_next_prioritaire(self):
        self.assertEqual(_bench()["baseline_field"], bench.BASELINE_PRIMARY)

    def test_repli_deterministe_si_ep_next_absent(self):
        parsed = build_parsed_initial()
        for e in parsed["bootstrap"]["elements"]:
            e["ep_next"] = None
        field, why = bench.baseline_field(parsed)
        self.assertEqual(field, bench.BASELINE_FALLBACK)
        self.assertIn("défini à l'avance", why)

    def test_arret_net_si_aucune_baseline_publique(self):
        parsed = build_parsed_initial()
        for e in parsed["bootstrap"]["elements"]:
            e["ep_next"] = None
            e["selected_by_percent"] = "0.0"
        self.assertIsNone(bench.baseline_field(parsed)[0])
        with self.assertRaises(SystemExit):
            bench.baseline_rows(parsed, [1, 2, 3, 4])

    def test_valeurs_declarees_non_comparables_entre_effectifs(self):
        for sq in _bench()["squads"].values():
            self.assertIn("value4_selon_sa_propre_fonction", sq)
            self.assertIn("non comparable", sq["avertissement_valeur"])


class ProtocoleTests(unittest.TestCase):
    """Le protocole de comparaison est figé et complet."""

    def test_les_quatre_metriques_sont_definies(self):
        cles = {m["key"] for m in bench.COMPARISON_PROTOCOL["metrics"]}
        self.assertEqual(cles, {"score_total", "score_hors_capitaine",
                                "joueurs_zero_minute", "calibration_p60"})
        for m in bench.COMPARISON_PROTOCOL["metrics"]:
            self.assertGreater(len(m["definition"]), 40)

    def test_les_limites_du_protocole_sont_ecrites(self):
        p = bench.COMPARISON_PROTOCOL
        self.assertIn("NON simulés", p["auto_subs"])
        self.assertIn("aucun verdict de qualité", p["verdict_rule"])

    def test_le_protocole_est_dans_l_artefact_fige(self):
        self.assertEqual(_bench()["protocole"], bench.COMPARISON_PROTOCOL)


class ExecutionDuProtocoleTests(unittest.TestCase):
    """Les métriques s'exécutent sur des résultats et se comportent bien."""

    def _live(self, minutes, points):
        b = _bench()
        ids = {p["id"] for sq in b["squads"].values() for p in sq["players"]}
        return {gw: {pid: {"minutes": minutes, "total_points": points}
                     for pid in ids} for gw in b["horizon"]}

    def test_les_quatre_metriques_sont_produites(self):
        res = bench.score_frozen(_bench(), self._live(90, 5))
        for nom, r in res.items():
            with self.subTest(effectif=nom):
                self.assertEqual(r["joueurs_zero_minute"], 0)
                # 11 titulaires × 4 GW × 5 pts = 220, + capitaine doublé 4 × 5
                self.assertEqual(r["score_hors_capitaine"], 11 * 4 * 5)
                self.assertEqual(r["score_total"], 11 * 4 * 5 + 4 * 5)
                self.assertIsNotNone(r["calibration_p60"]["brier"])
                self.assertEqual(r["calibration_p60"]["n"], 15 * 4)

    def test_les_joueurs_a_zero_minute_sont_comptes(self):
        res = bench.score_frozen(_bench(), self._live(0, 0))
        for r in res.values():
            self.assertEqual(r["joueurs_zero_minute"], 11 * 4)

    def test_la_regle_du_vice_capitaine_est_appliquee(self):
        # Capitaine à 0 minute : c'est le VICE qui est doublé (règle FPL exacte).
        b = _bench()
        sq = b["squads"]["interne"]
        live = {}
        for gw_s, dec in sq["decisions_par_gw"].items():
            gw = int(gw_s)
            live[gw] = {}
            for p in sq["players"]:
                live[gw][p["id"]] = {"minutes": 90, "total_points": 2}
            live[gw][dec["captain"]] = {"minutes": 0, "total_points": 0}
            live[gw][dec["vice"]] = {"minutes": 90, "total_points": 7}
        r = bench.score_frozen(b, live)["interne"]
        # 10 titulaires à 2 pts + le vice à 7 + capitaine 0, puis vice doublé
        self.assertEqual(r["score_hors_capitaine"], 4 * (9 * 2 + 7 + 0))
        self.assertEqual(r["score_total"], r["score_hors_capitaine"] + 4 * 7)

    def test_la_calibration_recompense_une_prevision_juste(self):
        b = _bench()
        juste = bench.score_frozen(b, self._live(90, 4))["interne"]["calibration_p60"]["brier"]
        faux = bench.score_frozen(b, self._live(0, 0))["interne"]["calibration_p60"]["brier"]
        self.assertNotEqual(juste, faux)
        for v in (juste, faux):
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)


class ReproductibiliteTests(unittest.TestCase):
    """Même snapshot → mêmes effectifs figés, et artefact relisible."""

    def test_deux_executions_donnent_le_meme_banc(self):
        a = bench.build_bench(build_parsed_initial())
        b = bench.build_bench(build_parsed_initial())
        for key in ("interne", "baseline"):
            self.assertEqual([p["id"] for p in a["squads"][key]["players"]],
                             [p["id"] for p in b["squads"][key]["players"]])

    def test_artefact_ecrit_et_relisible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = bench.write_bench(_bench(), tmp)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(data["recouvrement"], _bench()["recouvrement"])
            self.assertIn("protocole", data)
            self.assertIn("sources", data)

    def test_la_demo_est_marquee_comme_non_validante(self):
        b = _bench()
        self.assertTrue(b["synthetic"])
        self.assertIn("AUCUNE validation de qualité", b["avertissement"])


if __name__ == "__main__":
    unittest.main()
