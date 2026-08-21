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

    return {
        "run_dir": "(démo synthétique — aucune donnée réelle)",
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
