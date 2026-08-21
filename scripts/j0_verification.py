#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Protocole J0 — vérification en lecture seule des faits réglementaires du dossier.

GARANTIES
  - Lecture seule : uniquement des requêtes GET sur les endpoints PUBLICS de
    l'API FPL. Aucune authentification, aucun cookie, aucun identifiant de
    connexion, aucune écriture côté FPL.
  - Chaque réponse brute est sauvegardée en snapshot horodaté (premier
    snapshot point-in-time du projet).
  - L'API sert à vérifier les DONNÉES et PARAMÈTRES OPÉRATIONNELS de la
    saison (effectifs, chips et fenêtres, deadlines, prix, schéma des
    statistiques). Les RÈGLES que l'API n'expose pas explicitement (barème de
    points, règle du vice-capitaine, mécanique des prix, BPS…) restent sous
    l'autorité des pages officielles Help/Rules : elles sont listées en
    section manuelle du rapport, à confirmer page officielle à l'appui.

USAGE
  python3 scripts/j0_verification.py
      → checks API + génère j0_report.md et j0_manual.json (gabarit à remplir)
  python3 scripts/j0_verification.py --manual j0_manual.json
      → intègre les confirmations manuelles et finalise les statuts
  Options : --entry-id N   vérifie la lisibilité publique d'une équipe (post-deadline)
            --league-id N  vérifie la lisibilité publique d'une mini-ligue classic
            --out DIR      répertoire de sortie (défaut : ./j0_output)

STATUTS FINAUX
  [F] fait vérifié (API officielle concordante, ou page officielle confirmée à la main)
  [H] l'examen montre que l'énoncé n'est pas une règle mais une hypothèse
  [R] à revérifier : divergence observée, champ non exposé, ou confirmation manquante
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (J0-verification; lecture seule; contact: proprietaire du compte)"}

HELP_RULES_URL = "https://fantasy.premierleague.com/help/rules"
OFFICIAL = {
    "changes_2627": "https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627",
    "chips": "https://www.premierleague.com/en/news/4362085",
    "defcon": "https://www.premierleague.com/en/news/4361991/whats-happening-with-defensive-contribution-points-in-202627-fantasy",
    "prices": "https://www.premierleague.com/en/news/2858775",
    "dates": "https://www.premierleague.com/en/news/4468487/dates-for-202627-premier-league-season-confirmed",
}


class SnapshotStore:
    """Un répertoire immuable par exécution (snapshots/<horodatage UTC>/), jamais
    réutilisé ni écrasé, avec un manifeste par run : fichier, URL, retrieved_at,
    statut HTTP, SHA-256."""

    def __init__(self, out_dir):
        root = Path(out_dir) / "snapshots"
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
            "file": fname,
            "url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "http_status": http_status,
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
        (self.dir / "manifest.json").write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.dir / fname


def get_json(path, store, name):
    """GET public, sans cookie ; snapshot dans le run courant ; None si échec."""
    url = path if path.startswith("http") else f"{API}{path}"
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw, status = resp.read(), resp.status
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return None, f"échec GET {url} : {e}"
    store.save(name, raw, url, status)
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return None, f"réponse non-JSON {url} : {e}"


def first_key(d, candidates):
    """Retourne (clé, valeur) pour la première clé présente, sinon (None, None)."""
    for k in candidates:
        if isinstance(d, dict) and k in d:
            return k, d[k]
    return None, None


class Check:
    def __init__(self, cid, claim, authority, kind):
        self.cid, self.claim, self.authority, self.kind = cid, claim, authority, kind
        self.observed, self.status, self.note = "—", "R", ""

    def ok(self, observed, note=""):
        self.observed, self.status, self.note = observed, "F", note

    def ko(self, observed, note=""):
        self.observed, self.status, self.note = observed, "R", note


