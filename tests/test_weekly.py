# -*- coding: utf-8 -*-
"""Tests du mode hebdomadaire migré sur le contrat — hors ligne, aucune requête.

Ce que ces tests protègent :
  1. la décision de la semaine passe par le contrat de projections, pas par le
     snapshot ;
  2. la migration n'a changé aucun chiffre : mêmes XI, capitaine et arbitrage
     qu'avant ;
  3. la porte qualité hebdomadaire bloque ce qui doit l'être — deadline
     dépassée, collecte périmée, joueur illisible, décision instable ;
  4. l'effectif détenu, donnée personnelle, n'entre jamais dans le contrat ;
  5. l'évaluation mesure la stabilité sans importer l'optimiseur.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1] / "fpl_advisor"

from fpl_advisor import api, collect, model, weekly                    # noqa: E402
from fpl_advisor.advise import build_recommendation               # noqa: E402
from fpl_advisor.demo import build_parsed                         # noqa: E402
from fpl_advisor.evaluation import quality, stability             # noqa: E402
from fpl_advisor.evaluation.backend import SelectionBackend       # noqa: E402
from fpl_advisor.optimization import weekly as opt_weekly         # noqa: E402
from fpl_advisor.report import render                             # noqa: E402


def _parsed():
    if not hasattr(_parsed, "cache"):
        _parsed.cache = build_parsed()
    return _parsed.cache


def _contract():
    if not hasattr(_contract, "cache"):
        _contract.cache = weekly.build_contract(_parsed())
    return _contract.cache


def _rec():
    if not hasattr(_rec, "cache"):
        _rec.cache = build_recommendation(_parsed())
    return _rec.cache


class ContratHebdomadaireTests(unittest.TestCase):
    def test_horizon_de_trois_gw(self):
        c = _contract()
        self.assertEqual(len(c.horizon), weekly.WEEKLY_HORIZON_GWS)
        self.assertEqual(c.gw, _parsed()["next_gw"])

    def test_le_scenario_central_est_bien_la_reference(self):
        """`ep` (affiché) et `scenarios["central"]` (décidé) sont le même
        nombre : sinon le rapport montrerait autre chose que ce qui a servi
        à choisir le XI."""
        c = _contract()
        rows = {r["id"]: r for r in c.rows_for("central")}
        for r in c.rows:
            self.assertAlmostEqual(r.ep, rows[r.player_id]["eps"][r.gw], places=12)

    def test_le_contrat_ne_transporte_aucune_donnee_personnelle(self):
        c = _contract()
        squad_ids, _ = weekly.read_squad(_parsed())
        with tempfile.TemporaryDirectory() as tmp:
            path = c.save(Path(tmp) / "proj.json")
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        for interdit in ("my", "picks", "rivals", "standings", "team_id",
                         "league_id", "bank"):
            self.assertNotIn(interdit, data)
        # L'effectif détenu ne doit se déduire d'aucun champ du contrat.
        self.assertNotIn(squad_ids, list(data.values()))


class MigrationNeutreTests(unittest.TestCase):
    """La migration ajoute une porte qualité, elle ne change aucun chiffre."""

    def test_les_ep_sont_identiques_au_chemin_historique(self):
        parsed, c = _parsed(), _contract()
        elements = {e["id"]: e for e in parsed["bootstrap"]["elements"]}
        rows = {r["id"]: r for r in c.rows_for("central")}
        for pid in list(rows)[:40]:
            attendu = model.project_player(parsed, elements[pid], c.gw)["ep"]
            self.assertAlmostEqual(rows[pid]["eps"][c.gw], attendu, places=12)

    def test_xi_capitaine_et_arbitrage_restent_coherents(self):
        rec = _rec()
        self.assertEqual(len(rec["xi"]), 11)
        self.assertEqual(len(rec["bench"]), 4)
        self.assertEqual(len(rec["squad"]), 15)
        self.assertIn(rec["transfer"]["decision"], ("transférer", "conserver"))
        # Le capitaine affiché est bien celui du XI affiché, avec le même EP.
        cap = rec["armband"]["captain"]
        self.assertIn(cap["id"], {p["id"] for p in rec["xi"]})
        self.assertAlmostEqual(
            cap["ep"], next(p["ep"] for p in rec["xi"] if p["id"] == cap["id"]),
            places=12)


class PorteQualiteHebdomadaireTests(unittest.TestCase):
    def _bloquants(self, verdict):
        return [c.key for c in verdict.checks if c.state == quality.BLOCKED]

    def test_deadline_depassee_bloque(self):
        c = _contract()
        squad_ids, bank = weekly.read_squad(_parsed())
        apres = datetime.now(timezone.utc) + timedelta(days=5)
        rec = weekly.build_from_contract(c, squad_ids, bank, now=apres)
        self.assertEqual(rec["verdict"].state, quality.BLOCKED)
        self.assertIn("deadline_actionnable", self._bloquants(rec["verdict"]))
        self.assertEqual(rec["verdict"].label, "décision technique")

    def test_collecte_perimee_avertit_puis_bloque(self):
        c = _contract()
        base = datetime.now(timezone.utc)
        etats = {}
        for heures in (0, quality.SNAPSHOT_AGE_WARN_H + 1,
                       quality.SNAPSHOT_AGE_BLOCK_H + 1):
            v = quality.assess_weekly(c, {}, now=base + timedelta(hours=heures))
            etats[heures] = next(k.state for k in v.checks
                                 if k.key == "fraicheur_snapshot")
        self.assertEqual(etats[0], quality.ACCEPTED)
        self.assertEqual(etats[quality.SNAPSHOT_AGE_WARN_H + 1], quality.WARNING)
        self.assertEqual(etats[quality.SNAPSHOT_AGE_BLOCK_H + 1], quality.BLOCKED)

    def test_joueur_illisible_bloque_mais_la_decision_reste_calculee(self):
        parsed = build_parsed()
        squad_ids, bank = weekly.read_squad(parsed)
        # Un défenseur de l'effectif quitte le championnat : le contrat ne le
        # projette plus. L'effectif passe à 14 lisibles, le XI reste faisable.
        elements = {e["id"]: e for e in parsed["bootstrap"]["elements"]}
        parti = next(pid for pid in squad_ids
                     if elements[pid]["element_type"] == 2)
        elements[parti]["status"] = "u"
        rec = weekly.build_from_contract(weekly.build_contract(parsed),
                                         squad_ids, bank)
        self.assertEqual(rec["missing_ids"], [parti])
        self.assertIn("effectif_lisible", self._bloquants(rec["verdict"]))
        self.assertEqual(len(rec["squad"]), 14)
        self.assertEqual(len(rec["xi"]), 11)      # calculé malgré le blocage

    def test_desaccord_entre_scenarios_sur_le_capitaine(self):
        c = _contract()
        cas = {3: quality.ACCEPTED, 2: quality.WARNING, 1: quality.BLOCKED}
        for accord, attendu in cas.items():
            with self.subTest(accord=accord):
                v = quality.assess_weekly(
                    c, {"n_scenarios": 3, "captain_agree": accord})
                etat = next(k.state for k in v.checks
                            if k.key == "stabilite_capitaine")
                self.assertEqual(etat, attendu)

    def test_transfert_deja_effectue_bloque(self):
        """Les picks publics datent de la GW close. Un transfert déjà fait pour
        la GW à venir les rend faux, et rien d'autre ne le signalerait."""
        parsed = build_parsed()
        gw = parsed["next_gw"]
        self.assertEqual(weekly.pending_transfers(parsed, gw), [])
        parsed["my"]["transfers"] = [
            {"event": gw - 1, "element_in": 1, "element_out": 2},   # GW passée
            {"event": gw, "element_in": 3, "element_out": 4},       # celle-ci
        ]
        self.assertEqual(len(weekly.pending_transfers(parsed, gw)), 1)
        rec = build_recommendation(parsed)
        self.assertIn("effectif_a_jour", self._bloquants(rec["verdict"]))
        self.assertEqual(rec["verdict"].state, quality.BLOCKED)

    def test_sans_transfert_l_effectif_est_declare_a_jour(self):
        rec = _rec()
        etat = next(c.state for c in rec["verdict"].checks
                    if c.key == "effectif_a_jour")
        self.assertEqual(etat, quality.ACCEPTED)
        self.assertEqual(rec["pick_gw"], _parsed()["last_closed_gw"])

    def test_effectif_absent_bloque_avant_tout_calcul(self):
        parsed = dict(build_parsed(), my={})
        with self.assertRaises(SystemExit) as ctx:
            build_recommendation(parsed)
        self.assertIn("BLOCAGE FACTUEL", str(ctx.exception))


