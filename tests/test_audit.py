# -*- coding: utf-8 -*-
"""Tests de l'audit d'effectif comparatif — hors ligne, aucune requête.

Ce que ces tests protègent :
  1. le budget devenu paramétrable ne change AUCUN chiffre existant : à budget
     par défaut, l'optimiseur rend exactement ce qu'il rendait avant ;
  2. l'effectif reconstruit respecte la valeur d'équipe du manager, pas les
     100,0 M£ du départ, et toutes les contraintes FPL ;
  3. l'écart et le chemin de transferts se mesurent sur la VALEUR DE
     L'EFFECTIF (meilleur XI + brassard), jamais sur les points individuels —
     c'est la correction A2, elle doit tenir ici aussi ;
  4. le chemin est monotone, borné, et respecte banque et limite de club ;
  5. l'effectif détenu, donnée personnelle, n'entre jamais dans le contrat ;
  6. la porte qualité de l'audit bloque ce qui doit l'être et — choix assumé —
     ne bloque PAS sur une deadline dépassée ;
  7. un contrat figé en `.gz` se relit à l'identique.
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import audit as orch                              # noqa: E402
from fpl_advisor import weekly                                     # noqa: E402
from fpl_advisor.demo import build_parsed                          # noqa: E402
from fpl_advisor.evaluation import quality                         # noqa: E402
from fpl_advisor.forecasting import ProjectionSet                  # noqa: E402
from fpl_advisor.optimization import audit as opt_audit            # noqa: E402
from fpl_advisor.optimization import initial as opt_initial        # noqa: E402
from fpl_advisor.report import render_audit                        # noqa: E402


def _parsed():
    if not hasattr(_parsed, "cache"):
        _parsed.cache = build_parsed()
    return _parsed.cache


def _contract():
    if not hasattr(_contract, "cache"):
        _contract.cache = orch.build_contract(_parsed())
    return _contract.cache


def _squad_and_bank():
    return weekly.read_squad(_parsed())


def _rec():
    if not hasattr(_rec, "cache"):
        ids, bank = _squad_and_bank()
        _rec.cache = orch.build_from_contract(_contract(), ids, bank)
    return _rec.cache


def _fake(pid, et, cost, eps, team=1, p_play=1.0, p0=0.0):
    """Ligne de contrat minimale, telle que l'optimisation la consomme."""
    return {"id": pid, "web_name": f"J{pid}", "element_type": et, "team": team,
            "now_cost": cost, "p_play": p_play, "p60": p_play, "p0": p0,
            "minutes_basis": "", "minutes_confidence": "moyenne",
            "eps": dict(eps), "ep_by_gw": dict(eps), "ep_if_start_by_gw": dict(eps),
            "components_by_gw": {}, "ep4": sum(eps.values())}


def _quinze(eps_par_joueur, gws=(1,)):
    """15 joueurs légaux (2-5-5-3), un club par joueur, EP imposées."""
    squad, pid = [], 1
    for et, quota in ((1, 2), (2, 5), (3, 5), (4, 3)):
        for _ in range(quota):
            e = eps_par_joueur.get(pid, 1.0)
            squad.append(_fake(pid, et, 40, {g: e for g in gws}, team=pid))
            pid += 1
    return squad


