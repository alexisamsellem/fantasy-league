# -*- coding: utf-8 -*-
"""Minutes probabilistes : disponibilité, titularisations, distribution.

Seul endroit qui décide combien de minutes un joueur va jouer. Les taux
offensifs (`rates`) et la projection finale (`projection`) consomment
cette sortie sans la recalculer."""

from . import priors

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

    # Comptages bruts sur la même fenêtre que les taux pondérés. Ils ne servent
    # à aucun calcul : ils expliquent le résultat. Un titulaire confirmé qui
    # sort à 55 % de P(60+) sans alerte d'infirmerie n'est pas un bug — c'est
    # une absence observée, et le lecteur doit pouvoir le voir.
    window = hist[:n_gw] if n_gw else []
    n_starts_obs = sum(1 for h in window if h["started"])
    n_apps_obs = sum(1 for h in window if h["minutes"] > 0)

    if n_gw:
        r_start = priors.shrink(r_start_obs * n_gw, n_gw, prior_start, strength)
        r_play = priors.shrink(r_play_obs * n_gw, n_gw, prior_play, strength)
        basis = (f"historique {n_gw} GW ({n_starts_obs} titularisation"
                 f"{'s' if n_starts_obs > 1 else ''}, {n_apps_obs} apparition"
                 f"{'s' if n_apps_obs > 1 else ''}) rétréci vers "
                 f"{src_start or 'prior de poste'}")
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
            "confidence": confidence, "n_gw": n_gw,
            "n_starts_obs": n_starts_obs, "n_apps_obs": n_apps_obs}