class StabiliteDesDecisionsTests(unittest.TestCase):
    def test_trois_scenarios_rejoues_sur_le_meme_effectif(self):
        rec = _rec()
        ag = rec["agreement"]
        self.assertEqual(len(rec["scenarios"]), 3)
        self.assertEqual(ag["n_scenarios"], 3)
        for cle in ("captain_agree", "decision_agree", "swap_agree"):
            self.assertLessEqual(ag[cle], 3)
        self.assertEqual(ag["xi_size"], 11)
        # L'effectif ne bouge pas d'un scénario à l'autre : c'est celui du
        # manager. Seules les décisions peuvent changer.
        self.assertEqual(len(rec["squad"]), 15)

    def test_l_evaluation_n_importe_pas_l_optimiseur(self):
        """Un backend factice suffit : preuve que l'inversion tient aussi pour
        la stabilité hebdomadaire."""
        appels = []

        def faux_weekly(rows, squad_ids, bank, gws):
            appels.append(len(rows))
            ids = list(squad_ids)
            return {"captain_id": ids[0], "xi_ids": set(ids[:11]),
                    "decision": "conserver", "swap": None,
                    "transfer": {"candidates": []},
                    "armband": {"captain": {"web_name": "X", "ep": 1.0}}}

        backend = SelectionBackend(select=None, value=None, legality=None,
                                   decisions=None, weekly=faux_weekly)
        squad_ids, bank = weekly.read_squad(_parsed())
        rows, ag = stability.decision_stability(_contract(), backend,
                                                squad_ids, bank)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(appels), 3)
        self.assertEqual(ag["captain_agree"], 3)

    def test_conserver_ne_compare_aucun_couple_d_echange(self):
        """Sous « conserver », le meilleur candidat reste affiché pour
        information mais ne compte pas comme une décision : deux scénarios qui
        conservent décrivent la même action, quel que soit le candidat
        sous-jacent. Sans cette règle, la porte qualité criait à l'instabilité
        sur une semaine où il n'y a rien à faire."""
        c = _contract()
        squad_ids, bank = weekly.read_squad(_parsed())
        d = opt_weekly.weekly_decision(c.rows_for("central"), squad_ids, bank,
                                       list(c.horizon))
        if d["decision"] == "conserver":
            self.assertTrue(d["transfer"]["candidates"])   # candidats calculés
            self.assertIsNone(d["swap"])                   # mais rien à comparer
        else:
            self.assertIsNotNone(d["swap"])

    def test_backend_sans_weekly_refuse_explicitement(self):
        backend = SelectionBackend(select=None, value=None, legality=None,
                                   decisions=None)
        with self.assertRaises(ValueError):
            stability.decision_stability(_contract(), backend, [1, 2], 0)


