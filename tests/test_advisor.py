# -*- coding: utf-8 -*-
"""Tests essentiels du conseiller V0 — hors ligne, aucune requête réseau."""

import sys
import unittest
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import model, team           # noqa: E402
from fpl_advisor.advise import build_recommendation   # noqa: E402
from fpl_advisor.demo import build_parsed     # noqa: E402
from fpl_advisor.report import render         # noqa: E402
from fpl_advisor.rivals import local_exposure  # noqa: E402


def _squad(eps):
    """15 joueurs synthétiques : 2 GB, 5 DEF, 5 MIL, 3 ATT avec les EP donnés."""
    types = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    return [{"id": i + 1, "element_type": t, "ep": eps[i], "p_play": 1.0,
             "p0": 0.0, "team": i % 6 + 1, "now_cost": 50,
             "web_name": f"J{i+1}"}
            for i, (t, _) in enumerate(zip(types, eps))]


class XiTests(unittest.TestCase):
    def _brute_force(self, squad):
        best, score = None, -1
        for combo in combinations(squad, 11):
            gk = sum(1 for p in combo if p["element_type"] == 1)
            d = sum(1 for p in combo if p["element_type"] == 2)
            m = sum(1 for p in combo if p["element_type"] == 3)
            f = sum(1 for p in combo if p["element_type"] == 4)
            if gk != 1 or not (3 <= d <= 5) or not (2 <= m <= 5) or not (1 <= f <= 3):
                continue
            s = sum(p["ep"] for p in combo)
            if s > score:
                best, score = combo, s
        return score

    def test_xi_respecte_les_contraintes_et_atteint_l_optimum(self):
        eps = [4.0, 1.0, 5.0, 4.5, 4.0, 3.5, 1.0, 6.0, 5.5, 5.0, 2.0, 1.5, 6.5, 3.0, 1.0]
        squad = _squad(eps)
        xi, bench = team.pick_xi(squad)
        self.assertEqual(len(xi), 11)
        self.assertEqual(len(bench), 4)
        self.assertEqual(sum(1 for p in xi if p["element_type"] == 1), 1)
        self.assertGreaterEqual(sum(1 for p in xi if p["element_type"] == 2), 3)
        self.assertGreaterEqual(sum(1 for p in xi if p["element_type"] == 4), 1)
        self.assertAlmostEqual(sum(p["ep"] for p in xi), self._brute_force(squad), places=6)

    def test_banc_gardien_en_premier(self):
        xi, bench = team.pick_xi(_squad([4, 1, 5, 4, 4, 3, 1, 6, 5, 5, 2, 1, 6, 3, 1]))
        self.assertEqual(bench[0]["element_type"], 1)


class ArmbandTests(unittest.TestCase):
    def test_formule_du_brassard(self):
        xi = [{"id": 1, "ep": 6.0, "p0": 0.30, "web_name": "A", "element_type": 4},
              {"id": 2, "ep": 5.5, "p0": 0.05, "web_name": "B", "element_type": 3},
              {"id": 3, "ep": 4.0, "p0": 0.0, "web_name": "C", "element_type": 2}]
        band = team.armband(xi)
        # A+B : 6.0 + 0.30×5.5 = 7.65 ; B+A : 5.5 + 0.05×6.0 = 5.80 → A capitaine
        self.assertEqual(band["captain"]["id"], 1)
        self.assertEqual(band["vice"]["id"], 2)
        self.assertAlmostEqual(band["ev"], 7.65, places=6)


