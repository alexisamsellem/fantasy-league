# -*- coding: utf-8 -*-
"""Minutes probabilistes et projections de points par composante.

Trois principes, appliqués partout :

1. RÉTRÉCISSEMENT PLUTÔT QUE SEUIL. Aucune bascule « au-dessus de N minutes on
   fait confiance » : le poids de l'observation croît continûment avec
   l'information disponible (voir priors.shrink / shrink_per90). Conséquence
   voulue : après une ou deux GW, aucune probabilité n'est 0 % ni 100 % pour un
   joueur officiellement disponible.
2. UN SIGNAL, UN USAGE. Le prix n'est plus le prior des minutes ET des taux
   offensifs. La hiérarchie offensive vient du poste, du rôle sur coups de pied
   arrêtés et de la saison précédente ; le prix ne sert qu'en dernier recours
   pour départager les minutes, et la ligne est alors marquée faible confiance.
3. PAS DE DOUBLE COMPTAGE. Un taux xG/xA observé contient déjà la force
   offensive du club où il a été produit : on ne la remultiplie qu'à hauteur de
   la part du taux qui vient du prior (team-agnostique). Voir `team_term`.

Toutes les constantes de prior vivent dans `priors.py` et sont [H, NON
CALIBRÉES] : ce module est explicite, il n'est pas calibré.
"""

import math

from . import priors, scoring

CAMEO_MINUTES = 25
SEASON_MATCHES = 38          # longueur de saison pour les taux d'une saison passée [H]


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


def appearance_history(parsed, element_id):
    """[{minutes, started}] par GW passée, la plus récente d'abord.

    `started` vient du champ officiel `starts` du live quand il existe, sinon
    de l'approximation minutes >= 60 [H] — l'origine est reportée dans la base
    affichée par le rapport."""
    idx = live_index(parsed)
    rows, exact = [], True
    for gw in sorted(idx, reverse=True):
        st = idx[gw].get(element_id) or {}
        mins = int(st.get("minutes", 0) or 0)
        if st.get("starts") is None:
            exact = False
            started = mins >= 60
        else:
            started = bool(int(st.get("starts") or 0))
        rows.append({"minutes": mins, "started": started})
    return rows, exact


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


def past_seasons(parsed, element_id):
    """Saisons passées du joueur (contrat : history_past). [] si non collecté."""
    return (parsed.get("history_past") or {}).get(element_id) or []


def _weighted_rate(history, predicate):
    """(taux pondéré par récence, nombre de GW observées)."""
    if not history:
        return None, 0
    w = priors.recency_weights(len(history))
    hist = history[:len(w)]
    total = sum(w)
    rate = sum(wi for wi, h in zip(w, hist) if predicate(h)) / total
    return rate, len(hist)


def _prior_from_past(seasons, key, positional, strength):
    """Prior de pré-saison à partir des saisons passées, rétréci vers le poste.

    Retourne (taux, source). Sans saison passée : le prior de poste, et la
    source dit explicitement quelle donnée manque."""
    if not seasons:
        return positional, None
    last = seasons[-1]
    try:
        starts = float(last.get(key) or 0)
    except (TypeError, ValueError):
        return positional, None
    w = priors.PREV_SEASON_WEIGHT
    rate = priors.shrink(starts * w, SEASON_MATCHES * w, positional, strength)
    return rate, f"saison {last.get('season_name', 'précédente')}"


