# -*- coding: utf-8 -*-
"""Tests de l'architecture en trois couches — hors ligne, aucune requête.

Ce que ces tests protègent :
  1. le contrat de projections se sérialise et se relit sans perte ;
  2. l'optimisation fonctionne à partir du seul contrat, sans données brutes ;
  3. le contrôle qualité rend bien ses trois verdicts ;
  4. une équipe instable est bloquée mais reste calculable ;
  5. la direction des dépendances est respectée dans le code source.
"""

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1] / "fpl_advisor"

from fpl_advisor import initial, wiring                       # noqa: E402
from fpl_advisor.demo import build_parsed_initial             # noqa: E402
from fpl_advisor.evaluation import quality, stability         # noqa: E402
from fpl_advisor.evaluation.backend import SelectionBackend   # noqa: E402
from fpl_advisor.forecasting import ProjectionSet             # noqa: E402
from fpl_advisor.optimization import initial as opt_initial   # noqa: E402
from fpl_advisor.report import render_initial                 # noqa: E402


def _contract():
    if not hasattr(_contract, "cache"):
        _contract.cache = initial.build_contract(build_parsed_initial())
    return _contract.cache


class ContratSerialisationTests(unittest.TestCase):
    """Le contrat doit survivre à un aller-retour JSON sans rien perdre."""

    def test_champs_obligatoires_par_joueur_et_gw(self):
        c = _contract()
        self.assertTrue(c.rows)
        for r in c.rows[:20]:
            self.assertIsInstance(r.player_id, int)
            self.assertIn(r.gw, c.horizon)
            for champ in ("ep", "p0", "p60", "ep_if_start"):
                self.assertIsInstance(getattr(r, champ), float)
            self.assertEqual(set(r.scenarios), set(c.scenario_names))
            self.assertIn("appearance", r.components)
            self.assertTrue(r.confidence)
            self.assertIn("minutes", r.provenance)
        self.assertTrue(c.as_of and c.model_version and c.contract_version)

    def test_aller_retour_json_sans_perte(self):
        c = _contract()
        with tempfile.TemporaryDirectory() as tmp:
            path = c.save(Path(tmp) / "proj.json")
            relu = ProjectionSet.load(path)
        self.assertEqual(relu.to_dict(), c.to_dict())
        self.assertEqual(relu.horizon, c.horizon)
        self.assertEqual([r.gw for r in relu.rows[:10]], [r.gw for r in c.rows[:10]])

    def test_le_fichier_ne_contient_aucune_donnee_brute(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _contract().save(Path(tmp) / "proj.json")
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        for interdit in ("bootstrap", "fixtures", "live", "history_past",
                         "my", "rivals", "standings"):
            self.assertNotIn(interdit, data,
                             f"le contrat transporte des données brutes : {interdit}")


class OptimisationSansDonneesBrutesTests(unittest.TestCase):
    """L'optimiseur ne doit consommer que le contrat."""

    def test_meme_effectif_depuis_un_contrat_releu(self):
        c = _contract()
        with tempfile.TemporaryDirectory() as tmp:
            relu = ProjectionSet.load(c.save(Path(tmp) / "p.json"))
        a = initial.build_from_contract(c)
        b = initial.build_from_contract(relu)
        self.assertEqual([p["id"] for p in a["squad"]], [p["id"] for p in b["squad"]])
        self.assertAlmostEqual(a["value4"], b["value4"], places=9)
        self.assertEqual(a["armband"]["captain"]["id"], b["armband"]["captain"]["id"])
        self.assertEqual(a["min_overlap"], b["min_overlap"])

    def test_le_rapport_est_identique_depuis_un_contrat_releu(self):
        c = _contract()
        with tempfile.TemporaryDirectory() as tmp:
            relu = ProjectionSet.load(c.save(Path(tmp) / "p.json"))
        strip = lambda t: "\n".join(l for l in t.splitlines()
                                    if not l.startswith("Généré le"))
        self.assertEqual(strip(render_initial(initial.build_from_contract(c))),
                         strip(render_initial(initial.build_from_contract(relu))))

    def test_les_lignes_de_l_optimiseur_ne_portent_aucune_donnee_brute(self):
        rows = _contract().rows_for("central")
        autorises = {"id", "web_name", "element_type", "team", "now_cost",
                     "p_play", "p60", "p0", "minutes_basis", "minutes_confidence",
                     "eps", "ep_by_gw", "ep_if_start_by_gw", "components_by_gw", "ep4"}
        self.assertTrue(rows)
        for r in rows[:5]:
            self.assertEqual(set(r) - autorises, set())


class VerdictQualiteTests(unittest.TestCase):
    """Les trois états doivent être atteignables et déterministes."""

    def test_verdict_accepte(self):
        c = _contract()
        c2 = ProjectionSet.from_dict(c.to_dict())
        c2.data_confidence = "moyen-haut"
        v = quality.assess(c2, min_overlap=15,
                           squad_facts={"cost": 995, "budget": 1000,
                                        "captain_p60": 0.8, "captain_name": "X"},
                           baseline_overlap=9)
        self.assertEqual(v.state, quality.ACCEPTED)
        self.assertTrue(v.publishable)
        self.assertEqual(v.label, "recommandation")

    def test_verdict_avertissement(self):
        c = _contract()          # confiance « moyen » : référence d'équipe absente
        v = quality.assess(c, min_overlap=15,
                           squad_facts={"cost": 995, "budget": 1000,
                                        "captain_p60": 0.8, "captain_name": "X"},
                           baseline_overlap=9)
        self.assertEqual(v.state, quality.WARNING)
        self.assertTrue(v.publishable)
        self.assertEqual(v.label, "recommandation")

    def test_verdict_bloque(self):
        c = _contract()
        v = quality.assess(c, min_overlap=15,
                           squad_facts={"cost": 995, "budget": 1000,
                                        "captain_p60": 0.10, "captain_name": "X"})
        self.assertEqual(v.state, quality.BLOCKED)
        self.assertFalse(v.publishable)
        self.assertEqual(v.label, "candidat technique")

    def test_verdict_deterministe(self):
        c = _contract()
        a = quality.assess(c, min_overlap=13, squad_facts={"cost": 990})
        b = quality.assess(c, min_overlap=13, squad_facts={"cost": 990})
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_anomalies_detectees(self):
        c = _contract()
        cas = [
            ({"cost": 700, "budget": 1000}, "budget_utilise"),
            ({"cost": 990, "captain_p60": 0.05, "captain_name": "X"}, "capitaine_plausible"),
            ({"cost": 990, "size_ok": False}, "legalite_fpl"),
        ]
        for facts, cle in cas:
            with self.subTest(cle=cle):
                v = quality.assess(c, min_overlap=15, squad_facts=facts)
                bloquants = [k.key for k in v.checks if k.state == quality.BLOCKED]
                self.assertIn(cle, bloquants)


class BlocageEquipeInstableTests(unittest.TestCase):
    """Une équipe instable est bloquée, mais reste calculée pour le diagnostic."""

    def test_instabilite_bloque_la_publication(self):
        v = quality.assess(_contract(),
                           min_overlap=quality.STABILITY_MIN_OVERLAP - 1,
                           squad_facts={"cost": 990, "captain_p60": 0.8})
        self.assertEqual(v.state, quality.BLOCKED)
        self.assertIn("stabilite_top15",
                      [c.key for c in v.checks if c.state == quality.BLOCKED])

    def test_l_effectif_reste_calculable_et_nomme_candidat_technique(self):
        rec = initial.build_from_contract(_contract())
        rec = dict(rec, verdict=quality.assess(
            _contract(), min_overlap=5, squad_facts={"cost": 990, "captain_p60": 0.9}))
        self.assertEqual(len(rec["squad"]), 15)       # calculé malgré le blocage
        texte = render_initial(rec)
        self.assertIn("CANDIDAT TECHNIQUE", texte)
        self.assertIn("Candidat technique (15 joueurs)", texte)
        self.assertNotIn("## Effectif recommandé", texte)

    def test_stabilite_utilise_un_selecteur_injecte(self):
        # L'évaluation ne connaît que la signature du sélecteur : on peut lui en
        # passer un faux, preuve qu'elle ne dépend pas de l'optimiseur réel.
        appels = []

        def faux_select(rows, gws):
            appels.append(len(rows))
            return rows[:15], 42.0

        backend = SelectionBackend(select=faux_select, value=lambda s, g: 1.0,
                                   legality=lambda s: {}, decisions=lambda s, g: {})
        c = _contract()
        pool_ids = [r["id"] for r in opt_initial.build_pool(c.rows_for("central"))]
        rows, overlap = stability.top15_stability(c, backend, set(pool_ids[:15]), pool_ids)
        self.assertEqual(len(rows), len(c.scenario_names))
        self.assertEqual(len(appels), len(c.scenario_names))
        self.assertLessEqual(overlap, 15)


class DirectionDesDependancesTests(unittest.TestCase):
    """La direction des dépendances est vérifiée sur le code source lui-même."""

    def _imports(self, package):
        found = set()
        for path in (ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    found.add((node.level, node.module))
                elif isinstance(node, ast.ImportFrom):
                    found.add((node.level, ""))
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        found.add((0, a.name))
        return found

    def test_forecasting_ne_depend_ni_de_evaluation_ni_de_optimization(self):
        for _, mod in self._imports("forecasting"):
            self.assertNotIn("evaluation", mod)
            self.assertNotIn("optimization", mod)

    def test_evaluation_ne_depend_pas_de_optimization(self):
        for _, mod in self._imports("evaluation"):
            self.assertNotIn("optimization", mod,
                             "l'évaluation doit recevoir un SelectionBackend, "
                             "pas importer l'optimiseur")

    def test_optimization_ne_lit_aucune_donnee_brute(self):
        for _, mod in self._imports("optimization"):
            for interdit in ("collect", "api", "demo", "forecasting"):
                self.assertNotIn(interdit, mod,
                                 f"l'optimiseur ne doit pas importer {interdit}")

    def test_optimization_ne_mentionne_pas_les_cles_du_snapshot(self):
        source = "\n".join(p.read_text(encoding="utf-8")
                           for p in (ROOT / "optimization").rglob("*.py"))
        for cle in ('"bootstrap"', '"elements"', '"fixtures"', '"live"',
                    '"history_past"', 'parsed['):
            self.assertNotIn(cle, source,
                             f"l'optimiseur manipule une clé de snapshot : {cle}")


class NonRegressionDesCommandesTests(unittest.TestCase):
    """Les commandes publiques existantes continuent de fonctionner."""

    def test_commandes_publiques(self):
        from fpl_advisor.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["demo", "--data-dir", tmp]), 0)
            self.assertEqual(main(["initial-squad", "--demo", "--data-dir", tmp]), 0)
            self.assertEqual(main(["initial-bench", "--demo", "--data-dir", tmp]), 0)
            reports = Path(tmp) / "reports"
            self.assertTrue(list(reports.glob("GW3-recommandation-*.md")))
            self.assertTrue(list(reports.glob("GW1-effectif-initial-*.md")))
            self.assertTrue(list(reports.glob("GW1-banc-essai-initial.json")))

    def test_figeage_puis_relecture_par_la_cli(self):
        from fpl_advisor.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            proj = str(Path(tmp) / "proj.json")
            self.assertEqual(main(["initial-squad", "--demo", "--data-dir", tmp,
                                   "--freeze-projections", proj]), 0)
            self.assertTrue(Path(proj).exists())
            self.assertEqual(main(["initial-squad", "--from-projections", proj,
                                   "--data-dir", tmp]), 0)

    def test_les_facades_historiques_repondent_toujours(self):
        from fpl_advisor import bench, model, priors, team
        self.assertTrue(callable(model.project_player))
        self.assertTrue(callable(model.minutes_model))
        self.assertTrue(callable(team.pick_xi))
        self.assertTrue(callable(team.transfer_scan))
        self.assertTrue(callable(priors.shrink))
        self.assertTrue(callable(bench.build_bench))
        self.assertTrue(callable(wiring.selection_backend))


if __name__ == "__main__":
    unittest.main()
