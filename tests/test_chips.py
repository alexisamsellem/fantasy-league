# -*- coding: utf-8 -*-
"""Tests de la vérification du timing des chips (A12) — hors ligne.

Ce que ces tests protègent :
  1. les fenêtres officielles sont lues telles quelles, jamais inventées ; un
     chip joué dans une fenêtre ne compte pas pour l'autre ;
  2. la contrainte « un chip par GW » : marge, urgence, et une seule consigne
     « jouer » par GW ;
  3. les consignes suivent ce qui a été mesuré : même règle (faible) pour le
     banc et le capitaine, priorité au double match, horizon coupé à la fin
     de fenêtre, chips perdus annoncés quand la marge est négative.
"""

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from fpl_advisor import chips                                     # noqa: E402

OFFICIELS = [
    {"name": "wildcard", "start_event": 2, "stop_event": 19},
    {"name": "freehit", "start_event": 2, "stop_event": 19},
    {"name": "bboost", "start_event": 1, "stop_event": 19},
    {"name": "3xc", "start_event": 1, "stop_event": 19},
    {"name": "wildcard", "start_event": 20, "stop_event": 38},
    {"name": "freehit", "start_event": 20, "stop_event": 38},
    {"name": "bboost", "start_event": 20, "stop_event": 38},
    {"name": "3xc", "start_event": 20, "stop_event": 38},
]


def _sig(banc, cap_matchs=(1, 1, 1), gw=11):
    return [{"gw": gw + i, "capitaine": "X", "ep_capitaine": 6.0,
             "matchs_capitaine": cap_matchs[i], "ep_banc": b}
            for i, b in enumerate(banc)]


class FenetresTests(unittest.TestCase):

    def test_quatre_chips_avant_la_gw19(self):
        d = chips.disponibles(OFFICIELS, [], 11)
        self.assertEqual({c["name"] for c in d}, {"wildcard", "freehit", "bboost", "3xc"})
        self.assertTrue(all(c["fin"] == 19 and c["gw_restantes"] == 9 for c in d))

    def test_un_chip_joue_dans_la_fenetre_n_est_plus_disponible(self):
        d = chips.disponibles(OFFICIELS, [{"name": "3xc", "event": 3}], 11)
        self.assertNotIn("3xc", {c["name"] for c in d})

    def test_un_chip_joue_avant_ne_compte_pas_pour_la_seconde_moitie(self):
        d = chips.disponibles(OFFICIELS, [{"name": "3xc", "event": 3}], 20)
        self.assertIn("3xc", {c["name"] for c in d})

    def test_fenetres_absentes_jamais_inventees(self):
        self.assertIsNone(chips.disponibles([], [], 11))
        self.assertEqual(chips.verifier(None, None)["etat"], "inconnu")


