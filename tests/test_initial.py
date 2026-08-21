# -*- coding: utf-8 -*-
"""Tests essentiels du mode effectif initial — hors ligne, aucune requête."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import initial, model  # noqa: E402
from fpl_advisor.demo import build_parsed_initial  # noqa: E402
from fpl_advisor.report import render_initial  # noqa: E402


def _rec():
    """Recommandation calculée une seule fois pour toute la classe."""
    if not hasattr(_rec, "cache"):
        _rec.cache = initial.build_initial_recommendation(build_parsed_initial())
    return _rec.cache


class InitialSquadConstraintsTests(unittest.TestCase):
    def test_contraintes_fpl_exactes(self):
        rec = _rec()
        squad = rec["squad"]
        self.assertEqual(len(squad), 15)
        self.assertEqual(len({p["id"] for p in squad}), 15)
        for et, quota in initial.SQUAD_QUOTA.items():
            self.assertEqual(sum(1 for p in squad if p["element_type"] == et),
                             quota, f"quota du poste {et}")
        self.assertLessEqual(sum(p["now_cost"] for p in squad), initial.BUDGET)
        clubs = {}
        for p in squad:
            clubs[p["team"]] = clubs.get(p["team"], 0) + 1
        self.assertLessEqual(max(clubs.values()), initial.MAX_PER_CLUB)

    def test_xi_banc_brassard_coherents(self):
        rec = _rec()
        self.assertEqual(len(rec["xi"]), 11)
        self.assertEqual(len(rec["bench"]), 4)
        self.assertEqual(rec["bench"][0]["element_type"], 1)
        xi_ids = {p["id"] for p in rec["xi"]}
        band = rec["armband"]
        self.assertIn(band["captain"]["id"], xi_ids)
        self.assertIn(band["vice"]["id"], xi_ids)
        self.assertNotEqual(band["captain"]["id"], band["vice"]["id"])
        self.assertEqual(rec["cost"] + rec["bank"], rec["budget"])


class InitialSquadOptimizationTests(unittest.TestCase):
    def test_bat_l_effectif_le_moins_cher(self):
        parsed = build_parsed_initial()
        teams_by_id, means = model.team_strengths(parsed["bootstrap"])
        gws = _rec()["horizon"]
        pool = initial.build_pool(parsed, gws, teams_by_id, means)
        base = initial.squad_value(initial.cheapest_squad(pool), gws)
        self.assertGreater(_rec()["value4"], base)

    def test_aucun_echange_ameliorant_restant(self):
        # Optimum local : aucun échange un-pour-un faisable ne fait mieux.
        parsed = build_parsed_initial()
        teams_by_id, means = model.team_strengths(parsed["bootstrap"])
        rec = _rec()
        gws = rec["horizon"]
        pool = initial.build_pool(parsed, gws, teams_by_id, means)
        squad = [r for r in pool if r["id"] in {p["id"] for p in rec["squad"]}]
        self.assertEqual(len(squad), 15)
        value = initial.squad_value(squad, gws)
        cost = sum(r["now_cost"] for r in squad)
        clubs = {}
        for r in squad:
            clubs[r["team"]] = clubs.get(r["team"], 0) + 1
        squad_ids = {r["id"] for r in squad}
        for i, out in enumerate(squad):
            for inn in pool:
                if inn["id"] in squad_ids or inn["element_type"] != out["element_type"]:
                    continue
                if cost - out["now_cost"] + inn["now_cost"] > initial.BUDGET:
                    continue
                if inn["team"] != out["team"] \
                        and clubs.get(inn["team"], 0) + 1 > initial.MAX_PER_CLUB:
                    continue
                v = initial.squad_value(squad[:i] + [inn] + squad[i + 1:], gws)
                self.assertLessEqual(v, value + 1e-9,
                                     f"échange améliorant restant : "
                                     f"{out['web_name']} → {inn['web_name']}")


class InitialReportTests(unittest.TestCase):
    def test_rapport_complet(self):
        text = render_initial(_rec())
        for section in ("# Effectif initial GW1", "## Synthèse",
                        "## Effectif recommandé (15 joueurs)",
                        "## XI recommandé (GW1)", "## Banc (dans l'ordre)",
                        "## Capitaine et vice — règle FPL exacte",
                        "## Projections, incertitude, hypothèses critiques",
                        "## Événements qui feraient changer ces décisions",
                        "## Limites de la V0"):
            self.assertIn(section, text)
        self.assertIn("prior", text)   # pré-saison : bases de projection affichées


class InitialCliTests(unittest.TestCase):
    def test_commande_demo_sans_config(self):
        # Bout-en-bout CLI : aucune config requise, rapport écrit sur disque.
        from fpl_advisor.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["initial-squad", "--demo", "--data-dir", tmp]), 0)
            reports = list((Path(tmp) / "reports").glob("GW1-effectif-initial-*.md"))
            self.assertEqual(len(reports), 1)


if __name__ == "__main__":
    unittest.main()
