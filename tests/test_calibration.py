# -*- coding: utf-8 -*-
"""Tests de la mesure de calibration — hors ligne, aucune requête.

Ce que ces tests protègent :
  1. le score de compétence est NÉGATIF quand le moteur fait pire que le taux
     de base — c'est le seul verdict qui compte, il ne doit jamais être adouci ;
  2. les joueurs sans match et les joueurs non observés sont exclus et comptés,
     jamais traités comme des absences prédites ;
  3. la mesure refuse de conclure sur une journée non jouée ou un échantillon
     trop petit ;
  4. la commande refuse de noter des projections recalculées après coup.
"""

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import collect, weekly                       # noqa: E402
from fpl_advisor.demo import build_parsed                     # noqa: E402
from fpl_advisor.evaluation import calibration                # noqa: E402
from fpl_advisor.report import render_calibration             # noqa: E402


def _contract():
    if not hasattr(_contract, "cache"):
        _contract.cache = weekly.build_contract(build_parsed())
    return _contract.cache


def _minutes_from(contract, mode, seed=1):
    """Minutes fabriquées pour la GW de décision."""
    rng = random.Random(seed)
    out = {}
    for r in contract.rows:
        if r.gw != contract.gw:
            continue
        if mode == "calibre":          # tirées des probabilités annoncées
            u = rng.random()
            out[r.player_id] = 90 if u < r.p60 else (20 if u < r.p_play else 0)
        elif mode == "inverse":        # exactement le contraire de l'annonce
            out[r.player_id] = 0 if r.p60 > 0.5 else 90
        else:                          # personne ne joue
            out[r.player_id] = 0
    return out


class ScoreDeCompetenceTests(unittest.TestCase):
    def test_un_moteur_calibre_bat_le_taux_de_base(self):
        c = _contract()
        res = calibration.assess(c, _minutes_from(c, "calibre"))
        self.assertGreater(res["metriques"]["p60"]["competence"], 0.1)

    def test_un_moteur_a_l_envers_est_declare_en_echec(self):
        """Le verdict doit dire ÉCHEC, sans euphémisme."""
        c = _contract()
        res = calibration.assess(c, _minutes_from(c, "inverse"))
        self.assertLess(res["metriques"]["p60"]["competence"], 0)
        self.assertIn("ÉCHEC", res["conclusion"])
        self.assertIn("interdit de le présenter comme calibré", res["conclusion"])

    def test_brier_et_reference_sur_des_cas_connus(self):
        self.assertAlmostEqual(calibration.brier([(1.0, 1.0), (0.0, 0.0)]), 0.0)
        self.assertAlmostEqual(calibration.brier([(1.0, 0.0)]), 1.0)
        self.assertAlmostEqual(calibration.brier([(0.5, 1.0), (0.5, 0.0)]), 0.25)
        self.assertIsNone(calibration.brier([]))


class FiabiliteTests(unittest.TestCase):
    def test_une_probabilite_de_1_tombe_dans_la_derniere_tranche(self):
        rows = calibration.reliability([(1.0, 1.0)])
        self.assertEqual(rows[-1]["n"], 1)
        self.assertEqual(sum(r["n"] for r in rows), 1)

    def test_les_tranches_vides_sont_conservees(self):
        rows = calibration.reliability([(0.05, 0.0)])
        self.assertEqual(len(rows), len(calibration.BUCKETS))
        self.assertEqual([r["n"] for r in rows], [1, 0, 0, 0, 0])
        self.assertIsNone(rows[1]["annonce"])

    def test_l_ecart_dit_le_sens_de_l_erreur(self):
        # Annoncé 10 %, observé 100 % : trop prudent, écart positif.
        rows = calibration.reliability([(0.1, 1.0)])
        self.assertAlmostEqual(rows[0]["ecart"], 0.9, places=6)


class ExclusionsTests(unittest.TestCase):
    def test_les_joueurs_sans_match_sont_exclus_et_comptes(self):
        c = _contract()
        cibles = [r for r in c.rows if r.gw == c.gw][:5]
        for r in cibles:
            r.n_fixtures = 0
        try:
            res = calibration.assess(c, _minutes_from(c, "calibre"))
            m = res["metriques"]["p60"]
            self.assertEqual(m["sans_match"], 5)
            self.assertEqual(m["n"] + m["sans_match"],
                             sum(1 for r in c.rows if r.gw == c.gw))
        finally:
            for r in cibles:
                r.n_fixtures = 1

    def test_les_joueurs_non_observes_sont_exclus_et_comptes(self):
        c = _contract()
        mins = _minutes_from(c, "calibre")
        for pid in list(mins)[:3]:
            del mins[pid]
        m = calibration.assess(c, mins)["metriques"]["p60"]
        self.assertEqual(m["non_observes"], 3)


