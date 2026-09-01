# -*- coding: utf-8 -*-
"""Collecte quotidienne (lecture seule) + chargement DuckDB minimal.

Tout passe par un SnapshotStore immuable. Les données personnelles (team ID,
ligue, picks, noms) ne quittent jamais data/ (ignoré par Git).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from . import priors
from .api import SnapshotStore, get_json

HISTORY_GWS = 6          # profondeur d'historique de minutes collectée
TEAM_REFERENCE = "data/reference/team_priors.csv"   # contrat : priors.DATA_CONTRACT
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


HISTORY_PROGRESS_EVERY = 50   # joueurs entre deux lignes d'avancement


def collect_element_history(store, elements, limit=None, progress=print):
    """Saisons passées joueur par joueur (GET /element-summary/{id}/).

    C'est la source du contrat `history_past` : sans elle, les priors de
    pré-saison sont plats par poste. Un appel public par joueur, aucun
    paramètre personnel. Retourne (n_ok, n_echecs).

    Une ligne d'avancement toutes les `HISTORY_PROGRESS_EVERY` requêtes : un
    terminal muet ne se distingue pas d'un blocage. Mesuré le 22/08/2026 sur
    600 joueurs depuis une connexion domestique : ~36 s, 0 échec — mais le coût
    dépend entièrement du réseau. `progress=None` fait taire l'avancement."""
    todo = list(elements if limit is None else elements[:limit])
    total = len(todo)
    if progress:
        progress(f"Saisons passées : {total} joueurs à collecter "
                 "(un GET public chacun)…")
    ok = fail = 0
    for i, e in enumerate(todo, 1):
        data, _ = get_json(f"/element-summary/{e['id']}/", store,
                           f"element-summary-{e['id']}")
        if data is None:
            fail += 1
        else:
            ok += 1
        if progress and (i % HISTORY_PROGRESS_EVERY == 0 or i == total):
            progress(f"  {i}/{total} — {ok} obtenus, {fail} échecs")
    return ok, fail


def collect_public(data_dir="data", with_history=False, history_limit=None):
    """Collecte minimale du mode effectif initial : aucune équipe, aucune
    ligue, aucune config requise. Retourne le répertoire du snapshot.

    `with_history` ajoute les saisons passées (un GET public par joueur) :
    c'est long mais c'est la donnée qui rend un top 15 de pré-saison
    défendable."""
    store = SnapshotStore(data_dir)
    boot, _ = _collect_common(store)
    if with_history:
        collect_element_history(store, boot.get("elements", []), history_limit)
    return store.dir


def collect_all(cfg, data_dir="data", with_history=False):
    """Collecte bootstrap, fixtures, historique live, mon équipe, la ligue et
    les picks des rivaux (post-deadline uniquement). Retourne le répertoire du
    snapshot ou lève SystemExit avec un diagnostic précis.

    `with_history` ajoute les saisons passées (un GET public par joueur). Les
    snapshots étant immuables et indépendants, ces fichiers appartiennent à CE
    snapshot : un run hebdomadaire sans l'option n'hérite pas de ceux du
    précédent. C'est le seul moyen de sortir de la confiance « faible » en
    début de saison, quand la saison en cours n'a pas encore assez de journées
    jouées pour porter la hiérarchie toute seule."""
    store = SnapshotStore(data_dir)
    boot, closed = _collect_common(store)
    if with_history:
        collect_element_history(store, boot.get("elements", []))

    tid = cfg["team_id"]
    get_json(f"/entry/{tid}/", store, f"entry-{tid}")
    get_json(f"/entry/{tid}/history/", store, f"entry-{tid}-history")
    get_json(f"/entry/{tid}/transfers/", store, f"entry-{tid}-transfers")
    last = closed[-1] if closed else None
    if last:
        get_json(f"/entry/{tid}/event/{last}/picks/", store, f"entry-{tid}-gw{last}-picks")

    # Classements des ligues (pagination bornée) puis picks des rivaux.
    # Un même manager peut appartenir à plusieurs ligues : ses picks ne sont
    # collectés qu'une fois, sinon on paie deux fois le même GET.
    deja = {tid}
    for lid in (cfg.get("league_ids") or [cfg["league_id"]]):
        rivals = []
        for page in range(1, MAX_LEAGUE_PAGES + 1):
            data, _ = get_json(
                f"/leagues-classic/{lid}/standings/?page_standings={page}",
                store, f"league-{lid}-standings-p{page}")
            if not data:
                break
            rivals.extend(data.get("standings", {}).get("results") or [])
            if not data.get("standings", {}).get("has_next"):
                break
        for r in rivals[:MAX_RIVALS]:
            rid = r.get("entry")
            if not rid or rid in deja or not last:
                continue
            deja.add(rid)
            get_json(f"/entry/{rid}/event/{last}/picks/", store,
                     f"entry-{rid}-gw{last}-picks")
            get_json(f"/entry/{rid}/history/", store, f"entry-{rid}-history")

    return store.dir