def run_api_checks(out_dir, store, entry_id=None, league_id=None):
    checks = []
    boot, err = get_json("/bootstrap-static/", store, "bootstrap-static")

    c = Check("api_reachable", "API FPL publique accessible sans authentification",
              f"{API}/bootstrap-static/", "api")
    if boot is None:
        c.ko("inaccessible", err or "")
        return [c], None
    c.ok("accessible (snapshot enregistré)")
    checks.append(c)

    gs = boot.get("game_settings", {})
    (out_dir / "game_settings_dump.json").write_text(
        json.dumps(gs, indent=2, ensure_ascii=False), encoding="utf-8")

    # Effectif, XI, limite par club
    c = Check("squad", "Effectif de 15 joueurs, XI de 11, max 3 par club",
              f"{API}/bootstrap-static/ (game_settings)", "api")
    size = gs.get("squad_squadsize")
    play = gs.get("squad_squadplay")
    team_limit = gs.get("squad_team_limit")
    obs = f"squadsize={size}, squadplay={play}, team_limit={team_limit}"
    if (size, play, team_limit) == (15, 11, 3):
        c.ok(obs)
    elif None in (size, play, team_limit):
        c.ko(obs, "champ(s) absent(s) — confirmer sur Help/Rules")
    else:
        c.ko(obs, "DIVERGENCE avec le dossier — corriger le dossier")
    checks.append(c)

    # Quotas par poste et bornes du XI
    c = Check("positions", "Quotas 2 GB / 5 DEF / 5 MIL / 3 ATT ; XI : 1 GB, ≥3 DEF, ≥1 ATT",
              f"{API}/bootstrap-static/ (element_types)", "api")
    try:
        et = {t["singular_name_short"]: t for t in boot["element_types"]}
        sel = {k: t.get("squad_select") for k, t in et.items()}
        mn = {k: t.get("squad_min_play") for k, t in et.items()}
        mx = {k: t.get("squad_max_play") for k, t in et.items()}
        obs = f"select={sel}, min_play={mn}, max_play={mx}"
        expect_sel = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
        if all(sel.get(k) == v for k, v in expect_sel.items()) \
                and mn.get("GKP") == 1 and mx.get("GKP") == 1 \
                and mn.get("DEF", 99) >= 3 and mn.get("FWD", 99) >= 1:
            c.ok(obs)
        else:
            c.ko(obs, "à comparer ligne à ligne avec le dossier")
    except (KeyError, TypeError) as e:
        c.ko("structure element_types inattendue", str(e))
    checks.append(c)

    # Budget initial
    c = Check("budget", "Budget initial 100,0 M£",
              f"{API}/bootstrap-static/ (game_settings)", "api")
    k, v = first_key(gs, ["squad_total_spend", "budget", "initial_budget"])
    if v == 1000:
        c.ok(f"{k}={v} (unité 0,1 M£)")
    elif v is not None:
        c.ko(f"{k}={v}", "valeur inattendue — vérifier l'unité puis Help/Rules")
    else:
        c.ko("champ non exposé", "confirmer sur Help/Rules (section manuelle)")
    checks.append(c)

    # Transferts gratuits : cumul maximal
    c = Check("ft_bank", "1 transfert gratuit/GW, cumul maximal 5",
              f"{API}/bootstrap-static/ (game_settings) + Help/Rules", "api")
    k, v = first_key(gs, ["max_extra_free_transfers", "transfers_cap",
                          "free_transfers_cap", "transfers_limit"])
    if v is not None:
        c.ko(f"{k}={v}", "sémantique du champ à confirmer sur Help/Rules avant promotion [F]")
    else:
        c.ko("champ non exposé", "règle → autorité Help/Rules (section manuelle)")
    checks.append(c)

    # Chips : 2 jeux, fenêtres GW19/GW20
    c = Check("chips", "2 Wildcards, 2 Free Hits, 2 Bench Boosts, 2 Triple Captains ; "
                       "jeu 1 jusqu'à GW19, jeu 2 dès GW20",
              f"{API}/bootstrap-static/ (chips) + {OFFICIAL['chips']}", "api")
    chips = boot.get("chips")
    if isinstance(chips, list) and chips:
        summary = sorted((ch.get("name"), ch.get("start_event"), ch.get("stop_event"))
                         for ch in chips)
        counts = {}
        for name, _, _ in summary:
            counts[name] = counts.get(name, 0) + 1
        two_each = len(counts) == 4 and all(n == 2 for n in counts.values())
        windows_ok = all(
            (stop is not None and stop <= 19) or (start is not None and start >= 20)
            for _, start, stop in summary)
        obs = f"{summary}"
        if two_each and windows_ok:
            c.ok(obs)
        else:
            c.ko(obs, "compter/fenêtrer à la main contre la page officielle")
    else:
        c.ko("liste chips non exposée", "confirmer sur la page officielle (section manuelle)")
    checks.append(c)

    # Deadline : OBSERVATION mesurée sur les GW programmées. Ne prouve pas la
    # règle générale — celle-ci relève de Help/Rules (ligne manuelle deadline_rule).
    c = Check("deadline_h90_obs", "Observation : écart deadline → premier coup d'envoi, "
                                  "mesuré sur toutes les GW programmées",
              f"{API}/bootstrap-static/ (events) + {API}/fixtures/", "api")
    fixtures, err = get_json("/fixtures/", store, "fixtures")
    try:
        deadlines = {e["id"]: e["deadline_time"] for e in boot["events"]}
        firsts = {}
        for f in fixtures or []:
            ev, ko = f.get("event"), f.get("kickoff_time")
            if ev and ko:
                firsts[ev] = min(firsts.get(ev, ko), ko)
        def parse(ts):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        gaps = sorted({round((parse(firsts[ev]) - parse(deadlines[ev])).total_seconds() / 60)
                       for ev in firsts if ev in deadlines})
        obs = f"écarts observés (min) sur {len(firsts)} GW : {gaps}"
        if gaps == [90]:
            c.ok(obs, "observation cohérente — la règle générale reste à confirmer "
                      "sur Help/Rules (ligne manuelle deadline_rule)")
        elif gaps:
            c.ko(obs, "écart(s) ≠ 90 min — noter les GW concernées et corriger le dossier")
        else:
            c.ko("aucune GW mesurable", err or "")
    except (KeyError, TypeError, ValueError) as e:
        c.ko("calcul impossible", str(e))
    checks.append(c)

    # Prix : unité 0,1 M£
    c = Check("prices_unit", "Prix exprimés en pas de 0,1 M£ (now_cost entier, /10)",
              f"{API}/bootstrap-static/ (elements) + {OFFICIAL['prices']}", "api")
    try:
        costs = [e["now_cost"] for e in boot["elements"][:200]]
        obs = f"{len(boot['elements'])} joueurs ; now_cost ∈ [{min(costs)}, {max(costs)}]"
        c.ok(obs, "mécanique de variation et revente → autorité page officielle (manuel)")
    except (KeyError, ValueError, TypeError) as e:
        c.ko("elements illisible", str(e))
    checks.append(c)

    # Schéma des statistiques : champs DEFCON officiels
    c = Check("defcon_fields", "L'API officielle expose des statistiques de contribution "
                               "défensive par joueur (vérité terrain du modèle DEFCON)",
              f"{API}/bootstrap-static/ (element_stats) + {API}/event/{{gw}}/live/", "api")
    names = [s.get("name", "") for s in boot.get("element_stats", [])]
    pat = re.compile(r"defen|clearance|block|intercept|tackle|recover", re.I)
    hits = [n for n in names if pat.search(n)]
    live, _ = get_json("/event/1/live/", store, "event-1-live")
    live_keys = []
    try:
        live_keys = sorted(k for k in (live["elements"][0]["stats"].keys()) if pat.search(k))
    except (KeyError, IndexError, TypeError):
        pass
    obs = f"element_stats={hits or 'aucun'} ; live GW1={live_keys or 'aucun'}"
    if hits or live_keys:
        c.ok(obs, "noms exacts à figer dans le modèle ; seuils 10/12 → page officielle (manuel)")
    else:
        c.ko(obs, "champs introuvables — inspecter les snapshots à la main")
    checks.append(c)

    # Lisibilité publique d'une équipe (rivaux) — optionnel.
    # Le rapport masque l'ID (partageable) ; l'ID complet ne vit que dans les
    # snapshots locaux, jamais transmis.
    if entry_id:
        label = f"…{str(entry_id)[-2:]}"
        c = Check("entry_public", f"Équipe <ID masqué {label}> lisible sans authentification "
                                  "(profil, historique, picks post-deadline)",
                  f"{API}/entry/<ID>/ …", "api")
        parts = []
        for suffix, name, shown in [
                (f"/entry/{entry_id}/", f"entry-{entry_id}", "/entry/<ID>/"),
                (f"/entry/{entry_id}/history/", f"entry-history-{entry_id}",
                 "/entry/<ID>/history/"),
                (f"/entry/{entry_id}/event/1/picks/", f"entry-gw1-picks-{entry_id}",
                 "/entry/<ID>/event/1/picks/")]:
            data, _ = get_json(suffix, store, name)
            parts.append(f"{shown} → {'OK' if data is not None else 'ÉCHEC'}")
        obs = " ; ".join(parts)
        (c.ok if "ÉCHEC" not in obs else c.ko)(
            obs, "ID masqué dans ce rapport ; données réelles en snapshots locaux uniquement")
        checks.append(c)

    # Lisibilité publique d'une mini-ligue classic — optionnel (ID masqué idem)
    if league_id:
        label = f"…{str(league_id)[-2:]}"
        c = Check("league_public", f"Mini-ligue <ID masqué {label}> lisible sans "
                                   "authentification (classement + entry IDs des rivaux)",
                  f"{API}/leagues-classic/<ID>/standings/", "api")
        data, e2 = get_json(f"/leagues-classic/{league_id}/standings/", store,
                            f"league-{league_id}-standings")
        if data and data.get("standings", {}).get("results") is not None:
            n = len(data["standings"]["results"])
            c.ok(f"OK — {n} managers en page 1 (entry IDs présents)",
                 "aucun nom ni ID dans ce rapport ; détail en snapshots locaux uniquement")
        else:
            c.ko("ÉCHEC ou structure inattendue",
                 e2 or "la ligue est peut-être fermée à la lecture")
        checks.append(c)

    return checks, boot