class RefusDeConclureTests(unittest.TestCase):
    def test_journee_non_jouee_refusee(self):
        with self.assertRaises(SystemExit) as ctx:
            calibration.assess(_contract(), {})
        self.assertIn("n'est pas jouée", str(ctx.exception))

    def test_gw_hors_horizon_refusee(self):
        c = _contract()
        with self.assertRaises(SystemExit) as ctx:
            calibration.assess(c, {1: 90}, gw=max(c.horizon) + 5)
        self.assertIn("absente de l'horizon", str(ctx.exception))

    def test_echantillon_trop_petit_ne_conclut_pas(self):
        c = _contract()
        mins = dict(list(_minutes_from(c, "calibre").items())[:10])
        res = calibration.assess(c, mins)
        self.assertFalse(res["metriques"]["p60"]["assez"])
        self.assertIn("insuffisant", res["conclusion"])


class MinutesObserveesTests(unittest.TestCase):
    def _snapshot(self, tmp, nom, minutes):
        run = Path(tmp) / "snapshots" / nom
        run.mkdir(parents=True)
        (run / "event-2-live.json").write_text(json.dumps(
            {"elements": [{"id": i, "stats": {"minutes": m}}
                          for i, m in minutes.items()]}), encoding="utf-8")
        return run

    def test_une_gw_ouverte_mais_non_jouee_rend_vide(self):
        """Le fichier live existe dès l'ouverture de la GW, rempli de zéros."""
        with tempfile.TemporaryDirectory() as tmp:
            self._snapshot(tmp, "20260828T120000Z", {1: 0, 2: 0})
            self.assertEqual(collect.observed_minutes(tmp, 2), {})

    def test_le_snapshot_le_plus_recent_qui_contient_la_journee_gagne(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._snapshot(tmp, "20260828T120000Z", {1: 0, 2: 0})
            self._snapshot(tmp, "20260831T120000Z", {1: 90, 2: 12})
            self.assertEqual(collect.observed_minutes(tmp, 2), {1: 90, 2: 12})

    def test_gw_absente_ou_repertoire_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(collect.observed_minutes(tmp, 2), {})
            self._snapshot(tmp, "20260831T120000Z", {1: 90})
            self.assertEqual(collect.observed_minutes(tmp, 7), {})
            self.assertEqual(collect.observed_minutes(tmp, None), {})


class RapportEtCliTests(unittest.TestCase):
    def test_le_rapport_porte_les_avertissements_decisifs(self):
        c = _contract()
        texte = render_calibration(calibration.assess(c, _minutes_from(c, "calibre")))
        for attendu in ("point-in-time", "DONNÉES SYNTHÉTIQUES",
                        "négatif = pire que ne rien savoir",
                        "Ce que ce document ne dit pas",
                        "Aucun paramètre du moteur ne doit être ajusté"):
            self.assertIn(attendu, texte)

    def test_la_commande_refuse_des_projections_recalculees(self):
        from fpl_advisor.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                main(["calibrate", "--data-dir", tmp])
        self.assertIn("FIGÉES AVANT la deadline", str(ctx.exception))

    def test_bout_en_bout_par_la_cli(self):
        from fpl_advisor.__main__ import main
        c = _contract()
        with tempfile.TemporaryDirectory() as tmp:
            proj = str(Path(tmp) / "proj.json")
            c.save(proj)
            run = Path(tmp) / "snapshots" / "20260901T120000Z"
            run.mkdir(parents=True)
            (run / f"event-{c.gw}-live.json").write_text(json.dumps(
                {"elements": [{"id": pid, "stats": {"minutes": m}}
                              for pid, m in _minutes_from(c, "calibre").items()]}),
                encoding="utf-8")
            self.assertEqual(
                main(["calibrate", "--from-projections", proj, "--data-dir", tmp]), 0)
            self.assertTrue(list((Path(tmp) / "reports")
                                 .glob(f"GW{c.gw}-calibration-*.md")))


if __name__ == "__main__":
    unittest.main()