class BudgetParametrableTests(unittest.TestCase):
    """Le budget est devenu un paramètre. Par défaut, rien ne doit bouger."""

    def test_optimisation_identique_au_budget_par_defaut(self):
        rows = _contract().rows_for("central")
        pool = opt_initial.build_pool(rows)
        gws = list(_contract().horizon)
        implicite = opt_initial.optimize_squad(pool, gws)
        explicite = opt_initial.optimize_squad(pool, gws, opt_initial.BUDGET)
        self.assertEqual([r["id"] for r in implicite[0]],
                         [r["id"] for r in explicite[0]])
        self.assertAlmostEqual(implicite[1], explicite[1], places=12)

    def test_legalite_identique_au_budget_par_defaut(self):
        squad = _rec()["rebuilt"]
        rows = {r["id"]: r for r in _contract().rows_for("central")}
        squad = [rows[r["id"]] for r in squad]
        self.assertEqual(opt_initial.legality(squad),
                         opt_initial.legality(squad, opt_initial.BUDGET))

    def test_un_budget_plus_petit_donne_un_effectif_moins_cher(self):
        rows = _contract().rows_for("central")
        pool = opt_initial.build_pool(rows)
        gws = list(_contract().horizon)
        riche, v_riche = opt_initial.optimize_squad(pool, gws, 1000)
        pauvre, v_pauvre = opt_initial.optimize_squad(pool, gws, 800)
        self.assertLessEqual(sum(r["now_cost"] for r in pauvre), 800)
        self.assertLessEqual(sum(r["now_cost"] for r in riche), 1000)
        # Moins d'argent ne peut pas rendre meilleur : l'ensemble des effectifs
        # atteignables à 80,0 M£ est inclus dans celui à 100,0 M£.
        self.assertLessEqual(v_pauvre, v_riche + 1e-9)


class ValeurEtReconstructionTests(unittest.TestCase):
    def test_valeur_d_equipe_est_effectif_plus_banque(self):
        owned = _quinze({})
        self.assertEqual(opt_audit.team_value(owned, 25),
                         sum(r["now_cost"] for r in owned) + 25)

    def test_horizon_de_quatre_gw(self):
        c = _contract()
        self.assertEqual(len(c.horizon), orch.AUDIT_HORIZON_GWS)
        self.assertGreater(len(c.horizon), weekly.WEEKLY_HORIZON_GWS)

    def test_effectif_reconstruit_respecte_la_valeur_d_equipe(self):
        rec = _rec()
        self.assertLessEqual(rec["cout_ideal"], rec["budget"])
        self.assertEqual(rec["budget"], rec["cout_detenu"] + rec["bank"])

    def test_effectif_reconstruit_respecte_les_contraintes_fpl(self):
        legalite = _rec()["legality"]
        self.assertTrue(legalite["size_ok"], legalite)
        self.assertTrue(legalite["quota_ok"], legalite)
        self.assertTrue(legalite["club_ok"], legalite)
        self.assertTrue(legalite["budget_ok"], legalite)

    def test_l_effectif_reconstruit_vaut_au_moins_le_detenu(self):
        """À budget égal, un optimiseur qui rendrait moins bien que l'équipe
        détenue signalerait une erreur de mesure, pas une bonne équipe."""
        rec = _rec()
        self.assertIsNotNone(rec["retard"])
        self.assertGreaterEqual(rec["retard"], -1e-9)

    def test_la_reconstruction_ne_peut_pas_valoir_moins_que_le_detenu(self):
        """Régression : la montée locale partant du seul effectif le moins cher
        se calait SOUS l'équipe détenue sur le jeu de démo (retard −0,91 pt).
        Le rapport annonçait alors « votre équipe bat le modèle » alors que la
        seule chose démontrée était l'échec de la montée."""
        c = _contract()
        rows, gws = c.rows_for("central"), list(c.horizon)
        ids, bank = _squad_and_bank()
        owned, _ = opt_audit.read_owned(rows, ids)
        budget = opt_audit.team_value(owned, bank)
        detenu = opt_initial.squad_value(owned, gws)
        depuis_zero = opt_initial.optimize_squad(
            opt_initial.build_pool(rows), gws, budget)[1]
        self.assertLess(depuis_zero, detenu,
                        "le jeu de démo n'exerce plus le défaut : la montée "
                        "partant du moins cher ne se cale plus sous l'effectif "
                        "détenu, ce test ne protège plus rien")
        _, valeur, _ = opt_audit.rebuild(rows, gws, budget, owned)
        self.assertGreaterEqual(valeur, detenu - 1e-9)

    def test_les_deux_effectifs_sont_chiffres_de_la_meme_facon(self):
        """Détenu et reconstruit passent par `squad_value` : meilleur XI par GW
        + brassard. Une comparaison entre deux mesures différentes ne voudrait
        rien dire."""
        c, rec = _contract(), _rec()
        rows = {r["id"]: r for r in c.rows_for("central")}
        gws = list(c.horizon)
        detenu = [rows[r["id"]] for r in rec["owned"]]
        reconstruit = [rows[r["id"]] for r in rec["rebuilt"]]
        self.assertAlmostEqual(rec["valeur_detenue"],
                               opt_initial.squad_value(detenu, gws), places=9)
        self.assertAlmostEqual(rec["valeur_ideale"],
                               opt_initial.squad_value(reconstruit, gws), places=9)


