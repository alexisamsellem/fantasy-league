# -*- coding: utf-8 -*-
"""Tests de fumée du protocole J0 — hors ligne, aucune requête réseau."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import j0_verification as j0  # noqa: E402


class SnapshotStoreTests(unittest.TestCase):
    def test_deux_runs_ne_partagent_jamais_un_repertoire(self):
        with tempfile.TemporaryDirectory() as td:
            s1 = j0.SnapshotStore(td)
            s2 = j0.SnapshotStore(td)  # même seconde probable → suffixe attendu
            self.assertNotEqual(s1.dir, s2.dir)
            self.assertTrue(s1.dir.exists() and s2.dir.exists())

    def test_meme_nom_deux_fois_sans_ecrasement_et_manifeste_complet(self):
        with tempfile.TemporaryDirectory() as td:
            s = j0.SnapshotStore(td)
            p1 = s.save("bootstrap-static", b'{"a": 1}', "https://x/api/1", 200)
            p2 = s.save("bootstrap-static", b'{"a": 2}', "https://x/api/1", 200)
            self.assertNotEqual(p1, p2)
            self.assertEqual(p1.read_bytes(), b'{"a": 1}')  # le premier est intact
            manifest = json.loads((s.dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest), 2)
            for entry in manifest:
                for champ in ("file", "url", "retrieved_at", "http_status", "sha256"):
                    self.assertIn(champ, entry)
            self.assertNotEqual(manifest[0]["sha256"], manifest[1]["sha256"])


class TraceProbanteTests(unittest.TestCase):
    def _statut(self, manual):
        par_cle = {c.cid: c for c in j0.manual_checks(manual)}
        return par_cle["vice_zero_minute"].status

    def test_true_sans_trace_reste_R(self):
        self.assertEqual(self._statut({"vice_zero_minute": {"confirmed": True}}), "R")

    def test_true_avec_trace_complete_donne_F(self):
        manual = {"vice_zero_minute": {
            "confirmed": True,
            "verified_on": "2026-08-22",
            "page_title_or_section": "Captains",
            "confirmed_statement": "If your captain plays 0 minutes…",
        }}
        self.assertEqual(self._statut(manual), "F")

    def test_gabarit_vide_tout_en_R(self):
        checks = j0.manual_checks({})
        self.assertTrue(checks)
        self.assertTrue(all(c.status == "R" for c in checks))


if __name__ == "__main__":
    unittest.main()
