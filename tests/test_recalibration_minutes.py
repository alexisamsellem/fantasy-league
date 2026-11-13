# -*- coding: utf-8 -*-
"""Régression A10 : recalibration des probabilités de minutes.

Données réelles, hors ligne, aucune donnée personnelle :
  - projections-figees/projections-GW2..GW10.json.gz (ce que le moteur croyait
    AVANT chaque deadline) ;
  - tests/fixtures/resultats-GW2-GW10.csv.gz (minutes et points officiels, relevés
    sur l'API publique /event/{gw}/live/ pour les joueurs des fichiers figés).

Ce que ces tests protègent :
  1. le défaut corrigé était réel (tranche 60-80 % trop prudente 9 GW sur 9) ;
  2. les constantes livrées sont celles que les données donnent ;
  3. HORS ÉCHANTILLON (une GW laissée de côté à la fois), la correction
     améliore P(60+) et P(jouer) chaque semaine, recale la tranche 60-80 %, et
     réduit l'erreur quadratique sur les POINTS ;
  4. les incertains et les indisponibles ne sont pas touchés ; l'ordre des
     joueurs sur la probabilité est conservé.

GW2 et GW3 ont été figées avec P60_GIVEN_START = 0.88 (avant A9). Elles sont
rejouées sous 0.954 : p60 est strictement proportionnel à la constante
(voir test_priors::test_p60_reste_proportionnel_a_la_constante), donc le
rejeu est exact.
"""

import csv
import gzip
import io
import json
import math
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from fpl_advisor.evaluation import calibration                 # noqa: E402
from fpl_advisor.forecasting import minutes, priors            # noqa: E402

GWS = range(2, 11)
REJEU = {2: 0.954 / 0.88, 3: 0.954 / 0.88}     # GW figées avant A9


def _resultats():
    with gzip.open(RACINE / "tests" / "fixtures" / "resultats-GW2-GW10.csv.gz", "rt") as f:
        return {(int(r["gw"]), int(r["player_id"])): (int(r["minutes"]), int(r["total_points"]))
                for r in csv.DictReader(f)}


def _composantes(c, pos, p60o, ppo, p60n, ppn):
    """Composantes de points sous d'autres minutes. Chaque composante du
    moteur (projection.project_player) est linéaire en p60, p_cameo, xmin ou
    p_play pour une GW à un match : le recalcul est exact, sauf le malus des
    GB/DEF (mixte) traité au prorata de p60."""
    xo = 90 * p60o + 25 * max(0, ppo - p60o)
    xn = 90 * p60n + 25 * max(0, ppn - p60n)
    sh = xn / xo if xo > 0 else 0
    s60 = p60n / p60o if p60o > 0 else 0
    spp = ppn / ppo if ppo > 0 else 0
    return {"appearance": 2 * p60n + max(0, ppn - p60n),
            "goals": c["goals"] * sh, "assists": c["assists"] * sh,
            "saves": c["saves"] * sh, "bonus": c["bonus"] * sh,
            "cs": c["cs"] * s60, "defcon": c["defcon"] * spp,
            "malus": c["malus"] * (s60 if pos in (1, 2) else sh)}


def _jeu():
    if hasattr(_jeu, "cache"):
        return _jeu.cache
    obs = _resultats()
    out = []
    for gw in GWS:
        with gzip.open(RACINE / "projections-figees" / f"projections-GW{gw}.json.gz") as f:
            d = json.load(f)
        for r in d["rows"]:
            if r["gw"] != gw or not r["n_fixtures"] or (gw, r["player_id"]) not in obs:
                continue
            p = d["players"][str(r["player_id"])]
            p60, pp, c = r["p60"], r["p_play"], dict(r["components"])
            if gw in REJEU and p60 > 0:
                p60n = p60 * REJEU[gw]
                ppn = max(pp, p60n) if pp > p60 + 1e-12 else p60n
                c = _composantes(c, p["element_type"], p60, pp, p60n, ppn)
                p60, pp = p60n, ppn
            mins, pts = obs[(gw, r["player_id"])]
            out.append({"gw": gw, "pos": p["element_type"], "dispo": p["status"] == "a",
                        "p60": p60, "pp": pp, "c": c, "ep": sum(c.values()),
                        "y60": 1.0 if mins >= 60 else 0.0, "y1": 1.0 if mins >= 1 else 0.0,
                        "pts": pts})
    _jeu.cache = out
    return out


def _sig(p, a, b):
    if p <= 0:
        return 0.0
    p = min(max(p, 1e-4), 1 - 1e-4)
    return 1 / (1 + math.exp(-(a * math.log(p / (1 - p)) + b)))


def _hors_echantillon():
    """Chaque GW corrigée par des paramètres appris SANS elle."""
    if hasattr(_hors_echantillon, "cache"):
        return _hors_echantillon.cache
    rows = _jeu()
    for gw in GWS:
        app = [r for r in rows if r["gw"] != gw and r["dispo"]]
        a6, b6 = calibration.fit_recalibration([(r["p60"], r["y60"]) for r in app])
        a1, b1 = calibration.fit_recalibration([(r["pp"], r["y1"]) for r in app])
        for r in rows:
            if r["gw"] != gw:
                continue
            if r["dispo"]:
                r["p60c"] = _sig(r["p60"], a6, b6)
                r["ppc"] = max(_sig(r["pp"], a1, b1), r["p60c"])
            else:
                r["p60c"], r["ppc"] = r["p60"], r["pp"]
            r["epc"] = sum(_composantes(r["c"], r["pos"], r["p60"], r["pp"],
                                        r["p60c"], r["ppc"]).values())
    _hors_echantillon.cache = rows
    return rows


