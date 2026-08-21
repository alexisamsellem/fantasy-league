# -*- coding: utf-8 -*-
"""Collecte quotidienne (lecture seule) + chargement DuckDB minimal.

Tout passe par un SnapshotStore immuable. Les données personnelles (team ID,
ligue, picks, noms) ne quittent jamais data/ (ignoré par Git).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .api import SnapshotStore, get_json

HISTORY_GWS = 6          # profondeur d'historique de minutes collectée
MAX_LEAGUE_PAGES = 5     # mini-ligue privée : largement suffisant
MAX_RIVALS = 25


def _parse_iso(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def closed_gws(events, now=None):
    now = now or datetime.now(timezone.utc)
    return sorted(e["id"] for e in events
                  if e.get("deadline_time") and _parse_iso(e["deadline_time"]) <= now)


def next_gw_id(events, now=None):
    now = now or datetime.now(timezone.utc)
    future = [e["id"] for e in events
              if e.get("deadline_time") and _parse_iso(e["deadline_time"]) > now]
    return min(future) if future else None


def _collect_common(store):
    """Bootstrap + fixtures + historique live des GWs closes (données 100 %
    publiques, aucune config). Lève SystemExit si l'API est injoignable."""
    boot, err = get_json("/bootstrap-static/", store, "bootstrap-static")
    if boot is None:
        raise SystemExit(
            f"BLOCAGE COLLECTE : {err}\n"
            "L'API publique FPL est injoignable depuis cette machine (proxy, "
            "réseau ?). Aucune donnée n'a été modifiée ; réessayer depuis un "
            "réseau qui atteint fantasy.premierleague.com.")
    get_json("/fixtures/", store, "fixtures")
    closed = closed_gws(boot.get("events", []))
    for gw in closed[-HISTORY_GWS:]:
        get_json(f"/event/{gw}/live/", store, f"event-{gw}-live")
    return boot, closed


def collect_public(data_dir="data"):
    """Collecte minimale du mode effectif initial : aucune équipe, aucune
    ligue, aucune config requise. Retourne le répertoire du snapshot."""
    store = SnapshotStore(data_dir)
    _collect_common(store)
    return store.dir


def collect_all(cfg, data_dir="data"):
    """Collecte bootstrap, fixtures, historique live, mon équipe, la ligue et
    les picks des rivaux (post-deadline uniquement). Retourne le répertoire du
    snapshot ou lève SystemExit avec un diagnostic précis."""
    store = SnapshotStore(data_dir)
    boot, closed = _collect_common(store)

    tid, lid = cfg["team_id"], cfg["league_id"]
    get_json(f"/entry/{tid}/", store, f"entry-{tid}")
    get_json(f"/entry/{tid}/history/", store, f"entry-{tid}-history")
    get_json(f"/entry/{tid}/transfers/", store, f"entry-{tid}-transfers")
    last = closed[-1] if closed else None
    if last:
        get_json(f"/entry/{tid}/event/{last}/picks/", store, f"entry-{tid}-gw{last}-picks")

    # Classement de la ligue (pagination bornée) puis picks des rivaux
    rivals = []
    for page in range(1, MAX_LEAGUE_PAGES + 1):
        data, _ = get_json(f"/leagues-classic/{lid}/standings/?page_standings={page}",
                           store, f"league-{lid}-standings-p{page}")
        if not data:
            break
        rivals.extend(data.get("standings", {}).get("results") or [])
        if not data.get("standings", {}).get("has_next"):
            break
    for r in rivals[:MAX_RIVALS]:
        rid = r.get("entry")
        if not rid or rid == tid or not last:
            continue
        get_json(f"/entry/{rid}/event/{last}/picks/", store, f"entry-{rid}-gw{last}-picks")
        get_json(f"/entry/{rid}/history/", store, f"entry-{rid}-history")

    return store.dir