class OptimisationHebdomadaireTests(unittest.TestCase):
    def test_la_preselection_est_bornee_par_poste(self):
        c = _contract()
        squad_ids, _ = weekly.read_squad(_parsed())
        market = opt_weekly.shortlist(c.rows_for("central"), set(squad_ids),
                                      c.gw, per_position=3)
        for et in (1, 2, 3, 4):
            self.assertLessEqual(sum(1 for r in market
                                     if r["element_type"] == et), 3)
        self.assertFalse({r["id"] for r in market} & set(squad_ids))

    def test_le_module_ne_lit_aucune_donnee_brute(self):
        source = (ROOT / "optimization" / "weekly.py").read_text(encoding="utf-8")
        for interdit in ('"bootstrap"', '"elements"', '"live"', 'parsed['):
            self.assertNotIn(interdit, source)

    def test_advise_ne_projette_plus_lui_meme(self):
        """L'orchestrateur ne doit plus appeler le moteur de prévision : il
        délègue au contrat. C'était le point de divergence entre les deux modes."""
        source = (ROOT / "advise.py").read_text(encoding="utf-8")
        for interdit in ("project_player", "project_horizon", "team_strengths",
                         '"bootstrap"'):
            self.assertNotIn(interdit, source)


class FraicheurDuSnapshotTests(unittest.TestCase):
    def test_as_of_vient_du_manifeste(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20260820T101500Z"
            run.mkdir()
            (run / "manifest.json").write_text(json.dumps([
                {"file": "a.json", "retrieved_at": "2026-08-20T10:15:00+00:00"},
                {"file": "b.json", "retrieved_at": "2026-08-20T10:16:30+00:00"},
            ]), encoding="utf-8")
            self.assertEqual(collect.snapshot_as_of(run),
                             "2026-08-20T10:16:30+00:00")

    def test_repli_sur_le_nom_du_repertoire(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20260820T101500Z"
            run.mkdir()
            self.assertTrue(collect.snapshot_as_of(run).startswith("2026-08-20T10:15"))

    def test_repertoire_sans_horodatage_ne_fabrique_aucune_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(collect.snapshot_as_of(Path(tmp) / "n-importe-quoi"))


class CouvertureEnCoursDeSaisonTests(unittest.TestCase):
    """`history_past` ne veut pas dire la même chose avant la GW1 et après.

    Sans cette nuance, `run` — qui ne collecte pas les ~700 element-summary —
    serait bloqué toutes les semaines pour un critère de pré-saison."""

    def _sans_saisons_passees(self, n_gws):
        contract = weekly.build_contract(dict(build_parsed(), history_past={}))
        contract.n_history_gws = n_gws
        return contract

    def _couverture(self, contract):
        v = quality.assess_weekly(contract, {})
        return next(c.state for c in v.checks if c.key == "couverture_donnees")

    def test_debut_de_saison_sans_saisons_passees_bloque(self):
        c = self._sans_saisons_passees(quality.LIVE_GWS_REPLACING_HISTORY - 1)
        self.assertEqual(self._couverture(c), quality.BLOCKED)

    def test_assez_de_journees_jouees_degrade_sans_bloquer(self):
        c = self._sans_saisons_passees(quality.LIVE_GWS_REPLACING_HISTORY)
        self.assertEqual(self._couverture(c), quality.WARNING)

    def test_avant_la_gw1_le_blocage_reste_entier(self):
        """Le mode effectif initial garde le critère strict : rien n'a bougé
        pour lui."""
        c = self._sans_saisons_passees(10)
        etat = next(k.state for k in quality.assess(c).checks
                    if k.key == "couverture_donnees")
        self.assertEqual(etat, quality.BLOCKED)

    def test_une_source_obligatoire_absente_reste_bloquante(self):
        c = self._sans_saisons_passees(10)
        c.availability = [dict(r, present=False) if r["key"] == "bootstrap_core"
                          else r for r in c.availability]
        c.data_confidence = "bloqué"
        self.assertEqual(self._couverture(c), quality.BLOCKED)


class CollecteHebdomadaireTests(unittest.TestCase):
    def test_with_history_atteint_les_saisons_passees(self):
        """`run --with-history` doit appeler element-summary, sinon il n'existe
        aucun moyen de sortir de la confiance « faible » en début de saison."""
        appels = []
        elements = [{"id": 1}, {"id": 2}]

        def faux_get(path, store=None, name=None):
            appels.append(path)
            if path == "/bootstrap-static/":
                return {"elements": elements, "events": [], "teams": []}, None
            return {}, None

        vrai = collect.get_json
        collect.get_json = faux_get
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = {"team_id": 1, "league_id": 2}
                collect.collect_all(cfg, tmp)
                sans = [a for a in appels if "element-summary" in a]
                appels.clear()
                collect.collect_all(cfg, tmp, with_history=True)
                avec = [a for a in appels if "element-summary" in a]
        finally:
            collect.get_json = vrai
        self.assertEqual(sans, [])
        self.assertEqual(avec, ["/element-summary/1/", "/element-summary/2/"])


class ConfigurationLocaleTests(unittest.TestCase):
    """Le gabarit livré vaut 0 pour les deux identifiants. Un 0 est un entier :
    il passait la validation et produisait une collecte entière de 404."""

    def _ecrire(self, tmp, contenu):
        chemin = Path(tmp) / "config.local.json"
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        return chemin

    def test_le_gabarit_non_modifie_est_refuse(self):
        gabarit = json.loads(
            (Path(__file__).resolve().parents[1] / "config.example.json")
            .read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                api.load_config(self._ecrire(tmp, gabarit))
            self.assertIn("gabarit", str(ctx.exception))

    def test_identifiants_reels_acceptes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = api.load_config(
                self._ecrire(tmp, {"team_id": 1234567, "league_id": 98765}))
            self.assertEqual(cfg["team_id"], 1234567)

    def test_champ_manquant_ou_non_entier_refuse(self):
        for mauvais in ({"team_id": 1}, {"team_id": "1234567", "league_id": 9},
                        {"team_id": True, "league_id": 9}):
            with self.subTest(cfg=mauvais), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(SystemExit):
                    api.load_config(self._ecrire(tmp, mauvais))


class RapportHebdomadaireTests(unittest.TestCase):
    def test_sections_completes(self):
        texte = render(_rec())
        for section in ("## Contrôle qualité de la décision", "## Synthèse",
                        "## XI recommandé", "## Banc",
                        "## Capitaine et vice",
                        "## Trois scénarios et stabilité des décisions",
                        "## Transférer ou conserver",
                        "## Projections, incertitude",
                        "## Mini-ligue — exposition connue des rivaux",
                        "## Événements qui feraient changer",
                        "## Limites de la V0"):
            self.assertIn(section, texte)

    def test_une_decision_bloquee_n_est_jamais_appelee_recommandation(self):
        c = _contract()
        squad_ids, bank = weekly.read_squad(_parsed())
        apres = datetime.now(timezone.utc) + timedelta(days=5)
        texte = render(weekly.build_from_contract(c, squad_ids, bank, now=apres))
        self.assertIn("DÉCISION TECHNIQUE — publication refusée", texte)
        self.assertIn("## XI calculé (non publiable)", texte)
        self.assertNotIn("## XI recommandé", texte)


if __name__ == "__main__":
    unittest.main()
