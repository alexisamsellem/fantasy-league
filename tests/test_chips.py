# -*- coding: utf-8 -*-
"""Tests de la vérification du timing des chips (A12) — hors ligne.

Ce que ces tests protègent :
  1. les fenêtres officielles sont lues telles quelles, jamais inventées ; un
     chip joué dans une fenêtre ne compte pas pour l'autre ;
  2. la contrainte « un chip par GW » : marge, urgence, et une seule consigne
     « jouer » par GW ;
  3. les consignes suivent ce qui a été mesuré : banc renforcé sur l'EP du
     banc, triple capitaine seulement sur double match ;
  4. la prémisse du triple capitaine, sur données publiques : l'EP ne classe
     pas les candidats capitaines. Si un futur moteur y parvient, ce test
     échoue et la règle doit être revue.
"""

import csv
import gzip
import json
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

    def test_triple_capitaine_sans_double_match_est_libre(self):
        d = chips.disponibles(OFFICIELS, [], 11)
        tc = next(c for c in chips.verifier(d, _sig([6, 9, 7]))["chips"] if c["name"] == "3xc")
        self.assertEqual(tc["consigne"], "LIBRE")
        self.assertIn("ne prédit pas", tc["raison"])

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


class PremisseTripleCapitaineTests(unittest.TestCase):
    """Données publiques : projections figées GW2-GW10 et points officiels."""

    def test_l_ep_ne_classe_pas_les_candidats_capitaines(self):
        with gzip.open(RACINE / "tests" / "fixtures" / "resultats-GW2-GW10.csv.gz", "rt") as f:
            pts = {(int(r["gw"]), int(r["player_id"])): int(r["total_points"])
                   for r in csv.DictReader(f)}
        paires = []
        for gw in range(2, 11):
            with gzip.open(RACINE / "projections-figees" / f"projections-GW{gw}.json.gz") as f:
                d = json.load(f)
            paires += [(r["ep"], pts[(gw, r["player_id"])]) for r in d["rows"]
                       if r["gw"] == gw and r["ep"] >= 4.5 and (gw, r["player_id"]) in pts]
        self.assertGreater(len(paires), 40)

        def rangs(v):
            o = sorted(range(len(v)), key=lambda i: v[i])
            r = [0.0] * len(v)
            i = 0
            while i < len(o):
                j = i
                while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                    j += 1
                for k in range(i, j + 1):
                    r[o[k]] = (i + j) / 2
                i = j + 1
            return r
        x, y = rangs([a for a, _ in paires]), rangs([b for _, b in paires])
        n = len(x)
        mx, my = sum(x) / n, sum(y) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
        rho = cov / (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
        self.assertLess(rho, 0.2, "l'EP classe désormais les capitaines : revoir A12")


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
