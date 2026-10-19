# -*- coding: utf-8 -*-
"""Distributions simulées et contrat 1.1 — hors ligne.

Ce que ces tests protègent :
  1. la simulation garde l'espérance du contrat : elle ajoute une forme, elle
     ne déplace pas la moyenne ;
  2. l'aléa est partagé dans une équipe (deux défenseurs gagnent leur clean
     sheet ensemble) et seulement si on le demande ;
  3. le CRPS d'une prévision ponctuelle est l'erreur absolue ;
  4. un contrat 1.0 se relit (migration en mémoire) et se complète ; un 1.1
     fait l'aller-retour JSON sans perte ;
  5. sur l'archive GW2–GW6, la distribution bat les trois scénarios et
     l'espérance seule en CRPS.
"""

import gzip
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from fpl_advisor import weekly                                   # noqa: E402
from fpl_advisor.demo import build_parsed                        # noqa: E402
from fpl_advisor.forecasting import (CONTRACT_VERSION,           # noqa: E402
                                     ProjectionSet, distribution)
from fpl_advisor.forecasting.contract import migrate_1_0         # noqa: E402


def _contract():
    if not hasattr(_contract, "cache"):
        _contract.cache = weekly.build_contract(build_parsed())
    return _contract.cache


class CrpsTests(unittest.TestCase):
    def test_point_egal_erreur_absolue(self):
        self.assertAlmostEqual(distribution.crps([4.0], 7.0), 3.0)
        self.assertAlmostEqual(distribution.crps([4.0] * 50, 1.0), 3.0)

    def test_une_loi_centree_bat_un_point_decale(self):
        rng = random.Random(1)
        xs = [rng.gauss(5, 2) for _ in range(2000)]
        self.assertLess(distribution.crps(xs, 5.0), distribution.crps([8.0], 5.0))


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = _contract()
        cls.gw = cls.c.gw
        cls.tir = cls.c.simulate(cls.gw, n=4000)

    def test_l_esperance_du_contrat_est_conservee(self):
        rows = [r for r in self.c.rows if r.gw == self.gw and r.ep > 2]
        for r in rows[:25]:
            s = self.tir[r.player_id]
            self.assertAlmostEqual(sum(s) / len(s), r.ep, delta=0.2,
                                   msg=f"joueur {r.player_id}")

    def _defenseurs_meme_equipe(self):
        par_eq = {}
        for r in self.c.rows:
            m = self.c.players[str(r.player_id)]
            if r.gw == self.gw and m["element_type"] == 2 and r.p60 > 0.8:
                par_eq.setdefault(m["team"], []).append(r.player_id)
        return next(v[:2] for v in par_eq.values() if len(v) >= 2)

    @staticmethod
    def _corr(x, y):
        n = len(x)
        mx, my = sum(x) / n, sum(y) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
        vx = sum((a - mx) ** 2 for a in x)
        vy = sum((b - my) ** 2 for b in y)
        return cov / (vx * vy) ** 0.5

    def test_deux_defenseurs_sont_correles(self):
        a, b = self._defenseurs_meme_equipe()
        self.assertGreater(self._corr(self.tir[a], self.tir[b]), 0.3)

    def test_sans_partage_ils_ne_le_sont_pas(self):
        a, b = self._defenseurs_meme_equipe()
        ind = self.c.simulate(self.gw, n=4000, partage=False)
        self.assertLess(abs(self._corr(ind[a], ind[b])), 0.08)

    def test_reproductible(self):
        r = next(r for r in self.c.rows if r.gw == self.gw and r.ep > 3)
        a = self.c.simulate(self.gw, n=200)[r.player_id]
        b = self.c.simulate(self.gw, n=200)[r.player_id]
        self.assertEqual(a, b)


class ContratTests(unittest.TestCase):
    def test_version_et_dist_par_ligne(self):
        c = _contract()
        self.assertEqual(CONTRACT_VERSION, "1.1")
        self.assertEqual(c.contract_version, "1.1")
        self.assertTrue(all(r.dist and len(r.dist["q"]) == 7 for r in c.rows))
        self.assertEqual(set(c.matchs), {str(g) for g in c.horizon})

    def test_aller_retour_json(self):
        c = _contract()
        with tempfile.TemporaryDirectory() as tmp:
            relu = ProjectionSet.load(c.save(Path(tmp) / "p.json.gz"))
        self.assertEqual(relu.rows[0].dist, c.rows[0].dist)
        self.assertEqual(relu.matchs, c.matchs)

    def test_un_contrat_1_0_se_relit_puis_se_complete(self):
        p = RACINE / "projections-figees" / "projections-GW6.json.gz"
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["contract_version"], "1.0")
        c = ProjectionSet.load(p)
        self.assertEqual(c.contract_version, "1.1")
        self.assertIsNone(c.rows[0].dist)
        self.assertFalse(c.distribution["calcule"])
        with self.assertRaises(ValueError):
            c.simulate(6)
        from fpl_advisor.evaluation.benchmark import charger_resultats
        res = charger_resultats(6, RACINE / "resultats-observes")
        migrate_1_0(c, {6: [(f["team_h"], f["team_a"]) for f in res["fixtures"]]}, n=200)
        rows6 = [r for r in c.rows if r.gw == 6]
        self.assertTrue(all(r.dist is not None for r in rows6))
        self.assertTrue(all(r.dist is None for r in c.rows if r.gw != 6))
        self.assertEqual(c.distribution["gws"], [6])


class ArchiveReelleTests(unittest.TestCase):
    """VÉRIFIÉ le 19/10/2026 : contrats figés GW2–GW6 contre points réels."""

    @classmethod
    def setUpClass(cls):
        from banc_distributions import comparer, lignes_archive
        j, e = lignes_archive(RACINE / "projections-figees",
                              RACINE / "resultats-observes", n=300)
        j = {g: v for g, v in j.items() if g in (2, 3, 4, 5, 6)}
        e = {g: v for g, v in e.items() if g in (2, 3, 4, 5, 6)}
        cls.res = {"sc": comparer(j, "sim", "scenarios", 300),
                   "pt": comparer(j, "sim", "point", 300),
                   "e_sc": comparer(e, "sim", "scenarios", 300)}

    def test_la_distribution_bat_les_trois_scenarios(self):
        self.assertEqual(self.res["sc"]["verdict"], "oui")
        self.assertEqual(self.res["e_sc"]["verdict"], "oui")

    def test_la_distribution_bat_l_esperance_seule(self):
        self.assertEqual(self.res["pt"]["verdict"], "oui")


if __name__ == "__main__":
    unittest.main()