def minutes_model(player, history, elements=None, parsed=None, scenario=None):
    """Distribution {p0, p_cameo, p60} + espérance de minutes + base utilisée.

    `history` accepte les deux formes : liste de minutes (compatibilité) ou
    liste de {minutes, started} produite par appearance_history()."""
    scenario = scenario or priors.params("central")
    et = player["element_type"]
    avail = availability(player)
    strength = priors.MINUTES_PRIOR_MATCHES * scenario["prior_scale"]

    hist = [h if isinstance(h, dict) else {"minutes": h, "started": h >= 60}
            for h in (history or [])]
    seasons = past_seasons(parsed or {}, player.get("id")) if parsed else []

    prior_start, src_start = _prior_from_past(
        seasons, "starts", priors.START_RATE_PRIOR[et], strength)
    prior_play = max(prior_start, priors.PLAY_RATE_PRIOR[et])
    if seasons:
        last = seasons[-1]
        try:                       # apparitions = titularisations + entrées
            mins_prev = float(last.get("minutes") or 0)
            if mins_prev > 0:
                prior_play = max(prior_play, prior_start)
        except (TypeError, ValueError):
            pass

    r_start_obs, n_gw = _weighted_rate(hist, lambda h: h["started"])
    r_play_obs, _ = _weighted_rate(hist, lambda h: h["minutes"] > 0)

    if n_gw:
        r_start = priors.shrink(r_start_obs * n_gw, n_gw, prior_start, strength)
        r_play = priors.shrink(r_play_obs * n_gw, n_gw, prior_play, strength)
        basis = f"historique {n_gw} GW rétréci vers {src_start or 'prior de poste'}"
        confidence = "moyenne" if src_start else "faible"
    else:
        r_start, r_play = prior_start, prior_play
        if src_start:
            basis = f"prior de pré-saison ({src_start})"
            confidence = "moyenne"
        else:
            # Dernier recours : aucune saison passée collectée. On NE fabrique
            # pas de hiérarchie — on garde le prior de poste et on le dit.
            basis = ("prior de poste plat — saisons passées absentes "
                     "(element-summary non collecté)")
            confidence = "faible"

    r_play = max(r_play, r_start)
    tilt = scenario["minutes_tilt"]
    p60 = min(avail, avail * r_start * priors.P60_GIVEN_START * tilt)
    p_play = min(avail, max(avail * r_play * tilt, p60))
    p_cameo = max(0.0, p_play - p60)
    xmin = 90 * p60 + CAMEO_MINUTES * p_cameo
    return {"p_play": p_play, "p60": p60, "p_cameo": p_cameo,
            "p0": 1 - p_play, "xmin": xmin, "basis": basis, "avail": avail,
            "confidence": confidence, "n_gw": n_gw}


# ----------------------------------------------------------------- équipe ----

def team_strengths(bootstrap):
    """Conservé pour compatibilité : (teams par id, moyennes des ratings FPL)."""
    teams = {t["id"]: t for t in bootstrap.get("teams", [])}
    def mean(key):
        vals = [t.get(key) or 0 for t in teams.values()]
        return (sum(vals) / len(vals)) if vals else 1.0
    return teams, {k: mean(k) for k in
                   ("strength_attack_home", "strength_attack_away",
                    "strength_defence_home", "strength_defence_away")}


def team_factors(parsed):
    """{team_id: {att, def, promoted, source}} — multiplicateurs relatifs à 1.

    Priorité à la référence publique locale (buts pour/contre de la saison
    précédente, promus traités à part). À défaut, les ratings `strength_*` FPL,
    dont le statut reste [R] NON VALIDÉ : c'est marqué dans `source` et rendu
    dans le rapport."""
    cached = parsed.get("_team_factors")
    if cached is not None:
        return cached
    boot = parsed["bootstrap"]
    teams = boot.get("teams", [])
    ref = parsed.get("team_ref")
    out = {}
    if ref:
        seen = [r for r in ref.values() if r.get("gf90") is not None]
        mean_gf = (sum(r["gf90"] for r in seen) / len(seen)) if seen else scoring.LEAGUE_AVG_GOALS
        mean_ga = (sum(r["ga90"] for r in seen) / len(seen)) if seen else scoring.LEAGUE_AVG_GOALS
        for t in teams:
            r = ref.get(t["id"]) or {"promoted": True, "gf90": None, "ga90": None}
            if r.get("promoted") or r.get("gf90") is None:
                out[t["id"]] = {"att": priors.PROMOTED_ATTACK,
                                "def": priors.PROMOTED_DEFENCE, "promoted": True,
                                "source": "prior promus (absent de la référence)"}
            else:
                out[t["id"]] = {"att": r["gf90"] / mean_gf, "def": r["ga90"] / mean_ga,
                                "promoted": False,
                                "source": "référence publique locale (saison précédente)"}
    else:
        _, means = team_strengths(boot)
        for t in teams:
            att = ((t.get("strength_attack_home") or means["strength_attack_home"])
                   + (t.get("strength_attack_away") or means["strength_attack_away"])) / 2.0
            dfn = ((t.get("strength_defence_home") or means["strength_defence_home"])
                   + (t.get("strength_defence_away") or means["strength_defence_away"])) / 2.0
            m_att = (means["strength_attack_home"] + means["strength_attack_away"]) / 2.0
            m_def = (means["strength_defence_home"] + means["strength_defence_away"]) / 2.0
            # rating de défense FPL élevé = défense FORTE → encaisse MOINS
            out[t["id"]] = {"att": att / m_att if m_att else 1.0,
                            "def": (m_def / dfn) if dfn else 1.0,
                            "promoted": False,
                            "source": "ratings FPL strength_* [R NON VALIDÉ]"}
    lo, hi = priors.OPP_FACTOR_CLAMP
    for v in out.values():
        v["att"] = max(lo, min(hi, v["att"]))
        v["def"] = max(lo, min(hi, v["def"]))
    parsed["_team_factors"] = out
    return out


