# -*- coding: utf-8 -*-
"""Programme exact de transferts (PuLP + HiGHS) — hors ligne.

Ce que ces tests protègent :
  1. le plan respecte les règles FPL : quotas, 3 par club, valeur d'équipe,
     XI légal, un capitaine ;
  2. la règle des gratuits : banque plafonnée à 5, pas de hit tant qu'il
     reste un gratuit, deux gratuits = deux transferts sans hit ;
  3. l'objectif du solveur est celui que recalcule l'arbitre commun ;
  4. sur l'archive figée, le programme ne fait JAMAIS moins bien que le scan
     historique, sur le même objectif ;
  5. les gratuits en banque se reconstituent depuis l'historique public.
"""

import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

from fpl_advisor import weekly                                   # noqa: E402
from fpl_advisor.demo import build_parsed                        # noqa: E402
from fpl_advisor.optimization import milp                        # noqa: E402
from fpl_advisor.optimization import weekly as opt_weekly        # noqa: E402

SANS_SOLVEUR = not milp.disponible()


class RegleDesGratuitsTests(unittest.TestCase):
    def test_ft_suivant(self):
        self.assertEqual(milp.ft_suivant(1, 0), 2)
        self.assertEqual(milp.ft_suivant(5, 0), 5)        # plafond
        self.assertEqual(milp.ft_suivant(2, 3), 1)        # hit : rien de plus
        self.assertEqual(milp.ft_suivant(1, 1), 1)

    def test_reconstitution_depuis_l_historique(self):
        cur = [{"event": g, "event_transfers": n} for g, n in
               [(1, 0), (2, 1), (3, 1), (4, 1), (5, 0), (6, 0), (7, 0)]]
        ft, _ = weekly.free_transfers({"my": {"history": {"current": cur, "chips": []}}})
        self.assertEqual(ft, 4)
        cur[6] = {"event": 7, "event_transfers": 9}       # wildcard en GW7
        ft, _ = weekly.free_transfers({"my": {"history": {
            "current": cur, "chips": [{"name": "wildcard", "event": 7}]}}})
        self.assertEqual(ft, 4)
        ft, src = weekly.free_transfers({"my": {}})
        self.assertEqual(ft, 1)
        self.assertIn("[H]", src)


@unittest.skipIf(SANS_SOLVEUR, "PuLP + HiGHS absents")
class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsed = build_parsed()
        cls.contract = weekly.build_contract(cls.parsed)
        cls.rows = cls.contract.rows_for("central")
        cls.by_id = {r["id"]: r for r in cls.rows}
        cls.squad, cls.bank = weekly.read_squad(cls.parsed)
        cls.gws = list(cls.contract.horizon)[:3]

    def _plan(self, **kw):
        return milp.plan_transferts(self.rows, self.squad, self.bank, self.gws, **kw)

    def test_regles_fpl(self):
        pl = self._plan(free_transfers=2)
        valeur = self.bank + sum(self.by_id[p]["now_cost"] for p in self.squad)
        for g in self.gws:
            eff = pl["effectifs"][g]
            self.assertEqual(len(eff), 15)
            for et, q in milp.QUOTAS.items():
                self.assertEqual(sum(1 for p in eff if self.by_id[p]["element_type"] == et), q)
            clubs = {}
            for p in eff:
                clubs[self.by_id[p]["team"]] = clubs.get(self.by_id[p]["team"], 0) + 1
            self.assertLessEqual(max(clubs.values()), 3)
            self.assertLessEqual(sum(self.by_id[p]["now_cost"] for p in eff), valeur)
            xi = pl["xi"][g]
            self.assertEqual(len(xi), 11)
            self.assertTrue(set(xi) <= set(eff))
            self.assertIn(pl["capitaines"][g], xi)

    def test_pas_de_hit_tant_qu_il_reste_un_gratuit(self):
        pl = self._plan(free_transfers=1, ft_value=0.0)
        for g in self.gws:
            if pl["hits"][g]:
                self.assertEqual(len(pl["achats"][g]) - pl["hits"][g], pl["ft"][g])

    def test_l_objectif_est_celui_de_l_arbitre(self):
        pl = self._plan(free_transfers=1)
        v, vb = milp.evaluer(self.by_id, pl["effectifs"], self.gws, pl["hits"], pl["ft_fin"])
        self.assertAlmostEqual(v, pl["valeur"], places=6)
        self.assertAlmostEqual(vb, pl["valeur_banque"], places=6)

    def test_plus_de_gratuits_ne_coute_jamais(self):
        un = self._plan(free_transfers=1, ft_value=0.0)["valeur"]
        deux = self._plan(free_transfers=2, ft_value=0.0)["valeur"]
        self.assertGreaterEqual(deux, un - 1e-6)

    def test_decision_hebdomadaire_par_le_programme(self):
        d = opt_weekly.weekly_decision(self.rows, self.squad, self.bank, self.gws,
                                       optimiseur="milp", free_transfers=2)
        self.assertEqual(d["transfer"]["optimiseur"], "milp")
        self.assertIn("plan", d["transfer"])
        if d["decision"] == "transférer":
            self.assertEqual(len(d["apres_transfert"]["squad"]), 15)

    def test_libelle_du_scan_ne_joue_que_le_premier(self):
        tr = {"decision": "transférer", "optimiseur": "scan", "candidates": [
            {"out": {"web_name": "A"}, "in": {"web_name": "B"}},
            {"out": {"web_name": "C"}, "in": {"web_name": "D"}}]}
        self.assertEqual(opt_weekly.libelle(tr), "A → B")
        tr["optimiseur"], tr["hits"] = "milp", 1
        self.assertEqual(opt_weekly.libelle(tr), "A → B + C → D (1 hit, −4)")


@unittest.skipIf(SANS_SOLVEUR, "PuLP + HiGHS absents")
class ArchiveTests(unittest.TestCase):
    """Le programme contre le scan, sur des contrats figés réels."""

    def test_jamais_moins_bien_que_le_scan(self):
        from banc_optimiseur import TOLERANCE, archive
        res = archive(RACINE / "projections-figees", n_effectifs=2, gws={3, 6})
        self.assertEqual(len(res), 8)
        for r in res:
            self.assertGreaterEqual(r["ecart"], -TOLERANCE, r)


if __name__ == "__main__":
    unittest.main()