def _brier(rows, p, y):
    return sum((r[p] - r[y]) ** 2 for r in rows) / len(rows)


def _tranche(rows, p, y, lo=0.6, hi=0.8):
    s = [r for r in rows if lo <= r[p] < hi]
    return sum(r[p] for r in s) / len(s), sum(r[y] for r in s) / len(s), len(s)


class LeDefautEtaitReelTests(unittest.TestCase):

    def test_echantillon_complet(self):
        self.assertEqual(len(_jeu()), 5043)

    def test_la_tranche_60_80_etait_trop_prudente_chaque_semaine(self):
        rows = _jeu()
        annonce, observe, n = _tranche(rows, "p60", "y60")
        self.assertGreater(n, 700)
        self.assertGreater(observe - annonce, 0.08, "le défaut cumulé dépassait 10 points")
        for gw in GWS:
            a, o, _ = _tranche([r for r in rows if r["gw"] == gw], "p60", "y60")
            self.assertGreater(o, a, f"GW{gw} : le défaut devait apparaître chaque semaine")


class ConstantesLivreesTests(unittest.TestCase):

    def test_les_constantes_sont_celles_des_donnees(self):
        dispo = [r for r in _jeu() if r["dispo"]]
        for cle, champ, y in (("p60", "p60", "y60"), ("p_play", "pp", "y1")):
            a, b = calibration.fit_recalibration([(r[champ], r[y]) for r in dispo])
            a0, b0 = priors.MINUTES_RECALIBRATION[cle]
            self.assertAlmostEqual(a, a0, delta=0.01, msg=cle)
            self.assertAlmostEqual(b, b0, delta=0.01, msg=cle)

    def test_l_etirement_est_reel(self):
        # a > 1 : le moteur brut écrasait les probabilités vers le milieu.
        for a, _ in priors.MINUTES_RECALIBRATION.values():
            self.assertGreater(a, 1.15)


class HorsEchantillonTests(unittest.TestCase):

    def test_le_recalcul_des_points_redonne_l_ep_fige(self):
        for r in _jeu()[:500]:
            ep = sum(_composantes(r["c"], r["pos"], r["p60"], r["pp"], r["p60"], r["pp"]).values())
            self.assertAlmostEqual(ep, r["ep"], places=9)

    def test_brier_meilleur_chaque_semaine(self):
        rows = _hors_echantillon()
        for gw in GWS:
            s = [r for r in rows if r["gw"] == gw]
            self.assertLess(_brier(s, "p60c", "y60"), _brier(s, "p60", "y60"), f"P(60+) GW{gw}")
            self.assertLess(_brier(s, "ppc", "y1"), _brier(s, "pp", "y1"), f"P(jouer) GW{gw}")

    def test_la_tranche_60_80_est_recalee(self):
        annonce, observe, _ = _tranche(_hors_echantillon(), "p60c", "y60")
        self.assertLess(abs(observe - annonce), 0.04)

    def test_les_points_s_ameliorent(self):
        """Juge : erreur QUADRATIQUE. `ep` est une espérance ; l'erreur absolue
        récompense la médiane (1 à 2 points) et pénaliserait à tort toute
        correction qui rapproche l'espérance de la moyenne réelle."""
        rows = _hors_echantillon()
        mse = lambda s, k: sum((r[k] - r["pts"]) ** 2 for r in s) / len(s)  # noqa: E731
        self.assertLess(mse(rows, "epc"), mse(rows, "ep"))
        semaines = sum(mse([r for r in rows if r["gw"] == g], "epc")
                       < mse([r for r in rows if r["gw"] == g], "ep") for g in GWS)
        self.assertGreaterEqual(semaines, 7, "amélioration sur au moins 7 GW sur 9")

    def test_les_incertains_ne_sont_pas_touches(self):
        for r in _hors_echantillon():
            if not r["dispo"]:
                self.assertEqual((r["p60c"], r["ppc"]), (r["p60"], r["pp"]))


class MoteurTests(unittest.TestCase):

    def _joueur(self, status="a", chance=None):
        return {"id": 1, "element_type": 3, "status": status,
                "chance_of_playing_next_round": chance}

    def test_le_moteur_applique_la_correction_aux_disponibles(self):
        m = minutes.minutes_model(self._joueur(), [{"minutes": 90, "started": True}] * 4)
        self.assertAlmostEqual(m["p60"], priors.recalibrate(m["p60_brut"], "p60"), places=12)
        self.assertGreater(m["p60"], m["p60_brut"])
        self.assertGreaterEqual(m["p_play"], m["p60"])
        self.assertLess(m["p60"], 1.0)

    def test_le_moteur_laisse_les_incertains_bruts(self):
        m = minutes.minutes_model(self._joueur("d", 75), [{"minutes": 90, "started": True}] * 4)
        self.assertEqual((m["p60"], m["p_play"]), (m["p60_brut"], m["p_play_brut"]))

    def test_un_indisponible_reste_a_zero(self):
        m = minutes.minutes_model(self._joueur("i", 0), [{"minutes": 90, "started": True}] * 4)
        self.assertEqual((m["p60"], m["p_play"]), (0.0, 0.0))

    def test_monotone(self):
        grille = [i / 100 for i in range(0, 101)]
        for cle in ("p60", "p_play"):
            v = [priors.recalibrate(p, cle) for p in grille]
            self.assertEqual(v, sorted(v))
            self.assertLess(max(v), 1.0)


if __name__ == "__main__":
    unittest.main()