class DivergenceTests(unittest.TestCase):
    def test_les_trois_ensembles_se_recomposent(self):
        rec = _rec()
        self.assertEqual(rec["recouvrement"] + len(rec["detenus_ecartes"]),
                         len(rec["owned"]))
        self.assertEqual(rec["recouvrement"] + len(rec["retenus_non_detenus"]),
                         len(rec["rebuilt"]))

    def test_les_quotas_de_poste_sont_conserves_de_part_et_d_autre(self):
        rec = _rec()
        for et, quota in opt_initial.SQUAD_QUOTA.items():
            v = rec["par_poste"][et]
            self.assertEqual(v["communs"] + len(v["retenus_non_detenus"]), quota)


class CheminDeTransfertsTests(unittest.TestCase):
    def test_chaque_etape_ameliore_strictement_la_valeur(self):
        ch = _rec()["chemin"]
        self.assertIsNotNone(ch)
        for e in ch["etapes"]:
            self.assertGreater(e["gain"], 0.0)

    def test_le_cumul_est_croissant_et_egal_au_gain_total(self):
        ch = _rec()["chemin"]
        cumuls = [e["cumul"] for e in ch["etapes"]]
        self.assertEqual(cumuls, sorted(cumuls))
        if cumuls:
            self.assertAlmostEqual(cumuls[-1], ch["gain_total"], places=9)
        self.assertAlmostEqual(ch["valeur_arrivee"] - ch["valeur_depart"],
                               ch["gain_total"], places=9)

    def test_le_chemin_ne_depasse_jamais_le_nombre_de_semaines(self):
        rec = _rec()
        self.assertLessEqual(len(rec["chemin"]["etapes"]), rec["semaines"])
        self.assertEqual([e["semaine"] for e in rec["chemin"]["etapes"]],
                         list(range(1, len(rec["chemin"]["etapes"]) + 1)))

    def test_la_banque_ne_devient_jamais_negative(self):
        for e in _rec()["chemin"]["etapes"]:
            self.assertGreaterEqual(e["banque_apres"], 0)

    def test_un_entrant_hors_budget_est_refuse(self):
        squad = _quinze({})
        cher = _fake(99, 4, 200, {1: 99.0}, team=99)
        self.assertIsNone(opt_audit.best_swap(squad, [cher], [1], bank=0))
        # Avec la banque suffisante, le même échange redevient réalisable.
        step = opt_audit.best_swap(squad, [cher], [1], bank=160)
        self.assertIsNotNone(step)
        self.assertEqual(step["in"]["id"], 99)

    def test_la_limite_de_trois_joueurs_par_club_est_respectee(self):
        squad = _quinze({})
        for r in squad[2:5]:             # trois DÉFENSEURS du club 42
            r["team"] = 42
        # Un gardien du club 42 ferait un quatrième : quel que soit le gardien
        # sorti, il vient d'un autre club, donc le compte du club 42 monterait.
        quatrieme = _fake(99, 1, 40, {1: 99.0}, team=42)
        self.assertIsNone(opt_audit.best_swap(squad, [quatrieme], [1], bank=0))
        # Le même joueur dans un club non saturé entre sans difficulté.
        ailleurs = _fake(98, 1, 40, {1: 99.0}, team=77)
        self.assertIsNotNone(opt_audit.best_swap(squad, [ailleurs], [1], bank=0))

    def test_A2_le_gain_se_mesure_sur_le_XI_pas_sur_les_points_individuels(self):
        """Régression A2, portée à l'audit.

        Deux gardiens : un titulaire à 5 pts, un remplaçant à 0. Remplacer le
        remplaçant par un gardien à 4 pts n'ajoute RIEN au XI — un seul gardien
        joue. La différence de points individuels vaut pourtant +4."""
        squad = _quinze({1: 5.0, 2: 0.0})
        entrant = _fake(99, 1, 40, {1: 4.0}, team=99)
        self.assertIsNone(opt_audit.best_swap(squad, [entrant], [1], bank=0))
        # Le même joueur à la place du TITULAIRE ne passe pas non plus : il est
        # moins bon. En revanche, au-dessus de 5 pts, il entre.
        meilleur = _fake(98, 1, 40, {1: 7.0}, team=98)
        step = opt_audit.best_swap(squad, [meilleur], [1], bank=0)
        self.assertIsNotNone(step)
        self.assertEqual(step["out"]["id"], 1)

    def test_le_chemin_s_arrete_quand_plus_rien_n_ameliore(self):
        squad = _quinze({})
        rows = squad + [_fake(99, 4, 40, {1: 0.1}, team=99)]
        ch = opt_audit.transfer_path(squad, rows, 0, [1], weeks=4, pool=[rows[-1]])
        self.assertEqual(ch["etapes"], [])
        self.assertAlmostEqual(ch["gain_total"], 0.0, places=9)