class MinutesTests(unittest.TestCase):
    def test_blesse_sans_chance_ne_joue_pas(self):
        p = {"status": "i", "chance_of_playing_next_round": None,
             "team": 1, "element_type": 2, "now_cost": 50}
        m = model.minutes_model(p, [90, 90], [p])
        self.assertEqual(m["p_play"], 0.0)

    def test_historique_pondere_recent_d_abord(self):
        p = {"id": 1, "status": "a", "chance_of_playing_next_round": None,
             "team": 1, "element_type": 3, "now_cost": 80}
        # Le poids de récence doit ORDONNER les estimations : 90 min récents
        # puis des zéros anciens valent mieux que l'inverse. La valeur absolue,
        # elle, est volontairement rétrécie (plus de certitude à 5 GW).
        recent = model.minutes_model(p, [90, 90, 0, 0, 0])
        ancien = model.minutes_model(p, [0, 0, 0, 90, 90])
        self.assertGreater(recent["p60"], ancien["p60"])
        self.assertIn("historique 5 GW", recent["basis"])
        for m in (recent, ancien):        # jamais de certitude fabriquée
            self.assertGreater(m["p_play"], 0.0)
            self.assertLess(m["p_play"], 1.0)


class TransferTests(unittest.TestCase):
    def _setup(self, delta):
        out = {"id": 1, "element_type": 4, "team": 1, "now_cost": 60, "web_name": "OUT"}
        inn = {"id": 2, "element_type": 4, "team": 2, "now_cost": 60, "web_name": "IN"}
        squad = [out]
        eps = {1: {3: 2.0, 4: 2.0, 5: 2.0}, 2: {g: 2.0 + delta / 3 for g in (3, 4, 5)}}
        return team.transfer_scan(squad, [inn], eps, bank=0)

    def test_au_dessus_du_seuil_transferer(self):
        self.assertEqual(self._setup(3.0)["decision"], "transférer")

    def test_sous_le_seuil_conserver(self):
        self.assertEqual(self._setup(1.0)["decision"], "conserver")


