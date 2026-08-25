# -*- coding: utf-8 -*-
"""Tests de la référence d'équipe — hors ligne, aucune requête.

Ce que ces tests protègent : le fichier de référence n'échoue jamais
bruyamment. Un club dont le nom ne correspond pas au bootstrap FPL tombe en
silence dans le panier « promu » et reçoit un prior générique. Un fichier à
moitié faux est donc pire qu'un fichier absent — absent, au moins, c'est
signalé. Il faut que ce défaut soit visible partout : dans le rapport de
disponibilité, dans le contrôle qualité, et dans le script qui produit le
fichier.
"""

import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RACINE = Path(__file__).resolve().parents[1]

from fpl_advisor import weekly                                 # noqa: E402
from fpl_advisor.demo import build_parsed                      # noqa: E402
from fpl_advisor.evaluation import quality                     # noqa: E402
from fpl_advisor.forecasting import priors                     # noqa: E402


def _script():
    spec = importlib.util.spec_from_file_location(
        "build_team_priors", RACINE / "scripts" / "build_team_priors.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CLUBS = ["Alpha", "Bravo", "Citrus", "Delta", "Echo", "Foxtrot"]


def _reference(tmp, lignes):
    chemin = Path(tmp) / "team_priors.csv"
    with open(chemin, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["team_name", "goals_for", "goals_against", "matches", "division"])
        w.writerows(lignes)
    return str(chemin)


class AppariementVisibleTests(unittest.TestCase):
    def _rapport(self, lignes):
        parsed = build_parsed()
        with tempfile.TemporaryDirectory() as tmp:
            parsed["team_ref"] = priors.load_team_reference(
                _reference(tmp, lignes), parsed["bootstrap"]["teams"])
        return next(r for r in priors.availability_report(parsed)
                    if r["key"] == "team_reference")

    def test_tous_apparies(self):
        r = self._rapport([[c, 60, 40, 38, 1] for c in CLUBS])
        self.assertEqual((r["apparies"], r["promus"]), (6, 0))
        self.assertTrue(r["present"])
        self.assertIn("6/6 clubs appariés", r["detail"])

    def test_noms_qui_ne_collent_pas_comptes_comme_promus(self):
        """Le cœur du piège : aucune erreur, juste des priors génériques."""
        r = self._rapport([[c + " FC", 60, 40, 38, 1] for c in CLUBS])
        self.assertEqual((r["apparies"], r["promus"]), (0, 6))
        self.assertFalse(r["present"])

    def test_fichier_absent(self):
        parsed = dict(build_parsed(), team_ref=None)
        r = next(x for x in priors.availability_report(parsed)
                 if x["key"] == "team_reference")
        self.assertEqual(r["detail"], "fichier absent")
        self.assertFalse(r["present"])


class ControleQualiteTests(unittest.TestCase):
    def _contrat(self, lignes):
        parsed = build_parsed()
        with tempfile.TemporaryDirectory() as tmp:
            parsed["team_ref"] = priors.load_team_reference(
                _reference(tmp, lignes), parsed["bootstrap"]["teams"])
        return weekly.build_contract(parsed)

    def _etat(self, contract):
        v = quality.assess_weekly(contract, {})
        return next((c.state for c in v.checks if c.key == "reference_equipe"), None)

    def test_reference_saine_acceptee(self):
        self.assertEqual(self._etat(self._contrat([[c, 60, 40, 38, 1]
                                                   for c in CLUBS])),
                         quality.ACCEPTED)

    def test_trop_de_promus_avertit(self):
        # Un seul club apparié : les cinq autres tombent en « promus ».
        etat = self._etat(self._contrat([["Alpha", 60, 40, 38, 1]]))
        self.assertEqual(etat, quality.WARNING)

    def test_aucun_controle_quand_le_fichier_est_absent(self):
        """L'absence est déjà dite par couverture_donnees : pas de doublon."""
        contract = weekly.build_contract(build_parsed())
        self.assertIsNone(self._etat(contract))

    def test_le_seuil_suit_la_realite_du_championnat(self):
        self.assertEqual(quality.MAX_PROMUS_PLAUSIBLE, 4)


class ScriptDeConstructionTests(unittest.TestCase):
    E0 = [
        {"HomeTeam": "Man United", "AwayTeam": "Tottenham", "FTHG": "2", "FTAG": "1"},
        {"HomeTeam": "Tottenham", "AwayTeam": "Man United", "FTHG": "3", "FTAG": "0"},
        {"HomeTeam": "Man United", "AwayTeam": "Reléguéville", "FTHG": "1", "FTAG": "1"},
        {"HomeTeam": "Man United", "AwayTeam": "Tottenham", "FTHG": "", "FTAG": ""},
    ]

    def _ecrire_e0(self, tmp, lignes=None):
        chemin = Path(tmp) / "E0.csv"
        lignes = self.E0 if lignes is None else lignes
        with open(chemin, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
            w.writeheader()
            w.writerows(lignes)
        return str(chemin)

    def _snapshot(self, tmp, noms):
        run = Path(tmp) / "snapshots" / "20260822T180000Z"
        run.mkdir(parents=True)
        (run / "bootstrap-static.json").write_text(json.dumps(
            {"teams": [{"id": i, "name": n, "short_name": n[:3].upper()}
                       for i, n in enumerate(noms, 1)]}), encoding="utf-8")
        return str(tmp)

    def test_agregation_domicile_et_exterieur(self):
        m = _script()
        with tempfile.TemporaryDirectory() as tmp:
            stats = m.agrege(self._ecrire_e0(tmp))
        # Man United : 2+0+1 marqués, 1+3+1 encaissés, 3 matchs joués.
        self.assertEqual(stats["Man United"], {"gf": 3, "ga": 5, "m": 3})
        self.assertEqual(stats["Tottenham"], {"gf": 4, "ga": 2, "m": 2})

    def test_un_match_non_joue_est_ignore(self):
        m = _script()
        with tempfile.TemporaryDirectory() as tmp:
            stats = m.agrege(self._ecrire_e0(tmp))
        self.assertEqual(stats["Man United"]["m"], 3)   # 4 lignes, 1 sans score

    def test_les_alias_connus_sont_apparies(self):
        m = _script()
        equipes = [{"name": "Man Utd", "short_name": "MUN"},
                   {"name": "Spurs", "short_name": "TOT"}]
        trouves, doutes = m.apparie(["Man United", "Tottenham"], equipes)
        self.assertEqual(trouves, {"Man United": "Man Utd", "Tottenham": "Spurs"})
        self.assertEqual(doutes, [])

    def test_un_club_relegue_est_ignore_sans_bruit(self):
        m = _script()
        trouves, doutes = m.apparie(["Reléguéville"], [{"name": "Man Utd"}])
        self.assertEqual((trouves, doutes), ({}, []))

    def test_le_script_refuse_d_ecrire_sur_un_rapprochement_incertain(self):
        """Un nom proche mais pas identique n'est jamais deviné en silence :
        le script le montre et s'arrête sans rien écrire."""
        m = _script()
        proches = [{"HomeTeam": "Brentfrd", "AwayTeam": "Tottenham",
                    "FTHG": "1", "FTAG": "0"}]
        with tempfile.TemporaryDirectory() as tmp:
            data = self._snapshot(tmp, ["Brentford", "Spurs"])
            sortie = str(Path(tmp) / "ref.csv")
            tampon = io.StringIO()
            with redirect_stdout(tampon):
                code = m.main(["--e0", self._ecrire_e0(tmp, proches),
                               "--data-dir", data, "--out", sortie])
            self.assertEqual(code, 1)
            self.assertFalse(Path(sortie).exists())
            self.assertIn("INCERTAINS", tampon.getvalue())
            self.assertIn("Brentfrd", tampon.getvalue())

            # Relancé avec l'accord explicite, il écrit et le dit.
            tampon = io.StringIO()
            with redirect_stdout(tampon):
                code = m.main(["--e0", self._ecrire_e0(tmp, proches),
                               "--data-dir", data, "--out", sortie,
                               "--accepter-approximations"])
            self.assertEqual(code, 0)
            self.assertTrue(Path(sortie).exists())
            self.assertIn("Rapprochement accepté", tampon.getvalue())

    def test_bout_en_bout_et_relecture_par_le_moteur(self):
        m = _script()
        with tempfile.TemporaryDirectory() as tmp:
            data = self._snapshot(tmp, ["Man Utd", "Spurs", "Promu FC"])
            sortie = str(Path(tmp) / "ref.csv")
            tampon = io.StringIO()
            with redirect_stdout(tampon):
                code = m.main(["--e0", self._ecrire_e0(tmp), "--data-dir", data,
                               "--out", sortie])
            self.assertEqual(code, 0)
            self.assertIn("2/3 clubs FPL appariés", tampon.getvalue())
            self.assertIn("Promu FC", tampon.getvalue())
            # Le fichier produit doit être relu tel quel par le moteur.
            equipes = [{"id": 1, "name": "Man Utd", "short_name": "MUN"},
                       {"id": 2, "name": "Spurs", "short_name": "TOT"},
                       {"id": 3, "name": "Promu FC", "short_name": "PRO"}]
            ref = priors.load_team_reference(sortie, equipes)
            self.assertFalse(ref[1]["promoted"])
            self.assertFalse(ref[2]["promoted"])
            self.assertTrue(ref[3]["promoted"])
            self.assertAlmostEqual(ref[1]["gf90"], 3 / 3)
            self.assertAlmostEqual(ref[2]["ga90"], 2 / 2)

    def test_sans_snapshot_le_script_s_arrete(self):
        m = _script()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                m.main(["--e0", self._ecrire_e0(tmp), "--data-dir", tmp])
        self.assertIn("collecte", str(ctx.exception))

    def test_un_csv_hors_format_est_refuse(self):
        m = _script()
        with tempfile.TemporaryDirectory() as tmp:
            mauvais = Path(tmp) / "autre.csv"
            mauvais.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                m.agrege(str(mauvais))
        self.assertIn("football-data.co.uk", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