class ConsignesTests(unittest.TestCase):

    def test_marge_et_urgence(self):
        d = chips.disponibles(OFFICIELS, [], 16)          # 4 chips, 4 GW
        v = chips.verifier(d, _sig([5, 6, 7], gw=16))
        self.assertEqual(v["marge"], 0)
        self.assertTrue(v["urgent"])
        self.assertEqual(sum(c["consigne"] == "JOUER CETTE GW" for c in v["chips"]), 1)

    def test_banc_renforce_suit_l_ep_du_banc(self):
        d = chips.disponibles(OFFICIELS, [], 11)
        jouer = chips.verifier(d, _sig([9.0, 7.0, 6.0]))
        attendre = chips.verifier(d, _sig([6.0, 9.0, 7.0]))
        bb = lambda v: next(c for c in v["chips"] if c["name"] == "bboost")  # noqa: E731
        self.assertEqual(bb(jouer)["consigne"], "JOUER CETTE GW")
        self.assertEqual(bb(attendre)["consigne"], "ATTENDRE")
        self.assertIn("GW12", bb(attendre)["raison"])

    def test_triple_capitaine_suit_la_meme_regle_que_le_banc(self):
        # Revue A12 : hors GW2, les deux signaux valent ≈ +2 pts ; aucune
        # raison de traiter le capitaine autrement que le banc.
        d = chips.disponibles(OFFICIELS, [], 11)
        sig = _sig([6, 9, 7])
        sig[0]["ep_capitaine"], sig[1]["ep_capitaine"], sig[2]["ep_capitaine"] = 7.0, 6.0, 5.0
        v = chips.verifier(d, sig)
        tc = next(c for c in v["chips"] if c["name"] == "3xc")
        self.assertEqual(tc["consigne"], "JOUER CETTE GW")
        self.assertIn("signal faible", tc["raison"])

    def test_triple_capitaine_sur_double_match(self):
        d = chips.disponibles(OFFICIELS, [], 11)
        v = chips.verifier(d, _sig([9, 7, 6], cap_matchs=(2, 1, 1)))
        tc = next(c for c in v["chips"] if c["name"] == "3xc")
        bb = next(c for c in v["chips"] if c["name"] == "bboost")
        self.assertEqual(tc["consigne"], "JOUER CETTE GW")
        self.assertEqual(bb["consigne"], "PAS CETTE GW")       # un seul chip par GW
        v = chips.verifier(d, _sig([6, 9, 7], cap_matchs=(1, 2, 1)))
        tc = next(c for c in v["chips"] if c["name"] == "3xc")
        self.assertEqual(tc["consigne"], "ATTENDRE")

    def test_l_horizon_s_arrete_a_la_fin_de_fenetre(self):
        # GW18, banc renforcé seul : la GW20 est hors fenêtre et ne compte pas.
        d = chips.disponibles(OFFICIELS, [{"name": n, "event": 5} for n in
                                          ("wildcard", "freehit", "3xc")], 18)
        v = chips.verifier(d, _sig([6.0, 7.0, 9.0], gw=18))
        bb = next(c for c in v["chips"] if c["name"] == "bboost")
        self.assertEqual(bb["consigne"], "ATTENDRE")
        self.assertIn("GW19", bb["raison"])
        self.assertNotIn("GW20", bb["raison"])

    def test_double_match_apres_expiration_ignore(self):
        d = chips.disponibles(OFFICIELS, [{"name": n, "event": 5} for n in
                                          ("wildcard", "freehit", "bboost")], 19)
        v = chips.verifier(d, _sig([6, 7, 9], cap_matchs=(1, 2, 1), gw=19))
        tc = next(c for c in v["chips"] if c["name"] == "3xc")
        self.assertEqual(tc["consigne"], "JOUER CETTE GW")     # dernière GW, pas d'attente

    def test_marge_negative_annonce_des_chips_perdus(self):
        d = chips.disponibles(OFFICIELS, [], 19)                # 4 chips, 1 GW
        v = chips.verifier(d, _sig([6], gw=19))
        etats = [c["consigne"] for c in v["chips"]]
        self.assertEqual(etats.count("JOUER CETTE GW"), 1)
        self.assertEqual(etats.count("PERDU"), 3)

    def test_un_joueur_absent_n_efface_pas_les_signaux(self):
        rows = [{"id": i, "web_name": f"J{i}", "element_type": t, "team": i,
                 "now_cost": 50, "p_play": 0.9, "p60": 0.8, "p0": 0.1,
                 "eps": {11: float(i), 12: 1.0}}
                for i, t in enumerate([1, 1] + [2] * 5 + [3] * 5 + [4] * 3, start=1)]
        sig = chips.signaux(rows, [r["id"] for r in rows] + [999], [11, 12],
                            {(15, 11): 2})
        self.assertIsNotNone(sig)
        self.assertEqual(sig[0]["matchs_capitaine"], 2)


class RapportTests(unittest.TestCase):

    def test_la_section_chips_est_rendue(self):
        from fpl_advisor.report import _chips_lines
        d = chips.disponibles(OFFICIELS, [], 11)
        txt = "\n".join(_chips_lines(chips.verifier(d, _sig([9, 7, 6]))))
        self.assertIn("## Chips", txt)
        self.assertIn("marge de **5 semaine(s)**", txt)
        self.assertIn("banc renforcé", txt)
        self.assertIn("inconnu", "\n".join(_chips_lines({"etat": "inconnu", "raison": "x"})))


if __name__ == "__main__":
    unittest.main()
