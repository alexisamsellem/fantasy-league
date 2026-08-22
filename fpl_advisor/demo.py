# -*- coding: utf-8 -*-
"""Jeu de données 100 % synthétique pour prouver le bout-en-bout hors ligne.

Six clubs fictifs, 90 joueurs fictifs, 2 GW d'historique, 3 rivaux fictifs.
Aucune donnée réelle : sert aux tests et à la démonstration du pipeline.
"""

from datetime import datetime, timedelta, timezone

CLUBS = ["Alpha", "Bravo", "Citrus", "Delta", "Echo", "Foxtrot"]
POS_QUOTA = [(1, 2), (2, 5), (3, 5), (4, 3)]   # par club : 2 GB, 5 DEF, 5 MIL, 3 ATT


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parsed(now=None):
    now = now or datetime.now(timezone.utc)
    teams = []
    for i, name in enumerate(CLUBS, 1):
        s = 1000 + 80 * (len(CLUBS) - i)          # Alpha la plus forte
        teams.append({"id": i, "name": name, "short_name": name[:3].upper(),
                      "strength_attack_home": s + 60, "strength_attack_away": s,
                      "strength_defence_home": s + 40, "strength_defence_away": s - 20})

    elements, eid = [], 0
    for t in range(1, len(CLUBS) + 1):
        for et, quota in POS_QUOTA:
            for k in range(1, quota + 1):
                eid += 1
                starter = k <= {1: 1, 2: 4, 3: 4, 4: 2}[et]
                price = {1: 45, 2: 45, 3: 55, 4: 60}[et] + (18 if starter else 0) \
                    + (12 if t <= 2 and starter else 0) - 2 * k
                elements.append({
                    "id": eid, "web_name": f"{CLUBS[t-1]}-{ {1:'GB',2:'DEF',3:'MIL',4:'ATT'}[et] }{k}",
                    "team": t, "element_type": et, "now_cost": price,
                    "status": "a", "chance_of_playing_next_round": None,
                    "minutes": 180 if starter else 25,
                    "expected_goals_per_90": {1: 0.0, 2: 0.06, 3: 0.25, 4: 0.45}[et] * (1.2 if t <= 2 else 0.9),
                    "expected_assists_per_90": {1: 0.0, 2: 0.08, 3: 0.18, 4: 0.12}[et],
                    "saves_per_90": 3.2 if et == 1 else 0.0,
                    "bonus": 2 if starter and t <= 2 else 0,
                    "yellow_cards": 1 if et == 2 else 0,
                    "penalties_order": 1 if (et == 4 and k == 1) else None,
                    "direct_freekicks_order": 1 if (et == 3 and k == 1) else None,
                    "corners_and_indirect_freekicks_order": 1 if (et == 3 and k == 1) else None,
                    "ep_next": None,
                    "selected_by_percent": "0.0",
                    "starts": 2 if starter else 0,
                    "news": "",
                })
    # un blessé et un incertain, pour exercer les statuts
    elements[20]["status"], elements[20]["chance_of_playing_next_round"] = "i", 0
    elements[35]["status"], elements[35]["chance_of_playing_next_round"] = "d", 50

    events = [
        {"id": 1, "deadline_time": _iso(now - timedelta(days=8))},
        {"id": 2, "deadline_time": _iso(now - timedelta(days=3))},
        {"id": 3, "deadline_time": _iso(now + timedelta(days=3))},
        {"id": 4, "deadline_time": _iso(now + timedelta(days=10))},
        {"id": 5, "deadline_time": _iso(now + timedelta(days=17))},
    ]
    pairings = {1: [(1, 2), (3, 4), (5, 6)], 2: [(1, 3), (2, 5), (4, 6)],
                3: [(1, 4), (2, 6), (3, 5)], 4: [(6, 1), (5, 4), (2, 3)],
                5: [(1, 5), (3, 6), (4, 2)]}
    fixtures = [{"event": gw, "team_h": h, "team_a": a}
                for gw, pairs in pairings.items() for h, a in pairs]

    def live_for(gw):
        rows = []
        for e in elements:
            starter = e["minutes"] >= 180
            mins = 90 if starter else (20 if e["id"] % 3 == 0 else 0)
            if e["id"] == 21:      # le blessé n'a pas joué la GW2
                mins = 0 if gw == 2 else mins
            st = {"minutes": mins, "tackles": 3 if e["element_type"] in (2, 3) else 0,
                  "clearances_blocks_interceptions": 8 if e["element_type"] == 2 else 2,
                  "recoveries": 6 if e["element_type"] == 3 else 2}
            rows.append({"id": e["id"], "stats": st})
        return {"elements": rows}

    # Mon équipe : 15 joueurs sur 6 clubs (≤ 3 par club), GB2 remplaçant faible
    def club_ids(t, et, k):
        base = (t - 1) * 15
        offset = {1: 0, 2: 2, 3: 7, 4: 12}[et]
        return base + offset + k

    my_ids = [club_ids(1, 1, 1), club_ids(4, 1, 2),
              club_ids(1, 2, 1), club_ids(2, 2, 1), club_ids(3, 2, 1),
              club_ids(4, 2, 1), club_ids(5, 2, 5),
              club_ids(1, 3, 1), club_ids(2, 3, 1), club_ids(3, 3, 1),
              club_ids(5, 3, 1), club_ids(6, 3, 5),
              club_ids(2, 4, 1), club_ids(4, 4, 1), club_ids(6, 4, 1)]
    my_picks = {"picks": [{"element": i, "is_captain": i == my_ids[7],
                           "is_vice_captain": i == my_ids[12]} for i in my_ids],
                "entry_history": {"bank": 15, "value": 1000}}

    def rival_picks(shift):
        ids = my_ids[:10] + [club_ids(5, 4, 1 + shift % 2), club_ids(3, 3, 2),
                             club_ids(6, 2, 1), club_ids(2, 1, 2), club_ids(4, 3, 2)]
        return {"picks": [{"element": i, "is_captain": i == ids[shift],
                           "is_vice_captain": False} for i in ids]}

    standings = [
        {"entry": 9001, "entry_name": "Rival Nord", "player_name": "Manager R1", "rank": 1, "total": 142},
        {"entry": 1000, "entry_name": "Mon Équipe Démo", "player_name": "Moi", "rank": 2, "total": 131},
        {"entry": 9002, "entry_name": "Rival Sud", "player_name": "Manager R2", "rank": 3, "total": 120},
        {"entry": 9003, "entry_name": "Rival Ouest", "player_name": "Manager R3", "rank": 4, "total": 99},
    ]
    rivals = {
        9001: {"row": standings[0], "picks": rival_picks(0),
               "history": {"chips": [{"name": "wildcard", "event": 2}]}},
        9002: {"row": standings[2], "picks": rival_picks(3), "history": {"chips": []}},
        9003: {"row": standings[3], "picks": rival_picks(5), "history": {"chips": []}},
    }

    hist = synthetic_history_past(elements)
    attach_public_estimates(elements, hist)
    return {
        "run_dir": "(démo synthétique — aucune donnée réelle)",
        "synthetic": True,
        "history_past": hist,
        "bootstrap": {"teams": teams, "elements": elements, "events": events},
        "fixtures": fixtures,
        "live": {1: live_for(1), 2: live_for(2)},
        "events": events,
        "closed_gws": [1, 2], "last_closed_gw": 2, "next_gw": 3,
        "my": {"entry": {"name": "Mon Équipe Démo"}, "history": None,
               "transfers": [], "picks": my_picks},
        "standings": standings, "rivals": rivals,
        "team_id": 1000, "league_id": 424242,
    }