class FrontierePersonnelleTests(unittest.TestCase):
    def test_le_contrat_ne_transporte_aucune_donnee_personnelle(self):
        c = _contract()
        squad_ids, _ = _squad_and_bank()
        blob = str(c.to_dict())
        for cle in ("picks", "entry_history", "standings", "team_id"):
            self.assertNotIn(cle, blob)
        # Les identifiants détenus n'apparaissent pas EN TANT QU'EFFECTIF :
        # le contrat projette tout le marché, effectif compris, mais ne dit
        # nulle part lesquels sont détenus.
        self.assertNotIn("squad", c.to_dict())
        self.assertTrue(set(squad_ids) <= set(c.player_ids()))

    def test_le_contrat_ne_lit_pas_l_effectif(self):
        """`build_contract` ne doit rien tirer de `my` : c'est ce qui permet de
        figer les projections sans config ni team ID (commande `freeze`)."""
        public = dict(_parsed(), my={}, standings=[], rivals={}, team_id=None,
                      league_id=None)
        # `as_of` est horodaté à la construction quand le snapshot n'en porte
        # pas (cas de la démo) : il est comparé à part, le reste au bit près.
        sans_effectif = orch.build_contract(public).to_dict()
        avec_effectif = _contract().to_dict()
        sans_effectif.pop("as_of"), avec_effectif.pop("as_of")
        self.assertEqual(sans_effectif, avec_effectif)


class PorteQualiteTests(unittest.TestCase):
    def _faits(self, **kw):
        faits = {"min_overlap": 15, "rebuilt_ids": [], "squad_size": 15,
                 "missing_ids": [], "missing_names": [],
                 "already_transferred": 0, "pick_gw": 1,
                 "size_ok": True, "budget_ok": True, "quota_ok": True,
                 "club_ok": True}
        faits.update(kw)
        return faits

    def _now(self):
        return datetime.strptime(_contract().as_of[:19], "%Y-%m-%dT%H:%M:%S") \
            .replace(tzinfo=timezone.utc)

    def test_verdict_nominal_publiable(self):
        v = quality.assess_audit(_contract(), self._faits(), now=self._now())
        self.assertTrue(v.publishable, v.summary)

    def test_une_deadline_depassee_ne_bloque_pas_un_audit(self):
        """Choix assumé : un audit décrit une divergence sur quatre journées,
        il reste vrai après 17h30. La porte hebdomadaire, elle, bloque."""
        tard = self._now() + timedelta(days=30)
        v = quality.assess_audit(_contract(), self._faits(), now=tard)
        self.assertNotIn("deadline_actionnable", [c.key for c in v.checks])
        w = quality.assess_weekly(_contract(), self._faits(), now=tard)
        self.assertIn("deadline_actionnable",
                      [c.key for c in w.reasons(quality.BLOCKED)])

    def test_une_collecte_perimee_bloque(self):
        vieux = self._now() + timedelta(hours=quality.SNAPSHOT_AGE_BLOCK_H + 1)
        v = quality.assess_audit(_contract(), self._faits(), now=vieux)
        self.assertIn("fraicheur_snapshot",
                      [c.key for c in v.reasons(quality.BLOCKED)])

    def test_un_effectif_illisible_bloque(self):
        v = quality.assess_audit(
            _contract(), self._faits(missing_ids=[123], missing_names=["#123"]),
            now=self._now())
        self.assertIn("effectif_lisible",
                      [c.key for c in v.reasons(quality.BLOCKED)])

    def test_un_effectif_reconstruit_instable_bloque(self):
        v = quality.assess_audit(
            _contract(),
            self._faits(min_overlap=quality.STABILITY_MIN_OVERLAP - 1),
            now=self._now())
        self.assertIn("stabilite_top15",
                      [c.key for c in v.reasons(quality.BLOCKED)])

    def test_un_transfert_deja_passe_bloque(self):
        v = quality.assess_audit(_contract(), self._faits(already_transferred=1),
                                 now=self._now())
        self.assertIn("effectif_a_jour",
                      [c.key for c in v.reasons(quality.BLOCKED)])


