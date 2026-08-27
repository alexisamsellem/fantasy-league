# -*- coding: utf-8 -*-
"""Tests du multi-ligue — hors ligne, aucune requête.

Ce que ces tests protègent :
  1. la config accepte une ou plusieurs ligues, et refuse les identifiants du
     gabarit dans les deux formes ;
  2. les ligues ne se moyennent JAMAIS : chacune garde son classement, sa
     posture et son exposition ;
  3. les désaccords entre ligues sont nommés, pas fondus dans un chiffre ;
  4. la vue « une seule ligue » d'avant continue de rendre exactement la
     première ligue configurée.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import rivals                                    # noqa: E402
from fpl_advisor.api import load_config                           # noqa: E402


def _cfg(contenu):
    d = tempfile.mkdtemp()
    f = Path(d) / "config.local.json"
    f.write_text(json.dumps(contenu), encoding="utf-8")
    return str(f)


def _picks(ids, capitaine=None):
    return {"picks": [{"element": i, "is_captain": i == capitaine} for i in ids]}


def _ligue(lid, nom, membres, moi=1):
    """membres : {entry_id: (total, [element_ids], capitaine)}."""
    rows = [{"entry": e, "entry_name": f"E{e}", "player_name": f"P{e}",
             "total": v[0], "rank": i + 1}
            for i, (e, v) in enumerate(sorted(membres.items(),
                                              key=lambda kv: -kv[1][0]))]
    riv = {e: {"row": next(r for r in rows if r["entry"] == e),
               "picks": _picks(v[1], v[2]), "history": {"chips": []}}
           for e, v in membres.items() if e != moi}
    return {"id": lid, "name": nom, "standings": rows, "rivals": riv}


def _parsed(leagues, moi=1, mes_ids=(10, 11)):
    elements = [{"id": i, "web_name": f"J{i}"} for i in range(10, 20)]
    return {"bootstrap": {"elements": elements}, "team_id": moi,
            "last_closed_gw": 1, "leagues": leagues,
            "my": {"picks": _picks(list(mes_ids))},
            "standings": leagues[0]["standings"], "rivals": leagues[0]["rivals"],
            "league_id": leagues[0]["id"],
            "league_ids": [l["id"] for l in leagues]}


class ConfigTests(unittest.TestCase):
    def test_une_seule_ligue_reste_acceptee(self):
        cfg = load_config(_cfg({"team_id": 7, "league_id": 42}))
        self.assertEqual(cfg["league_ids"], [42])
        self.assertEqual(cfg["league_id"], 42)

    def test_plusieurs_ligues(self):
        cfg = load_config(_cfg({"team_id": 7, "league_ids": [42, 43]}))
        self.assertEqual(cfg["league_ids"], [42, 43])
        self.assertEqual(cfg["league_id"], 42, "la première est la référence")

    def test_les_doublons_ne_sont_pas_collectes_deux_fois(self):
        cfg = load_config(_cfg({"team_id": 7, "league_ids": [42, 43, 42]}))
        self.assertEqual(cfg["league_ids"], [42, 43])

    def test_le_gabarit_a_zero_est_refuse_dans_les_deux_formes(self):
        with self.assertRaises(SystemExit):
            load_config(_cfg({"team_id": 7, "league_id": 0}))
        with self.assertRaises(SystemExit):
            load_config(_cfg({"team_id": 7, "league_ids": [42, 0]}))

    def test_une_liste_vide_est_refusee(self):
        with self.assertRaises(SystemExit):
            load_config(_cfg({"team_id": 7, "league_ids": []}))


class VuesParLigueTests(unittest.TestCase):
    def setUp(self):
        # Ligue A : je suis 2ᵉ sur 3, à 5 pts. Ligue B : 3ᵉ sur 3, à 40 pts.
        a = _ligue(1, "A", {1: (60, [10, 11], None), 2: (65, [10, 12], 10),
                            3: (50, [10, 13], None)})
        b = _ligue(2, "B", {1: (60, [10, 11], None), 4: (100, [14, 15], 14),
                            5: (90, [15, 16], 15)})
        self.parsed = _parsed([a, b])
        self.vues = rivals.league_views(self.parsed)

    def test_une_vue_par_ligue_dans_l_ordre_de_la_config(self):
        self.assertEqual([v["id"] for v in self.vues], [1, 2])
        self.assertEqual([v["name"] for v in self.vues], ["A", "B"])

    def test_chaque_ligue_garde_son_propre_classement(self):
        a, b = self.vues
        self.assertEqual(a["standings"]["gap_to_leader"], 5)
        self.assertEqual(b["standings"]["gap_to_leader"], 40)

    def test_la_posture_depend_de_l_ecart_pas_d_une_moyenne(self):
        a, b = self.vues
        self.assertIn("chasseur proche", a["posture"])
        self.assertIn("en retard", b["posture"])

    def test_un_peloton_compact_n_est_pas_le_meme_retard(self):
        """Être loin du leader et à un point du voisin n'appelle pas la même
        conduite qu'être loin des deux. L'écart au leader seul l'effaçait."""
        loin = _ligue(1, "loin", {1: (60, [10], None), 2: (100, [11], None),
                                  3: (80, [12], None)})
        colle = _ligue(2, "collé", {1: (60, [10], None), 2: (100, [11], None),
                                    3: (61, [12], None)})
        a, b = rivals.league_views(_parsed([loin, colle]))
        self.assertIn("en retard", a["posture"])
        self.assertNotIn("compact", a["posture"])
        self.assertIn("compact", b["posture"])
        self.assertEqual(a["standings"]["gap_to_leader"],
                         b["standings"]["gap_to_leader"])

    def test_l_exposition_est_calculee_ligue_par_ligue(self):
        a, b = self.vues
        eo_a = {r["name"]: r["eo_local"] for r in a["exposure"]}
        eo_b = {r["name"]: r["eo_local"] for r in b["exposure"]}
        # J10 : possédé par les 2 rivaux de A, dont un capitaine → 3/2.
        self.assertAlmostEqual(eo_a["J10"], 1.5)
        # J10 n'est possédé par personne dans B.
        self.assertNotIn("J10", eo_b)

    def test_les_joueurs_detenus_sont_marques_dans_chaque_ligue(self):
        for v in self.vues:
            for r in v["exposure"]:
                self.assertEqual(r["i_own"], r["name"] in ("J10", "J11"))


