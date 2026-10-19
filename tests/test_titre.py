# -*- coding: utf-8 -*-
"""P(finir 1er) par mini-ligue — hors ligne, sur la démo synthétique.

Ce que ces tests protègent :
  1. le modèle résiduel retrouve le bruit d'une ligue simulée et ne prête pas
     de talent là où il n'y en a pas ;
  2. nombres aléatoires communs : deux options identiques ont un ΔP nul, au
     tirage près ;
  3. un leader très loin devant a P(1er) ≈ 1, un dernier très loin derrière ≈ 0 ;
  4. les ligues sont calculées séparément, jamais moyennées ;
  5. le désaccord P(1er)/EP est exposé avec son erreur de simulation.
"""

import random
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from fpl_advisor import titre, weekly                            # noqa: E402
from fpl_advisor.demo import build_parsed                        # noqa: E402


def _histoires(n_managers, n_gw, sigma, talents, seed=4):
    rng = random.Random(seed)
    out = {}
    for m in range(n_managers):
        cur = [{"event": g, "points": 50 + talents[m] + rng.gauss(0, sigma),
                "event_transfers_cost": 0} for g in range(1, n_gw + 1)]
        out[m + 1] = {"current": cur}
    return out


class ModeleResiduelTests(unittest.TestCase):
    def test_bruit_retrouve_et_talent_nul_retreci(self):
        h = _histoires(15, 20, 12.0, [0.0] * 15)
        mod = titre.modele_residuel(h, list(range(1, 21)))
        self.assertAlmostEqual(mod["sigma"], 12.0, delta=1.0)
        self.assertLess(mod["k"], 0.35)

    def test_vrai_talent_garde(self):
        talents = [(-1) ** m * 8.0 for m in range(15)]
        h = _histoires(15, 20, 6.0, talents)
        mod = titre.modele_residuel(h, list(range(1, 21)))
        self.assertGreater(mod["k"], 0.8)
        self.assertGreater(mod["a"][1], 5.0)

    def test_controle_de_dispersion(self):
        h = _histoires(15, 10, 10.0, [0.0] * 15)
        ctl = titre.controle_residuel(h, list(range(1, 11)))
        self.assertAlmostEqual(ctl["sd_z"], 1.0, delta=0.2)


class PPremierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsed = build_parsed()
        cls.contract = weekly.build_contract(cls.parsed)
        cls.squad, cls.bank = weekly.read_squad(cls.parsed)
        cls.options = titre.options_semaine(cls.contract, cls.squad, cls.bank)

    def _ligue(self, totals, lid=1):
        p = self.parsed
        std = [dict(r, total=t) for r, t in zip(p["standings"], totals)]
        return {"id": lid, "name": f"L{lid}", "standings": std,
                "rivals": {rid: dict(r) for rid, r in p["rivals"].items()}}

    def _calc(self, ligues, options=None, n=600):
        return titre.p_premier(self.contract, ligues, self.parsed["team_id"],
                               options or self.options, {}, [], n=n)

    def test_options_contiennent_conserver(self):
        self.assertTrue(any(o["echange"] is None for o in self.options))
        self.assertTrue(all(o["plan"][self.contract.gw]["cap"] == o["capitaine"]
                            for o in self.options))

    def test_options_identiques_delta_nul(self):
        o = self.options[0]
        v = self._calc([self._ligue([142, 131, 120, 99])], options=[o, dict(o)])[0]
        self.assertTrue(all(abs(r["dp1"]) < 1e-12 for r in v["options"]))

    def test_leader_tres_loin_devant(self):
        v = self._calc([self._ligue([100, 900, 90, 80])])[0]
        self.assertGreater(v["p1_reference"], 0.99)
        v = self._calc([self._ligue([900, 100, 880, 870])])[0]
        self.assertLess(v["p1_reference"], 0.01)
        self.assertFalse(v["resolu"])          # trop peu de titres simulés

    def test_ligues_separees(self):
        vues = self._calc([self._ligue([142, 131, 120, 99], 1),
                           self._ligue([300, 131, 120, 99], 2)])
        self.assertEqual([v["id"] for v in vues], [1, 2])
        self.assertGreater(vues[0]["p1_reference"], vues[1]["p1_reference"])

    def test_desaccord_expose_avec_son_erreur(self):
        v = self._calc([self._ligue([142, 131, 120, 99])])[0]
        d = v["desaccord"]
        for cle in ("meme_tete", "tete_p1", "tete_ep", "ecart_p1_tetes",
                    "se_ecart", "discernable", "spearman"):
            self.assertIn(cle, d)
        self.assertEqual(sorted(r["rang_p1"] for r in v["options"]),
                         list(range(1, len(v["options"]) + 1)))

    def test_un_bonus_sur_augmente_p1(self):
        o = self.options[0]
        bonus = dict(o, cout=-30)            # +30 pts garantis
        v = self._calc([self._ligue([142, 131, 120, 99])], options=[o, bonus])[0]
        gain = next(r for r in v["options"] if not r["reference"])
        self.assertGreater(gain["dp1"], 0.05)


if __name__ == "__main__":
    unittest.main()
