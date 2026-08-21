# -*- coding: utf-8 -*-
"""Taux par joueur : attaque (xG/xA), bonus, cartons, DEFCON.

Tous rétrécis vers des priors de poste explicites. Testables et
remplaçables un par un sans toucher au modèle de minutes."""

from .. import scoring
from . import priors
from .minutes import live_index, past_seasons

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


