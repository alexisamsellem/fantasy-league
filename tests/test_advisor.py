# -*- coding: utf-8 -*-
"""Tests essentiels du conseiller V0 — hors ligne, aucune requête réseau."""

import sys
import unittest
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import model, team           # noqa: E402
from fpl_advisor.advise import build_recommendation   # noqa: E402
from fpl_advisor.demo import build_parsed     # noqa: E402
from fpl_advisor.report import render         # noqa: E402
from fpl_advisor.rivals import local_exposure  # noqa: E402


def _squad(eps):
    """15 joueurs synthétiques : 2 GB, 5 DEF, 5 MIL, 3 ATT avec les EP donnés."""
    types = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    return [{"id": i + 1, "element_type": t, "ep": eps[i], "p_play": 1.0,
             "p0": 0.0, "team": i % 6 + 1, "now_cost": 50,
             "web_name": f"J{i+1}"}
            for i, (t, _) in enumerate(zip(types, eps))]


class XiTests(unittest.TestCase):
    def _brute_force(self, squad):
        best, score = None, -1
        for combo in combinations(squad, 11):
            gk = sum(1 for p in combo if p["element_type"] == 1)
            d = sum(1 for p in combo if p["element_type"] == 2)
            m = sum(1 for p in combo if p["element_type"] == 3)
            f = sum(1 for p in combo if p["element_type"] == 4)
            if gk != 1 or not (3 <= d <= 5) or not (2 <= m <= 5) or not (1 <= f <= 3):
                continue
            s = sum(p["ep"] for p in combo)
            if s > score:
                best, score = combo, s
        return score

    def test_xi_respecte_les_contraintes_et_atteint_l_optimum(self):
        eps = [4.0, 1.0, 5.0, 4.5, 4.0, 3.5, 1.0, 6.0, 5.5, 5.0, 2.0, 1.5, 6.5, 3.0, 1.0]
        squad = _squad(eps)
        xi, bench = team.pick_xi(squad)
        self.assertEqual(len(xi), 11)
        self.assertEqual(len(bench), 4)
        self.assertEqual(sum(1 for p in xi if p["element_type"] == 1), 1)
        self.assertGreaterEqual(sum(1 for p in xi if p["element_type"] == 2), 3)
        self.assertGreaterEqual(sum(1 for p in xi if p["element_type"] == 4), 1)
        self.assertAlmostEqual(sum(p["ep"] for p in xi), self._brute_force(squad), places=6)

    def test_banc_gardien_en_premier(self):
        xi, bench = team.pick_xi(_squad([4, 1, 5, 4, 4, 3, 1, 6, 5, 5, 2, 1, 6, 3, 1]))
        self.assertEqual(bench[0]["element_type"], 1)


class ArmbandTests(unittest.TestCase):
    def test_formule_du_brassard(self):
        xi = [{"id": 1, "ep": 6.0, "p0": 0.30, "web_name": "A", "element_type": 4},
              {"id": 2, "ep": 5.5, "p0": 0.05, "web_name": "B", "element_type": 3},
              {"id": 3, "ep": 4.0, "p0": 0.0, "web_name": "C", "element_type": 2}]
        band = team.armband(xi)
        # A+B : 6.0 + 0.30×5.5 = 7.65 ; B+A : 5.5 + 0.05×6.0 = 5.80 → A capitaine
        self.assertEqual(band["captain"]["id"], 1)
        self.assertEqual(band["vice"]["id"], 2)
        self.assertAlmostEqual(band["ev"], 7.65, places=6)


class MinutesTests(unittest.TestCase):
    def test_blesse_sans_chance_ne_joue_pas(self):
        p = {"status": "i", "chance_of_playing_next_round": None,
             "team": 1, "element_type": 2, "now_cost": 50}
        m = model.minutes_model(p, [90, 90], [p])
        self.assertEqual(m["p_play"], 0.0)

    def test_historique_pondere_recent_d_abord(self):
        p = {"status": "a", "chance_of_playing_next_round": None,
             "team": 1, "element_type": 3, "now_cost": 80}
        # 90 min récents, 0 ancien → p60 > 0.5 grâce au poids de récence
        m = model.minutes_model(p, [90, 90, 0, 0, 0], [p])
        self.assertGreater(m["p60"], 0.5)
        self.assertEqual(m["basis"], "historique 5 GW")


class TransferTests(unittest.TestCase):
    def _setup(self, delta):
        out = {"id": 1, "element_type": 4, "team": 1, "now_cost": 60, "web_name": "OUT"}
        inn = {"id": 2, "element_type": 4, "team": 2, "now_cost": 60, "web_name": "IN"}
        squad = [out]
        eps = {1: {3: 2.0, 4: 2.0, 5: 2.0}, 2: {g: 2.0 + delta / 3 for g in (3, 4, 5)}}
        return team.transfer_scan(squad, [inn], eps, bank=0)

    def test_au_dessus_du_seuil_transferer(self):
        self.assertEqual(self._setup(3.0)["decision"], "transférer")

    def test_sous_le_seuil_conserver(self):
        self.assertEqual(self._setup(1.0)["decision"], "conserver")


class ExposureTests(unittest.TestCase):
    def test_capitaine_compte_double(self):
        parsed = {
            "bootstrap": {"elements": [{"id": 7, "web_name": "X"}]},
            "last_closed_gw": 2,
            "my": {"picks": {"picks": []}},
            "rivals": {
                1: {"picks": {"picks": [{"element": 7, "is_captain": True}]}},
                2: {"picks": {"picks": [{"element": 7, "is_captain": False}]}},
            },
        }
        table, meta = local_exposure(parsed)
        self.assertEqual(meta["n_with_picks"], 2)
        self.assertAlmostEqual(table[0]["eo_local"], 1.5)  # (2 + 1) / 2


class DemoEndToEndTests(unittest.TestCase):
    def test_recommandation_complete_et_rapport(self):
        rec = build_recommendation(build_parsed())
        self.assertEqual(len(rec["xi"]), 11)
        self.assertEqual(len(rec["bench"]), 4)
        self.assertIn(rec["transfer"]["decision"], ("transférer", "conserver"))
        text = render(rec)
        for section in ("## Synthèse", "## XI recommandé", "## Banc",
                        "## Capitaine et vice", "## Transférer ou conserver",
                        "## Projections, incertitude",
                        "## Mini-ligue — exposition connue des rivaux",
                        "## Événements qui feraient changer",
                        "## Limites de la V0"):
            self.assertIn(section, text)


if __name__ == "__main__":
    unittest.main()