class RapportTests(unittest.TestCase):
    def test_le_rapport_porte_le_caveat_du_wildcard(self):
        md = render_audit(_rec())
        self.assertIn("wildcard", md)
        self.assertIn("CE QUE CET AUDIT N'EST PAS", md)
        self.assertIn("Prix de vente approximés", md)

    def test_le_rapport_ouvre_par_l_ecart_chiffre(self):
        md = render_audit(_rec())
        tete = md.split("\n\n")[1]
        self.assertIn("Retard de l'effectif détenu", tete)

    def test_le_rapport_montre_les_deux_effectifs_en_entier(self):
        rec = _rec()
        md = render_audit(rec)
        self.assertIn("Effectif détenu (15 joueurs)", md)
        self.assertIn("Effectif reconstruit (15 joueurs)", md)
        for r in rec["owned"] + rec["rebuilt"]:
            self.assertIn(r["web_name"], md)


class BoutEnBoutTests(unittest.TestCase):
    """Le chemin réellement emprunté par la commande `audit-effectif` :
    snapshot → effectif lu → contrat → audit → rapport écrit."""

    def test_build_audit_lit_l_effectif_et_ecrit_un_rapport(self):
        from fpl_advisor.report import write_audit
        with tempfile.TemporaryDirectory() as d:
            fige = Path(d) / "proj.json.gz"
            rec = orch.build_audit(_parsed(), freeze_to=fige)
            self.assertEqual(rec["frozen_projections"], str(fige))
            self.assertTrue(fige.exists())
            self.assertEqual([r["id"] for r in rec["owned"]],
                             _squad_and_bank()[0])
            self.assertEqual(rec["bank"], _squad_and_bank()[1])
            chemin = write_audit(rec, d)
            self.assertTrue(chemin.exists())
            self.assertIn(f"GW{rec['gw']}-audit-effectif", chemin.name)
            texte = chemin.read_text(encoding="utf-8")
            self.assertIn("Retard de l'effectif détenu", texte)
            self.assertIn("Chemin de transferts proposé", texte)

    def test_le_contrat_fige_par_l_audit_ne_dit_pas_qui_detient_quoi(self):
        with tempfile.TemporaryDirectory() as d:
            fige = Path(d) / "proj.json"
            orch.build_audit(_parsed(), freeze_to=fige)
            contenu = fige.read_text(encoding="utf-8")
            for cle in ('"picks"', '"entry_history"', '"team_id"', '"bank"',
                        '"standings"'):
                self.assertNotIn(cle, contenu)


class FigeageCompresseTests(unittest.TestCase):
    def test_aller_retour_gz_identique(self):
        c = _contract()
        with tempfile.TemporaryDirectory() as d:
            clair = c.save(Path(d) / "p.json")
            compresse = c.save(Path(d) / "p.json.gz")
            self.assertLess(compresse.stat().st_size, clair.stat().st_size)
            self.assertEqual(ProjectionSet.load(clair).to_dict(),
                             ProjectionSet.load(compresse).to_dict())
            self.assertEqual(ProjectionSet.load(compresse).to_dict(), c.to_dict())


if __name__ == "__main__":
    unittest.main()