# Règles hors API : l'autorité est la page officielle, confirmation humaine requise.
MANUAL_ITEMS = [
    ("vice_zero_minute", "Le vice-capitaine ne prend le brassard que si le capitaine "
                         "joue 0 minute dans la GW", HELP_RULES_URL),
    ("captain_x2", "Capitaine ×2 ; Triple Captain ×3", HELP_RULES_URL),
    ("hit_cost", "Transfert au-delà des gratuits : −4 pts", HELP_RULES_URL),
    ("deadline_rule", "Règle générale : la deadline de chaque Gameweek est fixée "
                      "90 minutes avant son premier coup d'envoi", HELP_RULES_URL),
    ("defcon_thresholds", "DEFCON : 2 pts si CBIT ≥ 10 (DEF) / CBIRT ≥ 12 (MIL-ATT), "
                          "plafond 2 pts/match", OFFICIAL["defcon"]),
    ("bps_2627", "BPS 2026/27 : chevauchement DEFCON réduit, gardiens/latéraux mieux "
                 "servis, pénalité de dépossession supprimée", OFFICIAL["changes_2627"]),
    ("sell_price", "Revente = prix d'achat + moitié de la hausse (pas de 0,1, arrondi "
                   "inférieur) ; baisse subie en totalité", OFFICIAL["prices"]),
    ("lockdown", "Verrouillage des scores à 09h00 UK le lendemain du dernier match",
     OFFICIAL["changes_2627"]),
    ("ft_bank_manual", "Cumul maximal de 5 transferts gratuits", HELP_RULES_URL),
    ("season_dates", "Saison du 21/08/2026 au 30/05/2027", OFFICIAL["dates"]),
]


