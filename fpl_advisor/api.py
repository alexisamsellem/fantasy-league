# -*- coding: utf-8 -*-
"""Accès HTTP en lecture seule + snapshots immuables (même design que J0, gelé).

Garanties : GET uniquement, endpoints publics, aucune authentification, aucun
cookie. Chaque exécution de collecte écrit dans data/snapshots/<horodatage UTC>/
avec un manifeste (fichier, URL, retrieved_at, statut HTTP, SHA-256).
"""

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (fpl-advisor v0; lecture seule)"}


class SnapshotStore:
    """Un répertoire immuable par exécution, jamais réutilisé ni écrasé."""

    def __init__(self, data_dir):
        root = Path(data_dir) / "snapshots"
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        cand, n = root / run_id, 2
        while cand.exists():
            cand, n = root / f"{run_id}-{n}", n + 1
        cand.mkdir(parents=True)
        self.dir, self.entries = cand, []

    def save(self, name, raw, url, http_status):
        fname, n = f"{name}.json", 2
        while (self.dir / fname).exists():
            fname, n = f"{name}-{n}.json", n + 1
        (self.dir / fname).write_bytes(raw)
        self.entries.append({
            "file": fname, "url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "http_status": http_status,
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
        (self.dir / "manifest.json").write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.dir / fname


def get_json(path, store=None, name=None):
    """GET public. Snapshot si un store est fourni. Retourne (objet, erreur)."""
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw, status = resp.read(), resp.status
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return None, f"échec GET {url} : {e}"
    if store is not None:
        store.save(name or "reponse", raw, url, status)
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"réponse non-JSON {url} : {e}"


def load_config(path="config.local.json"):
    """Config locale (jamais commitée) : {"team_id": int, "league_id": int}."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"Configuration absente : {path}.\n"
            "Copier config.example.json vers config.local.json et y mettre "
            "team_id et league_id (voir docs/guide-j0.md pour les retrouver). "
            "Ce fichier est ignoré par Git et ne doit jamais être commité.")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    for k in ("team_id", "league_id"):
        v = cfg.get(k)
        if not isinstance(v, int) or isinstance(v, bool):
            raise SystemExit(f"{path} : champ '{k}' manquant ou non entier.")
        # Le gabarit livré vaut 0 : il passe le test « est un entier » et
        # produirait une collecte entière de 404 silencieux. On refuse.
        if v <= 0:
            raise SystemExit(
                f"{path} : champ '{k}' encore à {v} — c'est la valeur du "
                "gabarit, pas la tienne. Ouvrir le fichier et y mettre les "
                "vrais identifiants (docs/guide-j0.md, sections 2 et 3).")
    return cfg
