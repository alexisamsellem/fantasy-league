# -*- coding: utf-8 -*-
"""Tests des scripts que GitHub Actions exécute — hors ligne, aucun envoi.

Ces trois scripts tournent sans personne devant l'écran. Une erreur y est
silencieuse : pas de mail, ou pire, un mail vide au moment où il compte.

  1. `envoyer_rapport` construit le message : destinataires, pièces jointes,
     et un garde-fou de taille ;
  2. `prochaine_deadline` choisit la BONNE deadline — la première future,
     jamais une passée ;
  3. `calibrer_en_attente` garde, pour une journée figée plusieurs fois, le
     figeage le plus tardif : c'est celui qui portait le plus d'information.
"""

import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))


def _charge(nom):
    """Les scripts ne sont pas un paquet : on les charge par chemin."""
    chemin = RACINE / "scripts" / f"{nom}.py"
    spec = importlib.util.spec_from_file_location(f"scripts_{nom}", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


envoyer = _charge("envoyer_rapport")
deadline = _charge("prochaine_deadline")
calibrer = _charge("calibrer_en_attente")


class MessageTests(unittest.TestCase):
    def test_les_entetes_portent_l_expediteur_et_le_destinataire(self):
        msg = envoyer.construire("Sujet", "corps", [], "moi@x.fr", "toi@y.fr")
        self.assertEqual(msg["Subject"], "Sujet")
        self.assertEqual(msg["From"], "moi@x.fr")
        self.assertEqual(msg["To"], "toi@y.fr")

    def test_une_piece_jointe_garde_son_nom_de_fichier(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "GW2-audit.md"
            f.write_text("# audit", encoding="utf-8")
            msg = envoyer.construire("S", "corps", [str(f)], "a@x", "b@y")
            noms = [p.get_filename() for p in msg.iter_attachments()]
            self.assertEqual(noms, ["GW2-audit.md"])

    def test_une_piece_jointe_absente_ne_fait_pas_echouer_l_envoi(self):
        """Le rapport d'audit peut manquer — son échec est toléré dans le
        workflow. Le mail de la semaine doit partir quand même."""
        msg = envoyer.construire("S", "corps", ["/inexistant.md"], "a@x", "b@y")
        self.assertEqual(list(msg.iter_attachments()), [])
        self.assertIn("corps", msg.get_content())

    def test_un_corps_vide_ne_produit_pas_un_mail_muet(self):
        msg = envoyer.construire("S", "", [], "a@x", "b@y")
        self.assertIn("vide", msg.get_content())

    def test_un_corps_enorme_est_tronque(self):
        msg = envoyer.construire("S", "x" * (envoyer.MAX_CORPS + 5000), [],
                                 "a@x", "b@y")
        self.assertLessEqual(len(msg.get_content().strip()), envoyer.MAX_CORPS)


class DeadlineTests(unittest.TestCase):
    def _events(self):
        return [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"},
                {"id": 2, "deadline_time": "2026-08-28T17:30:00Z"},
                {"id": 3, "deadline_time": "2026-09-12T17:30:00Z"}]

    def test_la_premiere_deadline_future_est_choisie(self):
        maintenant = datetime(2026, 8, 27, 17, 30, tzinfo=timezone.utc)
        gw, dt, heures = deadline.prochaine(self._events(), maintenant)
        self.assertEqual(gw, 2)
        self.assertAlmostEqual(heures, 24.0, places=6)

    def test_une_deadline_passee_n_est_jamais_rendue(self):
        maintenant = datetime(2026, 8, 29, 0, 0, tzinfo=timezone.utc)
        gw, _, _ = deadline.prochaine(self._events(), maintenant)
        self.assertEqual(gw, 3, "la GW2 est passée, il faut la suivante")

    def test_saison_terminee_n_est_pas_une_erreur(self):
        maintenant = datetime(2027, 6, 1, tzinfo=timezone.utc)
        self.assertEqual(deadline.prochaine(self._events(), maintenant),
                         (None, None, None))

    def test_une_deadline_illisible_est_ignoree_pas_devinee(self):
        events = [{"id": 1, "deadline_time": "pas une date"},
                  {"id": 2, "deadline_time": "2026-08-28T17:30:00Z"},
                  {"id": 3}]
        maintenant = datetime(2026, 8, 27, tzinfo=timezone.utc)
        gw, _, _ = deadline.prochaine(events, maintenant)
        self.assertEqual(gw, 2)


class FigeagesTests(unittest.TestCase):
    class _Faux:
        def __init__(self, gw, as_of):
            self.gw, self.as_of = gw, as_of

    def _dossier(self, fichiers):
        d = tempfile.mkdtemp()
        for nom in fichiers:
            (Path(d) / nom).write_text("{}", encoding="utf-8")
        return d

    def test_pour_une_meme_gw_le_figeage_le_plus_tardif_gagne(self):
        """Un témoin du mercredi et l'officiel du vendredi coexistent. C'est le
        vendredi qui compte : il portait les conférences de presse."""
        d = self._dossier(["projections-GW2-mercredi.json",
                           "projections-GW2-vendredi.json"])
        dates = {"projections-GW2-mercredi.json": "2026-08-26T10:00:00Z",
                 "projections-GW2-vendredi.json": "2026-08-28T12:00:00Z"}
        original = calibrer.ProjectionSet.load
        calibrer.ProjectionSet.load = staticmethod(
            lambda p: FigeagesTests._Faux(2, dates[Path(p).name]))
        try:
            trouves = calibrer.figeages(d)
        finally:
            calibrer.ProjectionSet.load = original
        self.assertEqual(len(trouves), 1)
        self.assertEqual(trouves[0][0].name, "projections-GW2-vendredi.json")

    def test_les_journees_sortent_dans_l_ordre(self):
        d = self._dossier(["projections-GW5.json", "projections-GW2.json"])
        gws = {"projections-GW5.json": 5, "projections-GW2.json": 2}
        original = calibrer.ProjectionSet.load
        calibrer.ProjectionSet.load = staticmethod(
            lambda p: FigeagesTests._Faux(gws[Path(p).name], "2026-01-01T00:00:00Z"))
        try:
            trouves = calibrer.figeages(d)
        finally:
            calibrer.ProjectionSet.load = original
        self.assertEqual([c.gw for _, c in trouves], [2, 5])

    def test_un_fichier_illisible_est_signale_pas_fatal(self):
        d = self._dossier(["projections-GW2.json"])
        original = calibrer.ProjectionSet.load

        def _casse(p):
            raise ValueError("JSON tronqué")

        calibrer.ProjectionSet.load = staticmethod(_casse)
        try:
            self.assertEqual(calibrer.figeages(d), [])
        finally:
            calibrer.ProjectionSet.load = original

    def test_un_dossier_vide_ne_plante_pas(self):
        self.assertEqual(calibrer.figeages(self._dossier([])), [])


if __name__ == "__main__":
    unittest.main()