def _read(run_dir, name):
    p = Path(run_dir) / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_snapshot(run_dir, cfg):
    """Recharge un snapshot en une structure 'parsed' consommée par les modèles."""
    run_dir = Path(run_dir)
    boot = _read(run_dir, "bootstrap-static")
    if boot is None:
        raise SystemExit(f"Snapshot incomplet : bootstrap-static absent de {run_dir}")
    events = boot.get("events", [])
    closed = closed_gws(events)
    last = closed[-1] if closed else None
    tid, lid = cfg["team_id"], cfg["league_id"]

    live = {}
    for gw in closed[-HISTORY_GWS:]:
        data = _read(run_dir, f"event-{gw}-live")
        if data:
            live[gw] = data

    standings = []
    for page in range(1, MAX_LEAGUE_PAGES + 1):
        data = _read(run_dir, f"league-{lid}-standings-p{page}")
        if not data:
            break
        standings.extend(data.get("standings", {}).get("results") or [])

    rivals = {}
    for r in standings:
        rid = r.get("entry")
        if not rid or rid == tid:
            continue
        rivals[rid] = {
            "row": r,
            "picks": _read(run_dir, f"entry-{rid}-gw{last}-picks") if last else None,
            "history": _read(run_dir, f"entry-{rid}-history"),
        }

    return {
        "run_dir": str(run_dir),
        "bootstrap": boot,
        "fixtures": _read(run_dir, "fixtures") or [],
        "live": live,
        "events": events,
        "closed_gws": closed,
        "last_closed_gw": last,
        "next_gw": next_gw_id(events),
        "my": {
            "entry": _read(run_dir, f"entry-{tid}"),
            "history": _read(run_dir, f"entry-{tid}-history"),
            "transfers": _read(run_dir, f"entry-{tid}-transfers"),
            "picks": _read(run_dir, f"entry-{tid}-gw{last}-picks") if last else None,
        },
        "standings": standings,
        "rivals": rivals,
        "team_id": tid,
        "league_id": lid,
    }


def load_public_snapshot(run_dir):
    """Recharge un snapshot public (mode effectif initial) : même structure
    'parsed' que load_snapshot mais sans équipe, ligue ni rivaux."""
    run_dir = Path(run_dir)
    boot = _read(run_dir, "bootstrap-static")
    if boot is None:
        raise SystemExit(f"Snapshot incomplet : bootstrap-static absent de {run_dir}")
    events = boot.get("events", [])
    closed = closed_gws(events)
    live = {}
    for gw in closed[-HISTORY_GWS:]:
        data = _read(run_dir, f"event-{gw}-live")
        if data:
            live[gw] = data
    return {
        "run_dir": str(run_dir),
        "bootstrap": boot,
        "fixtures": _read(run_dir, "fixtures") or [],
        "live": live,
        "events": events,
        "closed_gws": closed,
        "last_closed_gw": closed[-1] if closed else None,
        "next_gw": next_gw_id(events),
        "my": {}, "standings": [], "rivals": {},
        "team_id": None, "league_id": None,
    }


def latest_snapshot_dir(data_dir="data"):
    root = Path(data_dir) / "snapshots"
    if not root.exists():
        return None
    runs = sorted(d for d in root.iterdir() if d.is_dir())
    return runs[-1] if runs else None


def load_duckdb(parsed, db_path="data/fpl.duckdb"):
    """Normalisation minimale : tables players, teams, events, fixtures,
    player_gw (minutes par GW). Best-effort : exige le paquet duckdb."""
    try:
        import duckdb
    except ImportError:
        return "duckdb non installé (pip install duckdb) — normalisation sautée"
    con = duckdb.connect(db_path)
    boot = parsed["bootstrap"]
    con.execute("CREATE OR REPLACE TABLE teams AS SELECT * FROM (SELECT unnest(?::JSON[]) j)",
                [[json.dumps(t) for t in boot.get("teams", [])]])
    con.execute("CREATE OR REPLACE TABLE players AS SELECT * FROM (SELECT unnest(?::JSON[]) j)",
                [[json.dumps(e) for e in boot.get("elements", [])]])
    con.execute("CREATE OR REPLACE TABLE events AS SELECT * FROM (SELECT unnest(?::JSON[]) j)",
                [[json.dumps(e) for e in boot.get("events", [])]])
    con.execute("CREATE OR REPLACE TABLE fixtures AS SELECT * FROM (SELECT unnest(?::JSON[]) j)",
                [[json.dumps(f) for f in parsed.get("fixtures", [])]])
    rows = []
    for gw, data in parsed.get("live", {}).items():
        for el in data.get("elements", []):
            rows.append(json.dumps({"gw": gw, "element": el.get("id"),
                                    "stats": el.get("stats", {})}))
    con.execute("CREATE OR REPLACE TABLE player_gw AS SELECT * FROM (SELECT unnest(?::JSON[]) j)",
                [rows])
    con.close()
    return f"DuckDB mis à jour : {db_path}"