def build_manual_template(path):
    """Gabarit avec champs de trace probante. Un [F] manuel exige les quatre :
    url_consulted (ou l'authority par défaut), page_title_or_section,
    verified_on (date), confirmed_statement (l'énoncé effectivement lu)."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    template = {k: {"claim": claim, "authority": url, "confirmed": None,
                    "url_consulted": "", "page_title_or_section": "",
                    "verified_on": "", "confirmed_statement": "", "note": ""}
                for k, claim, url in MANUAL_ITEMS}
    path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    return template


def manual_checks(manual):
    out = []
    for key, claim, url in MANUAL_ITEMS:
        c = Check(key, claim, url, "manuel")
        entry = manual.get(key, {})
        v, note = entry.get("confirmed"), entry.get("note", "")
        c.authority = (entry.get("url_consulted") or "").strip() or url
        title = (entry.get("page_title_or_section") or "").strip()
        date = (entry.get("verified_on") or "").strip()
        stmt = (entry.get("confirmed_statement") or "").strip()
        trace_ok = bool(title and date and stmt)
        trace = f"{date} — section « {title} » — énoncé confirmé : « {stmt} »"
        if v is True and trace_ok:
            c.ok(trace, note)
        elif v is True:
            c.ko("confirmed=true SANS trace probante",
                 "un [F] exige URL, titre/section, date et énoncé confirmé — reste [R]")
        elif v is False:
            c.ko(f"INFIRMÉ — {trace if trace_ok else 'trace incomplète'}",
                 note or "corriger le dossier")
        elif v == "h":
            c.observed = f"requalifié en hypothèse — {trace if trace_ok else 'sans trace'}"
            c.status, c.note = "H", note
        else:
            c.ko("non confirmé (champ 'confirmed' vide)",
                 "ouvrir la source et répondre, trace à l'appui")
        out.append(c)
    return out


def write_report(out_dir, api_checks, man_checks):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Rapport J0 — vérification des faits réglementaires",
        f"\nGénéré le {now}. Lecture seule, endpoints publics uniquement, aucun identifiant.",
        "Autorité des règles : pages officielles Help/Rules et Premier League. "
        "L'API vérifie les paramètres opérationnels qu'elle expose explicitement ; "
        "une ligne « Observation » constate une régularité mesurée et ne prouve pas "
        "la règle générale, confirmée à part en section manuelle.",
        "Partage : ce rapport ne contient ni ID complet, ni nom de manager — il est "
        "transmissible tel quel. Chaque exécution écrit ses snapshots dans un "
        "répertoire immuable `snapshots/<horodatage UTC>/` avec un manifeste "
        "(fichier, URL, retrieved_at, statut HTTP, SHA-256) ; ces données réelles "
        "restent locales et ne sont jamais commitées ni transmises.",
        "\n## Checks automatisés (API officielle)\n",
        "| Règle | Source | Valeur observée | Statut |",
        "|---|---|---|---|",
    ]
    for c in api_checks:
        note = f" — {c.note}" if c.note else ""
        lines.append(f"| {c.claim} | {c.authority} | {c.observed}{note} | [{c.status}] |")
    lines += [
        "\n## Confirmations manuelles (autorité : pages officielles)\n",
        "Remplir `j0_manual.json` puis relancer avec `--manual j0_manual.json`. "
        "Un [F] exige la trace probante complète : `url_consulted` (sinon l'authority), "
        "`page_title_or_section`, `verified_on` (date) et `confirmed_statement` "
        "(l'énoncé effectivement lu). Un `confirmed: true` sans ces champs reste [R].\n",
        "| Règle | Source | Valeur observée | Statut |",
        "|---|---|---|---|",
    ]
    for c in man_checks:
        note = f" — {c.note}" if c.note else ""
        lines.append(f"| {c.claim} | {c.authority} | {c.observed}{note} | [{c.status}] |")
    total = api_checks + man_checks
    nf = sum(1 for c in total if c.status == "F")
    nr = sum(1 for c in total if c.status == "R")
    nh = sum(1 for c in total if c.status == "H")
    lines += [
        f"\n## Bilan : {nf} × [F], {nh} × [H], {nr} × [R] sur {len(total)} règles.",
        "Tout [R] exige une action : corriger le dossier, ou documenter pourquoi la "
        "vérification reste impossible. Le dossier ne promeut une ligne [F◦] → [F] "
        "que sur la foi de ce rapport.",
    ]
    (out_dir / "j0_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Protocole J0 (lecture seule)")
    ap.add_argument("--manual", type=Path, default=None)
    ap.add_argument("--entry-id", type=int, default=None)
    ap.add_argument("--league-id", type=int, default=None)
    ap.add_argument("--out", type=Path, default=Path("j0_output"))
    args = ap.parse_args()

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    store = SnapshotStore(out_dir)
    api_checks, _ = run_api_checks(out_dir, store, args.entry_id, args.league_id)
    manual_path = args.manual or (out_dir / "j0_manual.json")
    manual = build_manual_template(manual_path)
    man_checks = manual_checks(manual)
    write_report(out_dir, api_checks, man_checks)

    print(f"Rapport : {out_dir / 'j0_report.md'}")
    print(f"Confirmations manuelles : {manual_path} (à remplir puis relancer avec --manual)")
    print(f"Snapshots de ce run : {store.dir} (manifest.json inclus)")
    ko = [c.cid for c in api_checks if c.status == "R"]
    if ko:
        print(f"Checks API en [R] : {', '.join(ko)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
