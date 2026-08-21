# -*- coding: utf-8 -*-
"""Minutes probabilistes et projections de points par composante (V0).

Méthode volontairement simple et explicable ; chaque hypothèse [H] est
affichée dans le rapport. Les minutes priment : tout est conditionné à la
distribution {absent, entrée en jeu (~25 min), titulaire (~90 min)}.
"""

import math

from . import scoring

RECENCY_WEIGHTS = [0.35, 0.25, 0.20, 0.12, 0.08]   # GW la plus récente d'abord [H]
CAMEO_MINUTES = 25
MIN_SEASON_MINUTES_FOR_RATES = 180   # en dessous, taux par 90 jugés non fiables [H]


# ---------------------------------------------------------------- minutes ----

def live_index(parsed):
    """{gw: {element_id: stats}} — construit une fois, mis en cache."""
    idx = parsed.get("_live_idx")
    if idx is None:
        idx = {gw: {el["id"]: el.get("stats", {}) for el in data.get("elements", [])}
               for gw, data in parsed.get("live", {}).items()}
        parsed["_live_idx"] = idx
    return idx


def minutes_history(parsed, element_id):
    """Minutes par GW passée, la plus récente d'abord."""
    idx = live_index(parsed)
    return [int((idx[gw].get(element_id) or {}).get("minutes", 0) or 0)
            for gw in sorted(idx, reverse=True)]


def availability(player):
    """P(disponible) d'après le statut officiel FPL (lent mais fiable)."""
    status = player.get("status", "a")
    chance = player.get("chance_of_playing_next_round")
    if status == "a":
        return 1.0
    if status == "d":
        return (chance / 100.0) if isinstance(chance, (int, float)) else 0.5
    # i (blessé), s (suspendu), u (parti), n (indisponible)
    return (chance / 100.0) if isinstance(chance, (int, float)) else 0.0


def _weighted_share(history, predicate):
    if not history:
        return None
    w = RECENCY_WEIGHTS[:len(history)]
    total = sum(w)
    return sum(wi for wi, m in zip(w, history) if predicate(m)) / total


def price_percentile(player, elements):
    """Percentile de prix parmi les joueurs du même club et du même poste."""
    peers = [e["now_cost"] for e in elements
             if e["team"] == player["team"] and e["element_type"] == player["element_type"]]
    if len(peers) <= 1:
        return 1.0
    below = sum(1 for c in peers if c < player["now_cost"])
    return below / (len(peers) - 1)


def minutes_model(player, history, elements):
    """Distribution {p0, p_cameo, p60} + espérance de minutes + base utilisée."""
    avail = availability(player)
    r_play = _weighted_share(history, lambda m: m > 0)
    r_60 = _weighted_share(history, lambda m: m >= 60)
    if r_play is None:
        # Avant tout historique : prior grossier par prix relatif au club [H]
        pct = price_percentile(player, elements)
        r_play = min(0.90, 0.20 + 0.60 * pct)
        r_60 = 0.85 * r_play
        basis = "prior prix (aucun historique)"
    else:
        basis = f"historique {len(history)} GW"
    p_play = avail * r_play
    p60 = min(p_play, avail * (r_60 or 0.0))
    p_cameo = max(0.0, p_play - p60)
    xmin = 90 * p60 + CAMEO_MINUTES * p_cameo
    return {"p_play": p_play, "p60": p60, "p_cameo": p_cameo,
            "p0": 1 - p_play, "xmin": xmin, "basis": basis, "avail": avail}


# ----------------------------------------------------------------- équipe ----

def team_strengths(bootstrap):
    teams = {t["id"]: t for t in bootstrap.get("teams", [])}
    def mean(key):
        vals = [t.get(key) or 0 for t in teams.values()]
        return (sum(vals) / len(vals)) if vals else 1.0
    return teams, {k: mean(k) for k in
                   ("strength_attack_home", "strength_attack_away",
                    "strength_defence_home", "strength_defence_away")}


def fixture_lambdas(fixture, teams, means):
    """(λ_home, λ_away) par un modèle multiplicatif sur les forces FPL [H]."""
    h, a = teams.get(fixture["team_h"]), teams.get(fixture["team_a"])
    if not h or not a:
        return scoring.LEAGUE_AVG_GOALS, scoring.LEAGUE_AVG_GOALS
    att_h = (h.get("strength_attack_home") or means["strength_attack_home"]) / means["strength_attack_home"]
    def_a = (a.get("strength_defence_away") or means["strength_defence_away"]) / means["strength_defence_away"]
    att_a = (a.get("strength_attack_away") or means["strength_attack_away"]) / means["strength_attack_away"]
    def_h = (h.get("strength_defence_home") or means["strength_defence_home"]) / means["strength_defence_home"]
    lam_h = scoring.LEAGUE_AVG_GOALS * att_h / max(def_a, 0.25)
    lam_a = scoring.LEAGUE_AVG_GOALS * att_a / max(def_h, 0.25)
    clamp = lambda x: max(0.4, min(3.5, x))
    return clamp(lam_h), clamp(lam_a)


def team_fixtures_for_gw(fixtures, team_id, gw):
    return [f for f in fixtures if f.get("event") == gw
            and (f.get("team_h") == team_id or f.get("team_a") == team_id)]