class TransfertSurLeXiTests(unittest.TestCase):
    """Le gain d'un transfert se mesure sur le meilleur XI, pas sur les points
    du joueur vendu.

    Sortir un remplaçant qui ne joue pas ne rend pas ses points « manquants » :
    il n'en rapportait aucun. Comparer les points individuels surestime donc
    tout échange dont le sortant est sur le banc — et peut recommander un
    transfert qui n'ajoute presque rien au onze."""

    EPS = {1: [2.5, 0.2], 2: [2.6, 2.4, 2.2, 2.0, 0.1],
           3: [3.0, 2.9, 2.8, 2.7, 2.6], 4: [3.2, 3.1, 3.0]}
    GWS = (1, 2, 3)

    def _squad(self):
        rows, pid = [], 0
        for et, eps in self.EPS.items():
            for i, ep in enumerate(eps):
                pid += 1
                rows.append({"id": pid, "element_type": et, "ep": ep,
                             "p_play": 1.0, "p0": 0.0, "team": pid % 6 + 1,
                             "now_cost": 50, "web_name": f"J{pid}", "_ep": ep})
        return rows

    def _scan(self, ep_entrant):
        squad = self._squad()
        faible = min(squad, key=lambda r: r["_ep"])       # le DEF à 0.1, sur le banc
        self.assertEqual(faible["element_type"], 2)
        entrant = {"id": 99, "element_type": 2, "ep": ep_entrant, "p_play": 1.0,
                   "p0": 0.0, "team": 6, "now_cost": 50, "web_name": "IN",
                   "_ep": ep_entrant}
        eps = {r["id"]: {g: r["_ep"] for g in self.GWS} for r in squad + [entrant]}
        scan = team.transfer_scan(squad, [entrant], eps, bank=0)
        cnd = next(c for c in scan["candidates"] if c["out"]["id"] == faible["id"])
        return scan, cnd

    def test_le_gain_xi_est_bien_inferieur_a_l_ecart_individuel(self):
        scan, cnd = self._scan(3.0)
        self.assertTrue(scan["xi_based"])
        # Individuel : (3.0 − 0.1) × 3 GW = 8.7. Sur le XI, l'entrant ne
        # déplace que le 3e défenseur (2.4 → 2.6+2.5+... ) : +0.8 par GW.
        self.assertAlmostEqual(cnd["delta3_brut"], 8.7, places=6)
        self.assertAlmostEqual(cnd["delta3"], 2.4, places=6)
        self.assertLess(cnd["delta3"], cnd["delta3_brut"] / 3)

    def test_un_echange_de_banc_ne_declenche_plus_le_transfert(self):
        """Cas décisif : l'ancienne règle recommandait de transférer (7.2 pts
        annoncés), la nouvelle voit +0.9 sur le XI et conserve."""
        scan, cnd = self._scan(2.5)
        self.assertGreater(cnd["delta3_brut"], team.TRANSFER_THRESHOLD)
        self.assertLess(cnd["delta3"], team.TRANSFER_THRESHOLD)
        self.assertEqual(scan["decision"], "conserver")

    def test_un_sortant_titulaire_donne_le_meme_gain_des_deux_facons(self):
        """Quand le sortant joue, les deux mesures coïncident : la correction
        ne déplace que les échanges de banc."""
        squad = self._squad()
        titulaire = max((r for r in squad if r["element_type"] == 2),
                        key=lambda r: r["_ep"])
        entrant = {"id": 99, "element_type": 2, "ep": 4.0, "p_play": 1.0,
                   "p0": 0.0, "team": 6, "now_cost": 50, "web_name": "IN",
                   "_ep": 4.0}
        eps = {r["id"]: {g: r["_ep"] for g in self.GWS} for r in squad + [entrant]}
        # Tous les couples, pas seulement le top 3 : l'échange le mieux noté
        # reste celui qui sort le remplaçant.
        scan = team.transfer_scan(squad, [entrant], eps, bank=0, max_candidates=99)
        cnd = next(c for c in scan["candidates"] if c["out"]["id"] == titulaire["id"])
        self.assertAlmostEqual(cnd["delta3"], cnd["delta3_brut"], places=6)

    def test_effectif_incomplet_retombe_sur_l_ecart_individuel(self):
        """Aucune formation légale possible : on le dit au lieu de rendre 0."""
        out = {"id": 1, "element_type": 4, "team": 1, "now_cost": 60,
               "web_name": "OUT", "ep": 2.0, "p_play": 1.0, "p0": 0.0}
        inn = {"id": 2, "element_type": 4, "team": 2, "now_cost": 60,
               "web_name": "IN", "ep": 5.0, "p_play": 1.0, "p0": 0.0}
        eps = {1: {3: 2.0}, 2: {3: 5.0}}
        scan = team.transfer_scan([out], [inn], eps, bank=0)
        self.assertFalse(scan["xi_based"])
        self.assertAlmostEqual(scan["candidates"][0]["delta3"], 3.0, places=6)


class ExposureTests(unittest.TestCase):
    def test_capitaine_compte_double(self):
        parsed = {
            "bootstrap": {"elements": [{"id": 7, "web_name": "X"}]},
            "last_closed_gw": 2,
            "my": {"picks": {"picks": []}},
            "rivals": {
                1: {"picks": {"picks": [{"element": 7, "is_captain": True}]}},
                2: {"picks": {"picks": [{"element": 7, "is_captain": False}]}},
            },
        }
        table, meta = local_exposure(parsed)
        self.assertEqual(meta["n_with_picks"], 2)
        self.assertAlmostEqual(table[0]["eo_local"], 1.5)  # (2 + 1) / 2


class DemoEndToEndTests(unittest.TestCase):
    def test_recommandation_complete_et_rapport(self):
        rec = build_recommendation(build_parsed())
        self.assertEqual(len(rec["xi"]), 11)
        self.assertEqual(len(rec["bench"]), 4)
        self.assertIn(rec["transfer"]["decision"], ("transférer", "conserver"))
        text = render(rec)
        for section in ("## Synthèse", "## XI recommandé", "## Banc",
                        "## Capitaine et vice", "## Transférer ou conserver",
                        "## Projections, incertitude",
                        "## Mini-ligues — exposition connue des rivaux",
                        "## Événements qui feraient changer",
                        "## Limites de la V0"):
            self.assertIn(section, text)


if __name__ == "__main__":
    unittest.main()