def attach_public_estimates(elements, hist):
    """Champs publics SYNTHÉTIQUES imitant `ep_next` et `selected_by_percent`.

    Estimateur volontairement naïf et INDÉPENDANT du moteur interne (points de
    la saison passée ramenés au match), pour que la baseline du banc d'essai ne
    soit pas une copie déguisée des projections testées."""
    for e in elements:
        past = (hist.get(e["id"]) or [{}])[-1]
        pts = float(past.get("total_points") or 0)
        mins = float(past.get("minutes") or 0)
        per_match = pts / 38.0
        e["ep_next"] = f"{per_match:.1f}"
        e["selected_by_percent"] = f"{min(60.0, per_match * 6.0):.1f}"
        e["_synthetic_prev_minutes"] = mins
    return elements


def synthetic_history_past(elements):
    """Saisons passées 100 % SYNTHÉTIQUES, pour exercer le chemin de code des
    priors de pré-saison. Ne vaut aucune validation de qualité : les valeurs
    sont fabriquées, elles ne disent rien de la réalité 2026/27."""
    hist = {}
    for e in elements:
        et, k = e["element_type"], int(e["web_name"][-1])
        starter = e["starts"] > 0 or e["minutes"] >= 180
        strong_club = e["team"] <= 2
        starts = (34 - 3 * k) if starter else max(1, 6 - k)
        minutes = starts * 88 + (60 if starter else 40)
        base_g = {1: 0.0, 2: 0.04, 3: 0.22, 4: 0.42}[et] * (1.25 if strong_club else 0.85)
        base_a = {1: 0.0, 2: 0.06, 3: 0.20, 4: 0.12}[et] * (1.15 if strong_club else 0.9)
        rank = max(0.35, 1.0 - 0.14 * (k - 1))
        hist[e["id"]] = [{
            "season_name": "2025/26",
            "minutes": minutes, "starts": starts,
            "expected_goals": round(base_g * rank * minutes / 90, 2),
            "expected_assists": round(base_a * rank * minutes / 90, 2),
            "goals_scored": int(base_g * rank * minutes / 90),
            "assists": int(base_a * rank * minutes / 90),
            "bonus": int(0.16 * rank * minutes / 90) if starter else 0,
            "total_points": int((2.2 + 1.8 * rank) * minutes / 90),
        }]
    return hist


