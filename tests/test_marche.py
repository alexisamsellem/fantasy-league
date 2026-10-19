# -*- coding: utf-8 -*-
"""Le marché comme juge des probabilités d'équipe — hors ligne.

Ce que ces tests protègent :
  1. la marge du bookmaker est retirée (probabilités qui somment à 1) ;
  2. l'ajustement retrouve les λ de Poisson qui ont produit des prix ;
  3. le λ du moteur se relit EXACTEMENT dans un contrat figé ;
  4. la décision de ne pas brancher le marché reste fondée : si, sur
     l'archive, le marché se met à battre le moteur, le test casse et la
     question se rouvre.
"""

import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from fpl_advisor import scoring                                 # noqa: E402
from fpl_advisor.evaluation import marche                       # noqa: E402


class MargeEtAjustementTests(unittest.TestCase):
    def test_devig_somme_a_un(self):
        p, marge = marche.devig([2.0, 3.4, 3.8])
        self.assertAlmostEqual(sum(p), 1.0, places=12)
        self.assertGreater(marge, 0.0)

    def test_ajustement_retrouve_les_lambdas(self):
        h, _, a, o = marche.match_probs(1.7, 0.9)
        lh, la = marche.fit_lambdas(h, a, o)
        self.assertAlmostEqual(lh, 1.7, places=4)
        self.assertAlmostEqual(la, 0.9, places=4)

    def test_ligne_csv_et_noms_fpl(self):
        h, d, a, o = marche.match_probs(1.5, 1.1)
        row = {"HomeTeam": "Man United", "AwayTeam": "Tottenham",
               "AvgH": 1 / (h * 1.05), "AvgD": 1 / (d * 1.05), "AvgA": 1 / (a * 1.05),
               "Avg>2.5": 1 / (o * 1.04), "Avg<2.5": 1 / ((1 - o) * 1.04)}
        m = marche.market_lambdas(row)
        self.assertEqual((m["home"], m["away"]), ("MUN", "TOT"))
        self.assertAlmostEqual(m["lam_h"], 1.5, places=3)
        self.assertAlmostEqual(m["marge_1x2"], 0.05, places=6)
        self.assertIsNone(marche.market_lambdas({"HomeTeam": "X"}))


class LectureDuMoteurTests(unittest.TestCase):
    def test_lambda_relu_dans_les_composantes(self):
        lam = 1.3
        rows = [SimpleNamespace(gw=5, player_id=1, n_fixtures=1, p60=0.8,
                                components={"cs": 0.8 * math.exp(-lam) * scoring.CS_POINTS[2]}),
                SimpleNamespace(gw=5, player_id=2, n_fixtures=1, p60=0.01,
                                components={"cs": 0.001})]
        c = SimpleNamespace(gw=5, rows=rows, players={
            "1": {"team": 7, "element_type": 2}, "2": {"team": 8, "element_type": 1}})
        out = marche.lambdas_moteur(c)
        self.assertAlmostEqual(out[7], lam, places=12)
        self.assertNotIn(8, out)              # P(60+) trop faible : illisible


class ArchiveReelleTests(unittest.TestCase):
    """VÉRIFIÉ le 19/10/2026 : 50 matchs GW2–GW6, cotes football-data.co.uk
    lues le même jour, contrats figés modèle 0.3.1."""

    @classmethod
    def setUpClass(cls):
        from banc_marche import lignes_archive, mesurer
        lignes, cls.exclus = lignes_archive(RACINE / "projections-figees",
                                            RACINE / "resultats-observes")
        cls.lignes = {g: v for g, v in lignes.items() if g in (2, 3, 4, 5, 6)}
        cls.res = {q: mesurer(cls.lignes, q, b=300) for q in ("buts", "cs")}

    def test_cinquante_matchs_apparies(self):
        self.assertEqual(sum(len(v) for v in self.lignes.values()), 100)
        self.assertEqual(sum(self.exclus[g] for g in self.lignes), 0)

    def test_le_marche_ne_bat_pas_le_moteur(self):
        for q in ("buts", "cs"):
            self.assertFalse(self.res[q]["marche_gagne"], q)
            self.assertLess(self.res[q]["ic"][0], 0)


if __name__ == "__main__":
    unittest.main()