def fixture_lambdas(fixture, factors):
    """(λ_domicile, λ_extérieur) — attaque × faiblesse défensive adverse."""
    h = factors.get(fixture["team_h"]) or {"att": 1.0, "def": 1.0}
    a = factors.get(fixture["team_a"]) or {"att": 1.0, "def": 1.0}
    lam_h = scoring.LEAGUE_AVG_GOALS * h["att"] * a["def"] * priors.HOME_ADVANTAGE
    lam_a = scoring.LEAGUE_AVG_GOALS * a["att"] * h["def"] / priors.HOME_ADVANTAGE
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

def _num(d, key):
    try:
        return float(d.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def set_piece_bonus(player):
    """(bump xG/90, bump xA/90, libellé) d'après le rôle sur coups de pied
    arrêtés — hiérarchie disponible dès la pré-saison, sans recourir au prix."""
    bg = ba = 0.0
    tags = []
    pen = player.get("penalties_order")
    if pen in (1, 2):
        bg += priors.PEN_XG90[pen]
        tags.append(f"penalty n°{pen}")
    fk = player.get("direct_freekicks_order")
    if fk == 1:
        bg += priors.FK_XG90[1]
        ba += priors.FK_XA90[1]
        tags.append("coups francs")
    ck = player.get("corners_and_indirect_freekicks_order")
    if ck in (1, 2):
        ba += priors.CORNER_XA90[ck]
        tags.append(f"corners n°{ck}")
    return bg, ba, (", ".join(tags) if tags else "")


def attack_rates(parsed, player, scenario=None):
    """(xG/90, xA/90, base, poids de l'observation).

    Le poids `w_obs` mesure la part du taux qui vient de minutes réellement
    jouées (donc déjà porteuse de la force du club) : il pilote l'anti-double
    comptage dans project_player."""
    scenario = scenario or priors.params("central")
    et = player["element_type"]
    k = priors.ATTACK_PRIOR_MINUTES * scenario["prior_scale"]

    bg, ba, role = set_piece_bonus(player)
    prior_g = priors.XG90_PRIOR[et] + bg
    prior_a = priors.XA90_PRIOR[et] + ba
    notes = [f"prior poste{' + ' + role if role else ''}"]

    # Niveau 1 : la saison précédente affine le prior (rétrécie, puis régressée).
    seasons = past_seasons(parsed, player.get("id"))
    prev_min = 0.0
    if seasons:
        last = seasons[-1]
        prev_min = _num(last, "minutes")
        if prev_min > 0:
            if last.get("expected_goals") is not None:
                pg = _num(last, "expected_goals") / prev_min * 90
                pa = _num(last, "expected_assists") / prev_min * 90
                src = "xG/xA saison précédente"
            else:
                pg = _num(last, "goals_scored") / prev_min * 90
                pa = _num(last, "assists") / prev_min * 90
                src = "buts/passes saison précédente (xG absent)"
            eff = min(prev_min, priors.PREV_SEASON_MAX_MINUTES) * priors.PREV_SEASON_WEIGHT
            prior_g, _ = priors.shrink_per90(pg, eff, prior_g, k)
            prior_a, _ = priors.shrink_per90(pa, eff, prior_a, k)
            notes.append(src)

    # Niveau 2 : la saison en cours, rétrécie vers ce prior — pas de seuil.
    cur_min = _num(player, "minutes")
    g90, w = priors.shrink_per90(_num(player, "expected_goals_per_90"), cur_min, prior_g, k)
    a90, _ = priors.shrink_per90(_num(player, "expected_assists_per_90"), cur_min, prior_a, k)
    if cur_min > 0:
        notes.append(f"{cur_min:.0f} min en cours (poids {w:.0%})")

    w_obs = (cur_min + min(prev_min, priors.PREV_SEASON_MAX_MINUTES)
             * priors.PREV_SEASON_WEIGHT)
    w_obs = w_obs / (w_obs + k)
    return g90, a90, " ; ".join(notes), w_obs


def bonus_rate(parsed, player, scenario=None):
    """Bonus par 90 rétréci. Le dénominateur est le temps réellement joué
    (minutes / 90) et non un nombre d'apparitions approximé par minutes // 60."""
    scenario = scenario or priors.params("central")
    et = player["element_type"]
    k = priors.BONUS_PRIOR_MINUTES * scenario["prior_scale"]
    prior = priors.BONUS90_PRIOR[et]
    seasons = past_seasons(parsed, player.get("id"))
    if seasons:
        last = seasons[-1]
        pm = _num(last, "minutes")
        if pm > 0:
            eff = min(pm, priors.PREV_SEASON_MAX_MINUTES) * priors.PREV_SEASON_WEIGHT
            prior, _ = priors.shrink_per90(_num(last, "bonus") / pm * 90, eff, prior, k)
    cur_min = _num(player, "minutes")
    obs = (_num(player, "bonus") / cur_min * 90) if cur_min > 0 else 0.0
    rate, _ = priors.shrink_per90(obs, cur_min, prior, k)
    return rate


def yellow_rate(parsed, player, scenario=None):
    """Cartons jaunes par 90, même correction de dénominateur que le bonus."""
    scenario = scenario or priors.params("central")
    k = priors.BONUS_PRIOR_MINUTES * scenario["prior_scale"]
    cur_min = _num(player, "minutes")
    obs = (_num(player, "yellow_cards") / cur_min * 90) if cur_min > 0 else 0.0
    rate, _ = priors.shrink_per90(obs, cur_min, priors.YELLOW90_PRIOR, k)
    return rate


def defcon_rate(parsed, player, scenario=None):
    """P(seuil DEFCON atteint | a joué), rétrécie vers un prior de poste.

    Corrige le comportement « 0 pour tout le monde, puis 0 % ou 100 % après un
    match » : les comptages observés sont des pseudo-comptages ajoutés au
    prior, jamais une fréquence brute."""
    scenario = scenario or priors.params("central")
    et = player["element_type"]
    thr = scoring.DEFCON_THRESHOLD.get(et)
    if thr is None:
        return 0.0, "GB : non concerné"
    strength = priors.DEFCON_PRIOR_MATCHES * scenario["prior_scale"]
    prior = priors.DEFCON_RATE_PRIOR[et]

    hits = played = 0
    fields_ok = True
    idx = live_index(parsed)
    for gw in idx:
        st = idx[gw].get(player["id"])
        if not st or int(st.get("minutes", 0) or 0) <= 0:
            continue
        cbi, tkl, rec = (st.get("clearances_blocks_interceptions"),
                         st.get("tackles"), st.get("recoveries"))
        if cbi is None or tkl is None:
            fields_ok = False
            break
        count = int(cbi or 0) + int(tkl or 0)
        if et != 2:
            count += int(rec or 0)
        played += 1
        hits += 1 if count >= thr else 0

    if not fields_ok:
        # Repli documenté : le per-90 officiel de contribution défensive s'il
        # existe (statut [F◦], sémantique non confirmée par J0), sinon prior.
        dc90 = _num(player, "defensive_contribution_per_90")
        if dc90 > 0:
            return (min(0.95, dc90 / max(scoring.DEFCON_POINTS, 1)),
                    "defensive_contribution_per_90 [F◦ non confirmé par J0]")
        return prior, "champs CBIT absents — prior de poste (faible confiance)"
    if played == 0:
        return prior, "aucun match joué — prior de poste"
    return (priors.shrink(hits, played, prior, strength),
            f"{hits}/{played} GW rétréci (prior {prior:.0%}, force {strength:.1f})")


# -------------------------------------------------------------- projection ----

def project_player(parsed, player, gw, teams=None, means=None, minutes=None,
                   scenario=None):
    """Espérance de points par composante pour une GW.

    `teams`/`means` sont conservés pour compatibilité d'appel et ignorés :
    l'adversité passe désormais par team_factors(parsed)."""
    scenario = scenario or priors.params("central")
    if minutes is None:
        hist, _ = appearance_history(parsed, player["id"])
        minutes = minutes_model(player, hist, parsed=parsed, scenario=scenario)
    factors = team_factors(parsed)
    fx = team_fixtures_for_gw(parsed["fixtures"], player["team"], gw)
    comp = {"appearance": 0.0, "goals": 0.0, "assists": 0.0, "cs": 0.0,
            "saves": 0.0, "defcon": 0.0, "bonus": 0.0, "malus": 0.0}
    if not fx:
        return {"ep": 0.0, "components": comp, "minutes": minutes,
                "n_fixtures": 0, "note": "blank GW : aucun match",
                "rate_basis": "", "defcon_basis": ""}

    et = player["element_type"]
    g90, a90, rate_basis, w_obs = attack_rates(parsed, player, scenario)
    p_dc, dc_basis = defcon_rate(parsed, player, scenario)
    b90 = bonus_rate(parsed, player, scenario)
    y90 = yellow_rate(parsed, player, scenario)
    own = factors.get(player["team"], {"att": 1.0, "def": 1.0})
    lo, hi = priors.OPP_FACTOR_CLAMP

    for f in fx:
        home = f["team_h"] == player["team"]
        opp_id = f["team_a"] if home else f["team_h"]
        opp = factors.get(opp_id, {"att": 1.0, "def": 1.0})
        lam_h, lam_a = fixture_lambdas(f, factors)
        lam_against = lam_a if home else lam_h

        # Adversité : faiblesse défensive de l'ADVERSAIRE + terrain. La force
        # offensive du club du joueur n'est ajoutée qu'à hauteur de la part du
        # taux issue du prior team-agnostique (anti double comptage).
        opp_factor = max(lo, min(hi, opp["def"] * (priors.HOME_ADVANTAGE if home
                                                   else 1 / priors.HOME_ADVANTAGE)))
        team_term = w_obs * 1.0 + (1 - w_obs) * own["att"]
        share = minutes["xmin"] / 90.0

        comp["appearance"] += minutes["p60"] * scoring.APPEARANCE_GE60 \
            + minutes["p_cameo"] * scoring.APPEARANCE_LT60
        comp["goals"] += share * g90 * opp_factor * team_term * scoring.GOAL_POINTS[et]
        comp["assists"] += share * a90 * opp_factor * team_term * scoring.ASSIST_POINTS
        comp["cs"] += minutes["p60"] * math.exp(-lam_against) * scoring.CS_POINTS[et]
        if et == 1:
            comp["saves"] += share * _num(player, "saves_per_90") / scoring.SAVES_PER_POINT
        comp["defcon"] += minutes["p_play"] * p_dc * scoring.DEFCON_POINTS
        comp["bonus"] += share * b90
        malus = share * y90 * abs(scoring.YELLOW_MALUS)
        if et in (1, 2):
            malus += minutes["p60"] * expected_conceded_malus(lam_against)
        comp["malus"] -= malus

    ep = sum(comp.values())
    return {"ep": ep, "components": comp, "minutes": minutes,
            "n_fixtures": len(fx), "rate_basis": rate_basis,
            "defcon_basis": dc_basis, "w_obs": w_obs}


def project_horizon(parsed, player, gws, teams=None, means=None, scenario=None):
    """EP par GW sur une liste de GWs (minutes supposées persistantes [H]).

    Le facteur d'horizon du scénario s'applique GW par GW : l'écart entre
    scénarios s'ouvre avec la distance, ce qui matérialise l'incertitude
    croissante au lieu de la lisser."""
    scenario = scenario or priors.params("central")
    hist, _ = appearance_history(parsed, player["id"])
    minutes = minutes_model(player, hist, parsed=parsed, scenario=scenario)
    out = {}
    for i, gw in enumerate(gws):
        ep = project_player(parsed, player, gw, minutes=minutes,
                            scenario=scenario)["ep"]
        out[gw] = ep * priors.horizon_factor(scenario, i)
    return out
