# -*- coding: utf-8 -*-
"""Recalibration de P(60+) — le défaut répété GW2–GW6, figé par un test.

Ce que ces tests protègent :
  1. la carte livrée au moteur (`priors.P60_RECAL`) est bien celle qu'on
     obtient en l'ajustant sur les contrats FIGÉS GW2–GW6 : la constante n'a
     pas été retouchée à la main ;
  2. le protocole sans regard vers l'avant : la carte qui note la GW k
     n'a vu que les GW < k ;
  3. hors échantillon (GW3–GW6), la carte réduit le Brier poolé et ramène la
     tranche 60–80 % à moins de 5 points de l'observé — c'était +11 points ;
  4. le moteur applique la carte au P(60+) central, et P(jouer) ≥ P(60+).
"""

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from fpl_advisor.evaluation import benchmark as bm             # noqa: E402
from fpl_advisor.evaluation import calibration as cal          # noqa: E402
from fpl_advisor.evaluation import recalibration as rc         # noqa: E402
from fpl_advisor.forecasting import MODEL_VERSION, minutes, priors  # noqa: E402

GWS_AJUSTEMENT = (2, 3, 4, 5, 6)


def _paires_archive():
    from calibrer_en_attente import figeages
    out = {}
    for _, c in figeages(RACINE / "projections-figees"):
        if c.gw not in GWS_AJUSTEMENT:
            continue
        res = bm.charger_resultats(c.gw, RACINE / "resultats-observes")
        obs = res["players"]
        out[c.gw] = [(r.p60, 1.0 if obs[str(r.player_id)]["minutes"] >= 60 else 0.0)
                     for r in c.rows
                     if r.gw == c.gw and r.n_fixtures and str(r.player_id) in obs]
    return out


class CarteTests(unittest.TestCase):
    def test_identite_et_bornes(self):
        self.assertAlmostEqual(rc.appliquer(0.37, 0.0, 1.0), 0.37, places=9)
        self.assertEqual(rc.appliquer(0.0, 0.4, 1.4), 0.0)
        self.assertEqual(rc.appliquer(1.0, 0.4, 1.4), 1.0)

    def test_ajustement_retrouve_une_carte_connue(self):
        import random
        rng = random.Random(7)
        pairs = []
        for _ in range(20000):
            p = rng.uniform(0.02, 0.98)
            q = rc.appliquer(p, 0.5, 1.5)
            pairs.append((p, 1.0 if rng.random() < q else 0.0))
        a, b = rc.ajuster(pairs)
        self.assertAlmostEqual(a, 0.5, delta=0.08)
        self.assertAlmostEqual(b, 1.5, delta=0.08)

    def test_walk_forward_ne_regarde_jamais_devant(self):
        data = {g: [(0.5, float(i % 2)) for i in range(40)] for g in (2, 3, 4)}
        wf = rc.walk_forward(data)
        self.assertEqual(sorted(wf), [3, 4])
        self.assertEqual(wf[3]["fit_sur"], [2])
        self.assertEqual(wf[4]["fit_sur"], [2, 3])


class ArchiveReelleTests(unittest.TestCase):
    """VÉRIFIÉ le 19/10/2026 sur projections-figees/ (modèle 0.3.1) et
    resultats-observes/ (live FPL validé)."""

    @classmethod
    def setUpClass(cls):
        cls.data = _paires_archive()
        cls.wf = rc.walk_forward(cls.data)

    def test_la_constante_du_moteur_est_l_ajustement_de_l_archive(self):
        a, b = rc.ajuster([p for g in GWS_AJUSTEMENT for p in self.data[g]])
        self.assertAlmostEqual(priors.P60_RECAL[0], a, places=3)
        self.assertAlmostEqual(priors.P60_RECAL[1], b, places=3)

    def test_le_defaut_etait_repete(self):
        for g in GWS_AJUSTEMENT:
            tranche = cal.reliability(self.data[g])[3]          # 60–80 %
            self.assertGreater(tranche["ecart"], 0.03, f"GW{g}")

    def test_hors_echantillon_le_brier_baisse(self):
        brut = [p for g in self.wf for p in self.data[g]]
        recal = [p for g in self.wf for p in self.wf[g]["pairs_cal"]]
        self.assertLess(cal.brier(recal), cal.brier(brut) - 0.003)

    def test_hors_echantillon_la_tranche_60_80_est_corrigee(self):
        brut = [p for g in self.wf for p in self.data[g]]
        recal = [p for g in self.wf for p in self.wf[g]["pairs_cal"]]
        self.assertGreater(cal.reliability(brut)[3]["ecart"], 0.08)
        self.assertLess(abs(cal.reliability(recal)[3]["ecart"]), 0.05)


class MoteurTests(unittest.TestCase):
    def test_version_du_modele(self):
        self.assertEqual(MODEL_VERSION, "forecasting/0.4.0")

    def test_le_moteur_applique_la_carte_au_central(self):
        joueur = {"id": 1, "element_type": 3, "status": "a",
                  "chance_of_playing_next_round": None}
        hist = [{"minutes": 90, "started": True}] * 2 + [{"minutes": 0, "started": False}] * 2
        m = minutes.minutes_model(joueur, hist)
        carte = priors.P60_RECAL
        try:
            priors.P60_RECAL = (0.0, 1.0)
            brut = minutes.minutes_model(joueur, hist)
        finally:
            priors.P60_RECAL = carte
        self.assertAlmostEqual(m["p60"], rc.appliquer(brut["p60"], *carte), places=9)
        self.assertGreaterEqual(m["p_play"], m["p60"])

    def test_indisponible_reste_a_zero(self):
        joueur = {"id": 1, "element_type": 4, "status": "i",
                  "chance_of_playing_next_round": 0}
        m = minutes.minutes_model(joueur, [{"minutes": 90, "started": True}] * 5)
        self.assertEqual(m["p60"], 0.0)
        self.assertEqual(m["p_play"], 0.0)


if __name__ == "__main__":
    unittest.main()
