# -*- coding: utf-8 -*-
"""Tests de régression de la couche de projection — hors ligne.

Chaque test vise une régression NOMMÉE, pas une propriété générale : prix
compté deux fois, certitude excessive, petit échantillon non rétréci, DEFCON
binaire, présélection dominée par la GW1, instabilité non détectée.
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import initial, model, priors           # noqa: E402
from fpl_advisor.demo import build_parsed_initial        # noqa: E402
from fpl_advisor.report import render_initial            # noqa: E402


def _parsed(elements, fixtures=None, live=None, history=None):
    """Snapshot minimal, sans aucune donnée réelle."""
    teams = [{"id": 1, "name": "Fort", "short_name": "FOR",
              "strength_attack_home": 1300, "strength_attack_away": 1300,
              "strength_defence_home": 1300, "strength_defence_away": 1300},
             {"id": 2, "name": "Faible", "short_name": "FAI",
              "strength_attack_home": 900, "strength_attack_away": 900,
              "strength_defence_home": 900, "strength_defence_away": 900}]
    return {
        "bootstrap": {"teams": teams, "elements": elements, "events": []},
        "fixtures": fixtures if fixtures is not None else [
            {"event": 1, "team_h": 1, "team_a": 2}],
        "live": live or {}, "events": [], "next_gw": 1,
        "history_past": history or {},
    }


def _player(pid=1, et=3, team=1, cost=50, **kw):
    p = {"id": pid, "web_name": f"J{pid}", "element_type": et, "team": team,
         "now_cost": cost, "status": "a", "chance_of_playing_next_round": None,
         "minutes": 0, "starts": 0, "bonus": 0, "yellow_cards": 0,
         "expected_goals_per_90": 0.0, "expected_assists_per_90": 0.0,
         "saves_per_90": 0.0}
    p.update(kw)
    return p


class PrixComptéDeuxFoisTests(unittest.TestCase):
    """Le prix ne doit plus être le prior des minutes ET des taux offensifs,
    et la force offensive du club ne doit pas être comptée deux fois."""

    def test_les_taux_offensifs_ignorent_le_prix(self):
        cher, pas_cher = _player(1, cost=130), _player(2, cost=40)
        parsed = _parsed([cher, pas_cher])
        a = model.attack_rates(parsed, cher)
        b = model.attack_rates(parsed, pas_cher)
        self.assertAlmostEqual(a[0], b[0], places=10, msg="xG/90 dépend du prix")
        self.assertAlmostEqual(a[1], b[1], places=10, msg="xA/90 dépend du prix")

    def _sensibilite_a_la_force_du_club(self, minutes):
        """Écart relatif de la composante « buts » quand SEULE la force
        offensive du club du joueur change."""
        p = _player(1, minutes=minutes, expected_goals_per_90=0.5)
        fort = _parsed([p])
        faible = copy.deepcopy(fort)
        for t in faible["bootstrap"]["teams"]:
            if t["id"] == 1:                       # club du joueur affaibli
                t["strength_attack_home"] = t["strength_attack_away"] = 700
        a = model.project_player(fort, p, 1)["components"]["goals"]
        b = model.project_player(faible, p, 1)["components"]["goals"]
        return (a - b) / a

    def test_la_force_du_club_s_eteint_quand_le_taux_devient_observe(self):
        # Un xG/90 observé contient DÉJÀ la force offensive du club : plus il
        # est observé, moins on a le droit de la remultiplier. À la limite,
        # la sensibilité doit s'éteindre.
        e_prior = self._sensibilite_a_la_force_du_club(0)
        e_moyen = self._sensibilite_a_la_force_du_club(900)
        e_observe = self._sensibilite_a_la_force_du_club(20000)
        self.assertGreater(e_prior, e_moyen)
        self.assertGreater(e_moyen, e_observe)
        self.assertGreater(e_prior, 0.10, "la force du club ne compte pas assez "
                                          "pour un joueur sans historique")
        self.assertLess(e_observe, 0.02, "la force du club est recomptée sur un "
                                         "taux déjà observé (double comptage)")

    def test_la_sensibilite_residuelle_suit_la_part_du_prior(self):
        # Contrôle quantitatif du mécanisme : la part non observée du taux
        # (1 - w_obs) est exactement ce qui reste sensible au club.
        p = _player(1, minutes=4000, expected_goals_per_90=0.5)
        w_obs = model.attack_rates(_parsed([p]), p)[3]
        e = self._sensibilite_a_la_force_du_club(4000)
        self.assertLess(e, (1 - w_obs) * 0.6,
                        "sensibilité supérieure à la part issue du prior")

    def test_force_du_club_appliquee_quand_le_taux_vient_du_prior(self):
        # À l'inverse, sans minutes observées le taux est team-agnostique :
        # la force du club DOIT alors compter.
        vierge = _player(1, minutes=0)
        fort = _parsed([vierge])
        faible = copy.deepcopy(fort)
        for t in faible["bootstrap"]["teams"]:
            if t["id"] == 1:
                t["strength_attack_home"] = t["strength_attack_away"] = 700
        ep_fort = model.project_player(fort, vierge, 1)["components"]["goals"]
        ep_faible = model.project_player(faible, vierge, 1)["components"]["goals"]
        self.assertGreater(ep_fort, ep_faible)


class CertitudeExcessiveTests(unittest.TestCase):
    """Après une ou deux GW, aucune probabilité artificielle à 0 % ou 100 %."""

    def _live(self, minutes_par_gw, pid=1):
        return {gw: {"elements": [{"id": pid, "stats": {"minutes": m}}]}
                for gw, m in enumerate(minutes_par_gw, 1)}

    def test_une_seule_titularisation_ne_donne_pas_100_pct(self):
        p = _player(1)
        parsed = _parsed([p], live=self._live([90]))
        hist, _ = model.appearance_history(parsed, 1)
        m = model.minutes_model(p, hist, parsed=parsed)
        self.assertLess(m["p60"], 0.90, "certitude excessive après 1 match")
        self.assertGreater(m["p60"], 0.0)
        self.assertLess(m["p_play"], 1.0)
        self.assertGreater(m["p0"], 0.0)

    def test_deux_titularisations_ne_donnent_pas_100_pct(self):
        p = _player(1)
        parsed = _parsed([p], live=self._live([90, 90]))
        hist, _ = model.appearance_history(parsed, 1)
        m = model.minutes_model(p, hist, parsed=parsed)
        self.assertLess(m["p_play"], 1.0)
        self.assertLess(m["p60"], 0.95)

    def test_un_seul_zero_ne_donne_pas_0_pct(self):
        p = _player(1)
        parsed = _parsed([p], live=self._live([0]))
        hist, _ = model.appearance_history(parsed, 1)
        m = model.minutes_model(p, hist, parsed=parsed)
        self.assertGreater(m["p_play"], 0.05, "probabilité artificiellement nulle")

    def test_le_statut_officiel_reste_souverain(self):
        # Un forfait officiel EST une certitude légitime : on ne la lisse pas.
        p = _player(1, status="i", chance_of_playing_next_round=None)
        parsed = _parsed([p], live=self._live([90, 90]))
        hist, _ = model.appearance_history(parsed, 1)
        self.assertEqual(model.minutes_model(p, hist, parsed=parsed)["p_play"], 0.0)


class PetitEchantillonOffensifTests(unittest.TestCase):
    """Les taux offensifs doivent être rétrécis, sans seuil de bascule."""

    def test_taux_aberrant_sur_90_minutes_fortement_retreci(self):
        p = _player(1, minutes=90, expected_goals_per_90=2.0)
        g90, _, _, w = model.attack_rates(_parsed([p]), p)
        self.assertLess(g90, 0.5, "taux non rétréci sur un échantillon d'un match")
        self.assertLess(w, 0.15)

    def test_aucune_discontinuite_autour_de_180_minutes(self):
        avant = _player(1, minutes=179, expected_goals_per_90=1.2)
        apres = _player(1, minutes=181, expected_goals_per_90=1.2)
        g_a = model.attack_rates(_parsed([avant]), avant)[0]
        g_b = model.attack_rates(_parsed([apres]), apres)[0]
        self.assertLess(abs(g_a - g_b), 0.01, "seuil de bascule à 180 minutes")

    def test_le_poids_de_l_observation_croit_avec_les_minutes(self):
        poids = []
        for mins in (90, 450, 900, 2700):
            p = _player(1, minutes=mins, expected_goals_per_90=0.8)
            poids.append(model.attack_rates(_parsed([p]), p)[3])
        self.assertEqual(poids, sorted(poids))
        self.assertLess(poids[0], poids[-1])

    def test_le_role_sur_coups_de_pied_arretes_hierarchise_sans_prix(self):
        tireur = _player(1, et=4, penalties_order=1)
        autre = _player(2, et=4, penalties_order=None)
        parsed = _parsed([tireur, autre])
        self.assertGreater(model.attack_rates(parsed, tireur)[0],
                           model.attack_rates(parsed, autre)[0])


class DefconTests(unittest.TestCase):
    """Ni zéro pour tout le monde, ni 0 %/100 % après un match."""

    def _live_dc(self, counts, pid=1):
        return {gw: {"elements": [{"id": pid, "stats": {
            "minutes": 90, "tackles": c, "clearances_blocks_interceptions": 0,
            "recoveries": 0}}]} for gw, c in enumerate(counts, 1)}

    def test_un_seul_match_reussi_ne_donne_pas_100_pct(self):
        p = _player(1, et=2)
        p_dc, _ = model.defcon_rate(_parsed([p], live=self._live_dc([20])), p)
        self.assertLess(p_dc, 0.95)
        self.assertGreater(p_dc, priors.DEFCON_RATE_PRIOR[2])

    def test_un_seul_match_rate_ne_donne_pas_0_pct(self):
        p = _player(1, et=2)
        p_dc, _ = model.defcon_rate(_parsed([p], live=self._live_dc([0])), p)
        self.assertGreater(p_dc, 0.02, "DEFCON annulé après un seul match")
        self.assertLess(p_dc, priors.DEFCON_RATE_PRIOR[2])

    def test_champs_absents_donnent_le_prior_et_non_zero(self):
        p = _player(1, et=2)
        live = {1: {"elements": [{"id": 1, "stats": {"minutes": 90}}]}}
        p_dc, base = model.defcon_rate(_parsed([p], live=live), p)
        self.assertGreater(p_dc, 0.0, "DEFCON à zéro pour tout le monde")
        self.assertIn("prior", base)

    def test_gardien_non_concerne(self):
        p = _player(1, et=1)
        self.assertEqual(model.defcon_rate(_parsed([p]), p)[0], 0.0)


class BonusDenominateurTests(unittest.TestCase):
    """Le bonus se rapporte aux minutes jouées, pas à minutes // 60."""

    def test_denominateur_en_minutes_reelles(self):
        # 10 entrées de 45 minutes = 450 min : l'ancien dénominateur
        # (450 // 60 = 7 apparitions) surestimait le taux par match.
        p = _player(1, minutes=450, bonus=5)
        rate = model.bonus_rate(_parsed([p]), p)
        attendu_brut = 5 / (450 / 90)          # 1.0 bonus par 90
        self.assertLess(rate, attendu_brut, "taux non rétréci")
        self.assertGreater(rate, priors.BONUS90_PRIOR[3])

    def test_zero_minute_donne_le_prior(self):
        p = _player(1, minutes=0, bonus=0)
        self.assertAlmostEqual(model.bonus_rate(_parsed([p]), p),
                               priors.BONUS90_PRIOR[3], places=6)


