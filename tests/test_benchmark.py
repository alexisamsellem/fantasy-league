# -*- coding: utf-8 -*-
"""Banc d'essai sur les points — moteur contre ep_next, hors ligne.

Ce que ces tests protègent :
  1. un contrat figé après la deadline est refusé : noter une prévision qui
     connaissait le résultat ne mesure rien ;
  2. les deux prévisions sont notées sur la MÊME population ;
  3. le verdict ne dit « oui » que si le bootstrap ET Diebold-Mariano le
     disent, « non » dans le cas inverse, « non prouvé » sinon ;
  4. le résultat mesuré sur l'archive réelle (GW2–GW6) reste acquis : si un
     changement du dépôt le fait disparaître, le test casse.
"""

import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from fpl_advisor.evaluation import benchmark as bm             # noqa: E402


def _contrat(as_of="2026-08-28T09:00:00Z", deadline="2026-08-28T17:30:00Z"):
    rows = [SimpleNamespace(gw=2, player_id=i, ep=2.0 + i, n_fixtures=1)
            for i in range(1, 4)]
    rows.append(SimpleNamespace(gw=2, player_id=4, ep=1.0, n_fixtures=0))
    rows.append(SimpleNamespace(gw=3, player_id=1, ep=9.0, n_fixtures=1))
    players = {str(i): {"team": i, "element_type": 3, "ep_next": "2.5"}
               for i in range(1, 5)}
    players["3"]["ep_next"] = None
    return SimpleNamespace(gw=2, as_of=as_of, deadline=deadline,
                           rows=rows, players=players)


def _resultats():
    return {"players": {"1": {"total_points": 3, "minutes": 90},
                        "2": {"total_points": 1, "minutes": 10},
                        "3": {"total_points": 8, "minutes": 90}}}


class PopulationTests(unittest.TestCase):
    def test_refuse_un_contrat_fige_apres_la_deadline(self):
        with self.assertRaises(ValueError):
            bm.paires_points(_contrat(as_of="2026-08-28T18:00:00Z"), _resultats())

    def test_exclusions_comptees_et_meme_population(self):
        lignes, exclus = bm.paires_points(_contrat(), _resultats())
        self.assertEqual([l["player_id"] for l in lignes], [1, 2])
        self.assertEqual(exclus, {"sans_match": 1, "non_observes": 0, "ep_next": 1})
        self.assertTrue(all(l["gw"] == 2 for l in lignes))


class StatistiquesTests(unittest.TestCase):
    def test_student_bilateral(self):
        self.assertAlmostEqual(bm.student_p_bilateral(2.776, 4), 0.05, places=3)
        self.assertAlmostEqual(bm.student_p_bilateral(0.0, 4), 1.0, places=6)
        self.assertAlmostEqual(bm.student_p_bilateral(1.96, 10000), 0.05, places=3)

    def test_diebold_mariano_signe_et_degres(self):
        dm = bm.diebold_mariano([-1.0, -1.2, -0.8, -1.1, -0.9])
        self.assertLess(dm["t"], 0)
        self.assertEqual(dm["ddl"], 4)
        self.assertLess(dm["p"], 0.01)
        self.assertIsNone(bm.diebold_mariano([-1.0]))


def _lignes_synth(ecart, seed=3, n_gw=5):
    """Le moteur se trompe `ecart` fois moins (ecart < 1) ou plus que ep_next."""
    rng = random.Random(seed)
    par_gw = {}
    for g in range(2, 2 + n_gw):
        ls = []
        for t in range(20):
            choc = rng.gauss(0, 1)              # choc commun à l'équipe
            for k in range(25):
                mu = rng.uniform(0, 6)
                y = max(0.0, mu + choc + rng.gauss(0, 2))
                bruit = rng.gauss(0, 2)
                ls.append({"gw": g, "team": t, "player_id": t * 100 + k,
                           "ep": mu + ecart * bruit, "ep_next": mu + bruit, "y": y})
        par_gw[g] = ls
    return par_gw


class VerdictTests(unittest.TestCase):
    def test_meilleur_moteur_oui(self):
        res = bm.evaluer(_lignes_synth(0.3), b=300)
        self.assertEqual(res["global"]["verdict_mse"], "oui")

    def test_pire_moteur_non(self):
        res = bm.evaluer(_lignes_synth(2.0), b=300)
        self.assertEqual(res["global"]["verdict_mse"], "non")

    def test_moteur_identique_non_prouve(self):
        res = bm.evaluer(_lignes_synth(1.0), b=300)
        self.assertEqual(res["global"]["verdict_mse"], "non prouvé")

    def test_bootstrap_contradictoire_avec_dm_reste_non_prouve(self):
        self.assertEqual(bm.verdict((-2.0, -1.0), {"d_moy": -1.5, "p": 0.2}), "non prouvé")
        self.assertEqual(bm.verdict((-2.0, -1.0), None), "non prouvé")


class ArchiveReelleTests(unittest.TestCase):
    """Résultat VÉRIFIÉ le 19/10/2026 sur projections-figees/ GW2–GW6 et
    resultats-observes/ (live FPL lu le même jour). Le test fige la conclusion,
    pas les décimales : il casse si le moteur figé cesse de battre ep_next."""

    @classmethod
    def setUpClass(cls):
        from banc_points import lignes_archive
        cls.lignes, cls.meta = lignes_archive(RACINE / "projections-figees",
                                              RACINE / "resultats-observes")

    def test_cinq_journees_notees_avant_deadline(self):
        self.assertTrue({2, 3, 4, 5, 6} <= set(self.lignes))
        for m in self.meta.values():
            self.assertLess(str(m["as_of"]), str(m["deadline"]))

    def test_le_moteur_fige_bat_ep_next(self):
        res = bm.evaluer({g: self.lignes[g] for g in (2, 3, 4, 5, 6)}, b=400)
        gl = res["global"]
        self.assertLess(gl["ic_dmse"][1], 0)
        self.assertEqual(gl["verdict_mse"], "oui")


if __name__ == "__main__":
    unittest.main()