def _poisson_pmf(lam, k):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def expected_conceded_malus(lam):
    """E[floor(X/2)] pour X ~ Poisson(λ) — malus buts encaissés GB/DEF."""
    return sum(_poisson_pmf(lam, k) * (k // 2) for k in range(0, 11))


# ----------------------------------------------------------- taux joueurs ----

def _per90(player, key):
    try:
        return float(player.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def attack_rates(player, elements):
    """(xG/90, xA/90) — officiels si assez de minutes, sinon prior par prix [H]."""
    if int(player.get("minutes") or 0) >= MIN_SEASON_MINUTES_FOR_RATES:
        return (_per90(player, "expected_goals_per_90"),
                _per90(player, "expected_assists_per_90"),
                "xG/xA officiels par 90")
    pct = price_percentile(player, elements)
    base_g = {1: 0.00, 2: 0.05, 3: 0.18, 4: 0.32}[player["element_type"]]
    base_a = {1: 0.00, 2: 0.06, 3: 0.14, 4: 0.10}[player["element_type"]]
    scale = 0.5 + 1.0 * pct
    return base_g * scale, base_a * scale, "prior par poste et prix (peu de minutes)"


def defcon_rate(parsed, player):
    """P(seuil DEFCON atteint | a joué), estimée sur l'historique live via les
    champs officiels CBIT/récupérations ; None si champs indisponibles."""
    thr = scoring.DEFCON_THRESHOLD.get(player["element_type"])
    if thr is None:
        return 0.0, "GB : non concerné"
    hits = played = 0
    idx = live_index(parsed)
    for gw in idx:
        st = idx[gw].get(player["id"])
        if not st or int(st.get("minutes", 0) or 0) <= 0:
            continue
        cbi = st.get("clearances_blocks_interceptions")
        tkl = st.get("tackles")
        rec = st.get("recoveries")
        if cbi is None or tkl is None:
            return None, "champs CBIT absents du live — DEFCON estimé à 0"
        count = int(cbi or 0) + int(tkl or 0)
        if player["element_type"] != 2:
            count += int(rec or 0)
        played += 1
        hits += 1 if count >= thr else 0
    if played == 0:
        return 0.0, "aucun match joué dans l'historique"
    return hits / played, f"empirique sur {played} GW"


# -------------------------------------------------------------- projection ----

def project_player(parsed, player, gw, teams, means, minutes=None):
    """Espérance de points par composante pour une GW. Retourne un dict
    détaillé ; EP = somme des composantes. BGW → 0 ; DGW → somme des matchs."""
    elements = parsed["bootstrap"]["elements"]
    minutes = minutes or minutes_model(player, minutes_history(parsed, player["id"]), elements)
    fx = team_fixtures_for_gw(parsed["fixtures"], player["team"], gw)
    comp = {"appearance": 0.0, "goals": 0.0, "assists": 0.0, "cs": 0.0,
            "saves": 0.0, "defcon": 0.0, "bonus": 0.0, "malus": 0.0}
    if not fx:
        return {"ep": 0.0, "components": comp, "minutes": minutes,
                "n_fixtures": 0, "note": "blank GW : aucun match"}

    et = player["element_type"]
    g90, a90, rate_basis = attack_rates(player, elements)
    p_dc, dc_basis = defcon_rate(parsed, player)
    if p_dc is None:
        p_dc = 0.0
    appearances = max(1, int(player.get("minutes") or 0) // 60)
    bonus_rate = min(1.0, float(player.get("bonus") or 0) / appearances) if player.get("minutes") else 0.0
    yellows_rate = min(0.35, float(player.get("yellow_cards") or 0) / appearances) if player.get("minutes") else 0.1

    for f in fx:
        home = f["team_h"] == player["team"]
        lam_h, lam_a = fixture_lambdas(f, teams, means)
        lam_for, lam_against = (lam_h, lam_a) if home else (lam_a, lam_h)
        f_opp = max(0.6, min(1.6, lam_for / scoring.LEAGUE_AVG_GOALS))
        share = minutes["xmin"] / 90.0
        comp["appearance"] += minutes["p60"] * scoring.APPEARANCE_GE60 \
            + minutes["p_cameo"] * scoring.APPEARANCE_LT60
        comp["goals"] += share * g90 * f_opp * scoring.GOAL_POINTS[et]
        comp["assists"] += share * a90 * f_opp * scoring.ASSIST_POINTS
        comp["cs"] += minutes["p60"] * math.exp(-lam_against) * scoring.CS_POINTS[et]
        if et == 1:
            comp["saves"] += share * _per90(player, "saves_per_90") / scoring.SAVES_PER_POINT
        comp["defcon"] += minutes["p_play"] * p_dc * scoring.DEFCON_POINTS
        comp["bonus"] += minutes["p_play"] * bonus_rate
        malus = minutes["p_play"] * yellows_rate * abs(scoring.YELLOW_MALUS)
        if et in (1, 2):
            malus += minutes["p60"] * expected_conceded_malus(lam_against)
        comp["malus"] -= malus

    ep = sum(comp.values())
    return {"ep": ep, "components": comp, "minutes": minutes,
            "n_fixtures": len(fx), "rate_basis": rate_basis, "defcon_basis": dc_basis}


def project_horizon(parsed, player, gws, teams, means):
    """EP par GW sur une liste de GWs (minutes supposées persistantes [H])."""
    elements = parsed["bootstrap"]["elements"]
    minutes = minutes_model(player, minutes_history(parsed, player["id"]), elements)
    return {gw: project_player(parsed, player, gw, teams, means, minutes=minutes)["ep"]
            for gw in gws}