class ConflitsEntreLiguesTests(unittest.TestCase):
    def test_un_joueur_tres_expose_ici_et_absent_la_bas_est_signale(self):
        a = _ligue(1, "A", {1: (60, [10, 11], None), 2: (65, [10, 12], None)})
        b = _ligue(2, "B", {1: (60, [10, 11], None), 4: (100, [14, 15], None)})
        vues = rivals.league_views(_parsed([a, b]))
        conflits = {c["name"]: c for c in rivals.exposure_conflicts(vues)}
        self.assertIn("J10", conflits, "J10 : 100 % dans A, 0 % dans B")
        self.assertAlmostEqual(conflits["J10"]["eo"][0], 1.0)
        self.assertAlmostEqual(conflits["J10"]["eo"][1], 0.0)

    def test_aucun_conflit_quand_les_ligues_possedent_pareil(self):
        a = _ligue(1, "A", {1: (60, [10, 11], None), 2: (65, [10, 12], None)})
        b = _ligue(2, "B", {1: (60, [10, 11], None), 4: (100, [10, 12], None)})
        vues = rivals.league_views(_parsed([a, b]))
        self.assertEqual(rivals.exposure_conflicts(vues), [])

    def test_une_seule_ligue_ne_produit_aucun_conflit(self):
        a = _ligue(1, "A", {1: (60, [10, 11], None), 2: (65, [10, 12], None)})
        vues = rivals.league_views(_parsed([a]))
        self.assertEqual(rivals.exposure_conflicts(vues), [])


class CompatibiliteTests(unittest.TestCase):
    def test_les_vues_historiques_rendent_la_premiere_ligue(self):
        a = _ligue(1, "A", {1: (60, [10, 11], None), 2: (65, [10, 12], 10)})
        b = _ligue(2, "B", {1: (60, [10, 11], None), 4: (100, [14, 15], 14)})
        parsed = _parsed([a, b])
        expo, meta = rivals.local_exposure(parsed)
        self.assertEqual(expo, rivals.league_views(parsed)[0]["exposure"])
        self.assertEqual(meta["n_rivals"], 1)
        st = rivals.standings_summary(parsed)
        self.assertEqual(st["gap_to_leader"], 5)

    def test_un_snapshot_sans_bloc_leagues_reste_lisible(self):
        """Snapshot collecté avant le multi-ligue : `leagues` n'existe pas.
        La lecture doit retomber sur `standings`/`rivals` sans planter."""
        a = _ligue(1, "A", {1: (60, [10, 11], None), 2: (65, [10, 12], None)})
        parsed = _parsed([a])
        del parsed["leagues"]
        vues = rivals.league_views(parsed)
        self.assertEqual(len(vues), 1)
        self.assertEqual(vues[0]["standings"]["gap_to_leader"], 5)


if __name__ == "__main__":
    unittest.main()