def build_parsed_initial(now=None):
    """Variante pré-saison du jeu synthétique, pour le mode effectif initial :
    toutes les deadlines dans le futur, aucun historique live, compteurs de
    saison remis à zéro (le moteur bascule sur les priors par prix), aucune
    équipe ni ligue — comme avant la première deadline d'une vraie saison."""
    now = now or datetime.now(timezone.utc)
    parsed = build_parsed(now)
    for i, e in enumerate(parsed["events"]):
        e["deadline_time"] = _iso(now + timedelta(days=2 + 7 * i))
    # Anomalie A1 : `synthetic_history_past` déduit le statut de titulaire de la
    # saison passée depuis `starts`/`minutes` de la saison EN COURS. Il faut donc
    # la construire AVANT la remise à zéro, sinon tout le monde hérite d'un passé
    # de remplaçant et le capitaine de la démo tombe à P(60+) = 14 %.
    hist = synthetic_history_past(parsed["bootstrap"]["elements"])
    for e in parsed["bootstrap"]["elements"]:
        e["minutes"] = 0
        e["starts"] = 0
        e["bonus"] = 0
        e["yellow_cards"] = 0
        # Avant la GW1, les taux par 90 de la saison en cours n'existent pas.
        e["expected_goals_per_90"] = 0.0
        e["expected_assists_per_90"] = 0.0
    parsed["history_past"] = hist
    attach_public_estimates(parsed["bootstrap"]["elements"], parsed["history_past"])
    parsed.update({
        "run_dir": "(démo synthétique pré-saison — aucune donnée réelle)",
        "synthetic": True,
        "live": {}, "closed_gws": [], "last_closed_gw": None, "next_gw": 1,
        "my": {}, "standings": [], "rivals": {},
        "team_id": None, "league_id": None,
    })
    return parsed


def build_parsed_scale(n_teams=20, seed=7):
    """Jeu SYNTHÉTIQUE à la taille d'une vraie saison (20 clubs, ~700 joueurs).

    Sert à deux choses, et à rien d'autre : mesurer le coût d'exécution, et
    vérifier que la détection d'instabilité du top 15 se déclenche sur une
    dispersion réaliste (la petite démo à 6 clubs est trop peu peuplée pour
    l'exercer). Les valeurs sont fabriquées : aucune validation de qualité.
    """
    import random
    rng = random.Random(seed)
    teams = [{"id": i, "name": f"Club{i}", "short_name": f"C{i:02d}",
              "strength_attack_home": 1000 + 20 * i,
              "strength_attack_away": 980 + 20 * i,
              "strength_defence_home": 1000 + 15 * i,
              "strength_defence_away": 980 + 15 * i}
             for i in range(1, n_teams + 1)]
    quota = [(1, 4), (2, 11), (3, 12), (4, 8)]     # effectif FPL réaliste
    elements, hist, eid = [], {}, 0
    for t in range(1, n_teams + 1):
        for et, n in quota:
            for k in range(1, n + 1):
                eid += 1
                starter = k <= {1: 1, 2: 5, 3: 5, 4: 2}[et]
                elements.append({
                    "id": eid, "web_name": f"P{eid}", "team": t, "element_type": et,
                    "now_cost": {1: 45, 2: 45, 3: 50, 4: 55}[et]
                                + (rng.randint(0, 45) if starter else 0),
                    "status": "a", "chance_of_playing_next_round": None,
                    "minutes": 0, "starts": 0, "bonus": 0, "yellow_cards": 0,
                    "expected_goals_per_90": 0.0, "expected_assists_per_90": 0.0,
                    "saves_per_90": 3.0 if et == 1 else 0.0,
                    "penalties_order": 1 if (et == 4 and k == 1) else None,
                    "ep_next": f"{rng.uniform(1, 6):.1f}",
                    "selected_by_percent": "5.0",
                })
                st = (34 - 2 * k) if starter else rng.randint(0, 6)
                mins = st * 88
                hist[eid] = [{
                    "season_name": "2025/26", "minutes": mins, "starts": st,
                    "expected_goals": round({1: 0., 2: .05, 3: .2, 4: .4}[et]
                                            * mins / 90 * rng.uniform(.5, 1.6), 2),
                    "expected_assists": round({1: 0., 2: .07, 3: .16, 4: .12}[et]
                                              * mins / 90 * rng.uniform(.5, 1.6), 2),
                    "goals_scored": 0, "assists": 0,
                    "bonus": int(mins / 90 * 0.2), "total_points": int(mins / 90 * 4)}]
    fixtures = []
    for gw in range(1, 6):
        order = list(range(1, n_teams + 1))
        rng.shuffle(order)
        for i in range(0, n_teams - 1, 2):
            fixtures.append({"event": gw, "team_h": order[i], "team_a": order[i + 1]})
    return {
        "run_dir": "(démo synthétique à l'échelle — aucune donnée réelle)",
        "synthetic": True,
        "bootstrap": {"teams": teams, "elements": elements, "events": []},
        "fixtures": fixtures, "live": {},
        "events": [{"id": g, "deadline_time": None} for g in range(1, 6)],
        "next_gw": 1, "history_past": hist,
        "my": {}, "standings": [], "rivals": {},
        "team_id": None, "league_id": None,
    }