def snapshot_as_of(run_dir):
    """Date de connaissance des données d'un snapshot : la plus récente des
    dates de récupération du manifeste.

    Sans elle, le contrat de projections se datait de l'heure d'exécution du
    conseiller, pas de celle de la collecte — et un snapshot vieux de trois
    jours passait pour frais. Repli sur le nom du répertoire (horodatage UTC de
    la collecte), puis sur None : jamais une date fabriquée."""
    run_dir = Path(run_dir)
    manifest = run_dir / "manifest.json"
    if manifest.exists():
        try:
            entries = json.loads(manifest.read_text(encoding="utf-8"))
            stamps = [e.get("retrieved_at") for e in entries if e.get("retrieved_at")]
            if stamps:
                return max(stamps)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    try:
        dt = datetime.strptime(run_dir.name.split("-")[0], "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()


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
    tid = cfg["team_id"]
    league_ids = cfg.get("league_ids") or [cfg["league_id"]]

    live = {}
    for gw in closed[-HISTORY_GWS:]:
        data = _read(run_dir, f"event-{gw}-live")
        if data:
            live[gw] = data

    def _une_ligue(lid):
        rows, nom = [], None
        for page in range(1, MAX_LEAGUE_PAGES + 1):
            data = _read(run_dir, f"league-{lid}-standings-p{page}")
            if not data:
                break
            nom = nom or (data.get("league") or {}).get("name")
            rows.extend(data.get("standings", {}).get("results") or [])
        riv = {}
        for r in rows:
            rid = r.get("entry")
            if not rid or rid == tid:
                continue
            riv[rid] = {
                "row": r,
                "picks": _read(run_dir, f"entry-{rid}-gw{last}-picks") if last else None,
                "history": _read(run_dir, f"entry-{rid}-history"),
            }
        return {"id": lid, "name": nom or f"ligue {lid}",
                "standings": rows, "rivals": riv}

    leagues = [_une_ligue(lid) for lid in league_ids]
    # La première ligue reste la vue par défaut : tout ce qui lisait
    # `standings` / `rivals` continue de fonctionner sans le savoir.
    standings = leagues[0]["standings"] if leagues else []
    rivals = leagues[0]["rivals"] if leagues else {}

    return {
        "run_dir": str(run_dir),
        "as_of": snapshot_as_of(run_dir),
        "bootstrap": boot,
        "fixtures": _read(run_dir, "fixtures") or [],
        "live": live,
        "events": events,
        "history_past": read_history_past(run_dir, boot.get("elements", [])),
        "team_ref": priors.load_team_reference(TEAM_REFERENCE, boot.get("teams", [])),
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
        "leagues": leagues,
        "team_id": tid,
        "league_id": league_ids[0],
        "league_ids": league_ids,
    }


def read_history_past(run_dir, elements):
    """{element_id: [saisons passées]} depuis les fichiers element-summary du
    snapshot. Dict vide si la collecte n'a pas été faite — jamais fabriqué."""
    run_dir = Path(run_dir)
    out = {}
    for e in elements:
        data = _read(run_dir, f"element-summary-{e['id']}")
        if data and data.get("history_past"):
            out[e["id"]] = data["history_past"]
    return out


def load_public_snapshot(run_dir, team_reference=TEAM_REFERENCE):
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
    elements = boot.get("elements", [])
    return {
        "run_dir": str(run_dir),
        "as_of": snapshot_as_of(run_dir),
        "bootstrap": boot,
        "fixtures": _read(run_dir, "fixtures") or [],
        "live": live,
        "events": events,
        "closed_gws": closed,
        "last_closed_gw": closed[-1] if closed else None,
        "next_gw": next_gw_id(events),
        "history_past": read_history_past(run_dir, elements),
        "team_ref": priors.load_team_reference(team_reference, boot.get("teams", [])),
        "my": {}, "standings": [], "rivals": {},
        "team_id": None, "league_id": None,
    }


def gw_fixtures_state(data_dir="data", gw=None):
    """(matchs terminés, matchs au calendrier) pour une GW, d'après le snapshot
    le plus récent qui porte un calendrier.

    Sert de garde-fou à la calibration. `event.finished` du bootstrap ne suffit
    pas : FPL le laisse à faux pendant des jours après le dernier coup de
    sifflet, le temps de figer les bonus. Le calendrier, lui, dit la vérité
    match par match."""
    root = Path(data_dir) / "snapshots"
    if not root.exists() or gw is None:
        return 0, 0
    for run in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
        fixtures = _read(run, "fixtures")
        if not fixtures:
            continue
        de_la_gw = [f for f in fixtures if f.get("event") == gw]
        if not de_la_gw:
            continue
        return sum(1 for f in de_la_gw if f.get("finished")), len(de_la_gw)
    return 0, 0


def gw_complete(data_dir="data", gw=None):
    """La journée est-elle intégralement jouée ?

    Condition NÉCESSAIRE pour noter des prévisions. Sans elle, un joueur dont
    le match n'a pas encore eu lieu compte comme « n'a pas joué », et le score
    mesure l'avancement du calendrier, pas la qualité du modèle."""
    finis, total = gw_fixtures_state(data_dir, gw)
    return total > 0 and finis == total


def observed_minutes(data_dir="data", gw=None):
    """{element_id: minutes} d'une GW jouée, pris dans le snapshot le plus
    récent qui la contient réellement.

    Un fichier `event-<gw>-live.json` existe dès que la GW est ouverte, mais il
    ne contient que des zéros avant les matchs. On exige donc au moins une
    minute non nulle : sinon on rend {} et l'appelant refuse de conclure, au
    lieu de scorer des prédictions contre une journée non jouée."""
    root = Path(data_dir) / "snapshots"
    if not root.exists() or gw is None:
        return {}
    for run in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
        data = _read(run, f"event-{gw}-live")
        if not data:
            continue
        mins = {int(e["id"]): int((e.get("stats") or {}).get("minutes") or 0)
                for e in data.get("elements", []) if e.get("id") is not None}
        if any(mins.values()):
            return mins
    return {}


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