class PreselectionHorizonTests(unittest.TestCase):
    """La présélection classe sur l'horizon complet, jamais sur la seule GW1."""

    def test_un_joueur_sans_match_en_gw1_reste_selectionnable(self):
        parsed = build_parsed_initial()
        gws = [1, 2, 3, 4]
        # Le club 1 ne joue pas la GW1, mais joue les GW suivantes.
        parsed["fixtures"] = [f for f in parsed["fixtures"]
                              if not (f["event"] == 1 and 1 in (f["team_h"], f["team_a"]))]
        pool_ids = {r["id"] for r in initial.build_pool(parsed, gws)}
        club1 = [e["id"] for e in parsed["bootstrap"]["elements"] if e["team"] == 1]
        self.assertTrue(pool_ids & set(club1),
                        "aucun joueur du club sans match en GW1 dans le vivier — "
                        "présélection dominée par la première GW")

    def test_le_classement_du_vivier_utilise_l_ep_cumulee(self):
        parsed = build_parsed_initial()
        gws = [1, 2, 3, 4]
        pool = initial.build_pool(parsed, gws)
        for r in pool:
            self.assertAlmostEqual(r["ep4"], sum(r["eps"].values()), places=9)
            self.assertEqual(len(r["eps"]), len(gws))


class ReferenceEquipeTests(unittest.TestCase):
    """Le fichier de référence remplace les ratings FPL non validés ; absent,
    il ne fabrique rien et le repli est explicitement marqué."""

    def _ecrire(self, tmp, lignes):
        path = Path(tmp) / "team_priors.csv"
        path.write_text("team_name,goals_for,goals_against,matches,division\n"
                        + "\n".join(lignes) + "\n", encoding="utf-8")
        return str(path)

    def test_fichier_absent_ne_fabrique_rien(self):
        self.assertIsNone(priors.load_team_reference("/inexistant/x.csv", []))

    def test_promu_detecte_par_absence_ou_par_division(self):
        import tempfile
        teams = [{"id": 1, "name": "Fort", "short_name": "FOR"},
                 {"id": 2, "name": "Faible", "short_name": "FAI"},
                 {"id": 3, "name": "Promu", "short_name": "PRO"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = self._ecrire(tmp, ["Fort,80,30,38,1", "Faible,35,70,38,1",
                                      "Promu,60,40,46,2"])
            ref = priors.load_team_reference(path, teams)
        self.assertFalse(ref[1]["promoted"])
        self.assertTrue(ref[3]["promoted"], "club de division 2 non traité en promu")
        self.assertGreater(ref[1]["gf90"], ref[2]["gf90"])

    def test_la_reference_pilote_les_facteurs_d_equipe(self):
        import tempfile
        parsed = _parsed([_player(1)])
        sans = model.team_factors(parsed)
        self.assertIn("NON VALIDÉ", sans[1]["source"])
        with tempfile.TemporaryDirectory() as tmp:
            path = self._ecrire(tmp, ["Fort,80,30,38,1", "Faible,35,70,38,1"])
            parsed2 = _parsed([_player(1)])
            parsed2["team_ref"] = priors.load_team_reference(
                path, parsed2["bootstrap"]["teams"])
        avec = model.team_factors(parsed2)
        self.assertIn("référence publique", avec[1]["source"])
        self.assertGreater(avec[1]["att"], avec[2]["att"])


class StabiliteTests(unittest.TestCase):
    """Une équipe instable doit être DÉTECTÉE et ANNONCÉE, pas masquée."""

    def test_le_verdict_de_stabilite_suit_le_recouvrement_mesure(self):
        rec = initial.build_initial_recommendation(build_parsed_initial())
        self.assertEqual(rec["stable"],
                         rec["min_overlap"] >= rec["stability_threshold"])
        self.assertLessEqual(rec["min_overlap"], 15)
        self.assertEqual(len(rec["scenarios"]), 3)
        # Les scénarios doivent réellement diverger, sinon la mesure est creuse.
        valeurs = [s["own_value"] for s in rec["scenarios"]]
        self.assertGreater(max(valeurs) - min(valeurs), 1.0)

    def test_une_petite_variation_des_priors_est_mesuree_et_rendue(self):
        base = initial.build_initial_recommendation(build_parsed_initial())
        ids_base = {p["id"] for p in base["squad"]}
        original = dict(priors.XG90_PRIOR)
        try:                                    # variation raisonnable : ±10 %
            for k in priors.XG90_PRIOR:
                priors.XG90_PRIOR[k] = original[k] * 1.10
            varie = initial.build_initial_recommendation(build_parsed_initial())
        finally:
            priors.XG90_PRIOR.update(original)
        commun = len(ids_base & {p["id"] for p in varie["squad"]})
        # On n'exige PAS la stabilité (ce serait une prétention de qualité) :
        # on exige que l'instabilité éventuelle soit chiffrée et écrite.
        texte = render_initial(varie)
        self.assertIn("Recouvrement minimal du top 15", texte)
        if varie["min_overlap"] < varie["stability_threshold"]:
            self.assertIn("EFFECTIF INSTABLE", texte)
        self.assertLessEqual(commun, 15)

    def test_a_taille_reelle_l_instabilite_est_detectee_et_ecrite(self):
        # La démo à 6 clubs est trop peu peuplée pour exercer la détection :
        # à 20 clubs et ~700 joueurs, beaucoup de candidats sont quasi
        # équivalents et le top 15 bouge sous une variation raisonnable des
        # priors. C'est exactement ce que la machinerie doit rendre visible.
        from fpl_advisor.demo import build_parsed_scale
        rec = initial.build_initial_recommendation(build_parsed_scale())
        self.assertEqual(len(rec["squad"]), 15)
        self.assertEqual(rec["stable"],
                         rec["min_overlap"] >= rec["stability_threshold"])
        texte = render_initial(rec)
        self.assertIn("Recouvrement minimal du top 15", texte)
        if not rec["stable"]:
            self.assertIn("EFFECTIF INSTABLE", texte)
            self.assertIn("UNE option parmi plusieurs", texte)

    def test_le_rapport_annonce_l_instabilite_quand_elle_existe(self):
        rec = initial.build_initial_recommendation(build_parsed_initial())
        rec = dict(rec, stable=False, min_overlap=9)
        self.assertIn("EFFECTIF INSTABLE", render_initial(rec))


if __name__ == "__main__":
    unittest.main()
