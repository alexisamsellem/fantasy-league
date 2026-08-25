# -*- coding: utf-8 -*-
"""Priors rétrécis, contrat de données et scénarios d'incertitude.

Principe directeur : aucune quantité n'est estimée sans dire d'où elle vient.
Chaque estimation renvoie une valeur ET une provenance (`source`) + un niveau
de confiance. Quand la donnée nécessaire est absente, on ne la remplace pas
par un signal de substitution silencieux : on rétrécit vers un prior de poste
explicite et on marque la ligne « faible confiance » en nommant la source
manquante (voir DATA_CONTRACT).

Toutes les valeurs numériques de ce module sont des priors [H, NON CALIBRÉS] :
ordres de grandeur posés avant observation, à réestimer sur données réelles.
Aucune n'a été ajustée sur des résultats 2026/27 — le module ne prétend pas
être calibré, il prétend être explicite.
"""

# --------------------------------------------------------- contrat de données ----

# Ce que la couche de projection consomme, où le prendre, et ce qui casse sans.
# `key` : identifiant utilisé par availability_report().
DATA_CONTRACT = [
    {
        "key": "bootstrap_core",
        "source": "GET /api/bootstrap-static/ → elements[]",
        "fields": ["status", "chance_of_playing_next_round", "minutes",
                   "element_type", "team", "now_cost"],
        "used_for": "disponibilité, minutes observées, quotas et budget",
        "without": "aucune projection possible — arrêt",
        "required": True,
    },
    {
        "key": "starts",
        "source": "GET /api/bootstrap-static/ → elements[].starts",
        "fields": ["starts"],
        "used_for": "prior de titularisation (P(60+)) séparé de P(jouer)",
        "without": "titularisations déduites des minutes seules — confiance réduite",
        "required": False,
    },
    {
        "key": "set_pieces",
        "source": "GET /api/bootstrap-static/ → elements[].penalties_order, "
                  "direct_freekicks_order, corners_and_indirect_freekicks_order",
        "fields": ["penalties_order", "direct_freekicks_order",
                   "corners_and_indirect_freekicks_order"],
        "used_for": "hiérarchie offensive de pré-saison (rôle), sans utiliser le prix",
        "without": "priors offensifs plats par poste — hiérarchie perdue",
        "required": False,
    },
    {
        "key": "xg_xa",
        "source": "GET /api/bootstrap-static/ → elements[].expected_goals_per_90, "
                  "expected_assists_per_90",
        "fields": ["expected_goals_per_90", "expected_assists_per_90"],
        "used_for": "taux offensifs observés de la saison en cours (rétrécis)",
        "without": "priors de poste et de rôle uniquement",
        "required": False,
    },
    {
        "key": "history_past",
        "source": "GET /api/element-summary/{element_id}/ → history_past[] "
                  "(un appel public par joueur ; collecté par "
                  "`initial-squad --with-history`)",
        "fields": ["season_name", "minutes", "starts", "expected_goals",
                   "expected_assists", "bonus", "total_points"],
        "used_for": "PRIOR DE PRÉ-SAISON : minutes/titularisations et xG/xA de la "
                    "saison précédente — c'est LA source qui rend un top 15 "
                    "d'avant-GW1 défendable",
        "without": "priors plats par poste : le classement des joueurs d'un même "
                   "poste devient arbitraire — top 15 NON EXPLOITABLE",
        "required": False,
    },
    {
        "key": "team_reference",
        "source": "fichier local `data/reference/team_priors.csv` (colonnes : "
                  "team_name,goals_for,goals_against,matches,division) — à "
                  "constituer depuis une source publique gratuite, p. ex. "
                  "football-data.co.uk (E0.csv saison précédente)",
        "fields": ["goals_for", "goals_against", "matches", "division"],
        "used_for": "priors attaque/défense d'équipe indépendants, gestion des "
                    "promus, encadrement des ratings FPL non validés",
        "without": "ratings `strength_*` FPL utilisés seuls — statut [R] non "
                   "validé, adversité peu fiable",
        "required": False,
    },
    {
        "key": "ep_next",
        "source": "GET /api/bootstrap-static/ → elements[].ep_next",
        "fields": ["ep_next"],
        "used_for": "baseline publique officielle du test d'acceptation",
        "without": "repli déterministe défini à l'avance : selected_by_percent",
        "required": False,
    },
]

CONTRACT_BY_KEY = {c["key"]: c for c in DATA_CONTRACT}


def _has_field(elements, field, nonzero=False):
    """Le champ est-il réellement exploitable dans le bootstrap ?"""
    present = [e.get(field) for e in elements if field in e]
    if not present:
        return False
    if not nonzero:
        return True
    for v in present:
        try:
            if float(v or 0) != 0.0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def availability_report(parsed):
    """Quels éléments du contrat sont réellement présents dans ce snapshot.

    Retourne [{key, present, source, detail}] — rendu tel quel dans le rapport
    pour que l'absence d'une source soit visible, jamais silencieuse."""
    elements = parsed.get("bootstrap", {}).get("elements", []) or []
    hist = parsed.get("history_past") or {}
    rows = []
    for c in DATA_CONTRACT:
        key, extra = c["key"], {}
        if key == "bootstrap_core":
            ok = bool(elements)
            detail = f"{len(elements)} joueurs"
        elif key == "starts":
            ok = _has_field(elements, "starts")
            detail = "champ présent" if ok else "champ absent"
        elif key == "set_pieces":
            ok = _has_field(elements, "penalties_order", nonzero=True)
            n = sum(1 for e in elements if e.get("penalties_order"))
            detail = f"{n} tireurs de penalty identifiés" if ok else "aucun ordre renseigné"
        elif key == "xg_xa":
            ok = _has_field(elements, "expected_goals_per_90", nonzero=True)
            detail = "taux non nuls présents" if ok else "aucun taux non nul (pré-saison ?)"
        elif key == "history_past":
            n = sum(1 for v in hist.values() if v)
            ok = n > 0
            detail = f"{n} joueurs avec au moins une saison passée" if ok \
                else "AUCUNE saison passée collectée"
        elif key == "team_reference":
            ref = parsed.get("team_ref")
            # Le fichier de référence n'échoue jamais bruyamment : un club dont
            # le nom ne correspond pas au bootstrap tombe en silence dans le
            # panier « promu » et reçoit un prior générique. Compter les
            # appariements réels est le seul moyen de rendre ce défaut visible.
            apparies = sum(1 for v in (ref or {}).values() if not v["promoted"])
            promus = len(ref or {}) - apparies
            ok = apparies > 0
            detail = (f"{apparies}/{len(ref)} clubs appariés, {promus} traités "
                      "comme promus") if ref else "fichier absent"
            extra = {"apparies": apparies, "promus": promus}
        elif key == "ep_next":
            ok = _has_field(elements, "ep_next", nonzero=True)
            detail = "ep_next non nul présent" if ok else "ep_next absent ou nul"
        else:                                     # pragma: no cover - garde-fou
            ok, detail = False, "inconnu"
        row = {"key": key, "present": ok, "required": c["required"],
               "source": c["source"], "used_for": c["used_for"],
               "without": c["without"], "detail": detail}
        row.update(extra)
        rows.append(row)
    return rows


def missing_required(report):
    return [r for r in report if r["required"] and not r["present"]]


def confidence_level(report):
    """Niveau de confiance global de la couche de projection.

    « exploitable » exige la source qui porte la hiérarchie de pré-saison
    (history_past) ; sans elle, les priors sont plats par poste et le top 15
    n'est pas défendable, quel que soit le nombre de tests verts."""
    by_key = {r["key"]: r for r in report}
    if missing_required(report):
        return "bloqué", "source obligatoire absente"
    if not by_key["history_past"]["present"]:
        return "faible", ("saisons passées absentes (element-summary non "
                          "collecté) : priors de poste plats, hiérarchie "
                          "entre joueurs d'un même poste non fondée")
    if not by_key["team_reference"]["present"]:
        return "moyen", ("adversité fondée sur les ratings FPL non validés "
                         "(pas de référence d'équipe indépendante)")
    return "moyen-haut", "sources principales présentes ; calibration non prouvée"


# ------------------------------------------------------------ priors de poste ----
# 1=GB, 2=DEF, 3=MIL, 4=ATT. Tous [H, NON CALIBRÉS].

START_RATE_PRIOR = {1: 0.35, 2: 0.40, 3: 0.38, 4: 0.38}
PLAY_RATE_PRIOR = {1: 0.38, 2: 0.55, 3: 0.58, 4: 0.58}
P60_GIVEN_START = 0.88          # un titulaire sorti avant la 60e reste rare [H]

XG90_PRIOR = {1: 0.00, 2: 0.05, 3: 0.15, 4: 0.30}
XA90_PRIOR = {1: 0.00, 2: 0.07, 3: 0.14, 4: 0.11}
BONUS90_PRIOR = {1: 0.12, 2: 0.14, 3: 0.15, 4: 0.20}
DEFCON_RATE_PRIOR = {1: 0.0, 2: 0.28, 3: 0.14, 4: 0.05}
YELLOW90_PRIOR = 0.12                   # cartons jaunes par 90 [H]

# Rôle sur coups de pied arrêtés — hiérarchie disponible dès la pré-saison et
# indépendante du prix (contrat : set_pieces). Bumps additifs [H].
PEN_XG90 = {1: 0.11, 2: 0.03}           # penalties_order 1 puis 2
FK_XG90 = {1: 0.03}
FK_XA90 = {1: 0.02}
CORNER_XA90 = {1: 0.05, 2: 0.02}

# Forces de rétrécissement (unités : matchs pour les taux binaires, minutes
# pour les taux par 90). Plus la force est grande, plus on régresse vers le
# prior de poste.
MINUTES_PRIOR_MATCHES = 3.0     # prior de poste = 3 matchs d'information
ATTACK_PRIOR_MINUTES = 900.0            # ~10 matchs pleins
BONUS_PRIOR_MINUTES = 900.0
DEFCON_PRIOR_MATCHES = 6.0

# Régression saison → saison : une saison passée ne vaut pas une saison en
# cours (transferts, âge, changement de rôle) [H].
PREV_SEASON_WEIGHT = 0.65
PREV_SEASON_MAX_MINUTES = 1800.0        # plafond d'information d'une saison passée

# Pondération de récence sur l'historique live (la GW la plus récente d'abord).
# Décroissance géométrique : l'information sature, elle ne devient jamais
# certitude — c'est ce qui empêche un 0 %/100 % après une ou deux GW.
RECENCY_DECAY = 0.85
RECENCY_MAX_GWS = 6

# Adversité et avantage du terrain
HOME_ADVANTAGE = 1.12                   # [H]
PROMOTED_ATTACK = 0.82                  # promus : attaque plus faible [H]
PROMOTED_DEFENCE = 1.18                 # promus : encaissent davantage [H]
OPP_FACTOR_CLAMP = (0.65, 1.55)


# ------------------------------------------------------------------ shrinkage ----

def shrink(successes, trials, prior_rate, strength):
    """Taux binaire rétréci (Beta-Binomial en forme de pseudo-comptages).

    Ne renvoie jamais exactement 0 ni 1 tant que strength > 0 et
    0 < prior_rate < 1 : une seule apparition ne peut pas produire une
    certitude."""
    strength = max(strength, 1e-9)
    return (successes + strength * prior_rate) / (trials + strength)


def shrink_per90(obs_rate, obs_minutes, prior_rate, k_minutes):
    """Taux par 90 rétréci vers un prior, sans seuil de bascule.

    Remplace le « on fait confiance au-dessus de 180 minutes » : le poids de
    l'observation croît continûment avec les minutes jouées."""
    k_minutes = max(k_minutes, 1e-9)
    w = obs_minutes / (obs_minutes + k_minutes)
    return w * obs_rate + (1 - w) * prior_rate, w


def recency_weights(n):
    n = min(n, RECENCY_MAX_GWS)
    return [RECENCY_DECAY ** i for i in range(n)]


# ------------------------------------------------------------------ scénarios ----
# Trois jeux de paramètres : l'incertitude est représentée en re-projetant,
# pas en habillant un chiffre unique. `prior_scale` change le rétrécissement
# (donc le CLASSEMENT relatif des joueurs à petit échantillon), `horizon_decay`
# représente l'incertitude croissante GW après GW, `minutes_tilt` incline les
# probabilités de minutes.

SCENARIOS = {
    "prudent": {"label": "prudent", "prior_scale": 1.8, "horizon_decay": -0.07,
                "minutes_tilt": 0.92,
                "note": "rétrécissement fort vers les priors de poste, minutes "
                        "revues à la baisse, décote croissante avec l'horizon"},
    "central": {"label": "central", "prior_scale": 1.0, "horizon_decay": 0.0,
                "minutes_tilt": 1.0,
                "note": "paramètres de référence"},
    "favorable": {"label": "favorable", "prior_scale": 0.6, "horizon_decay": 0.07,
                  "minutes_tilt": 1.06,
                  "note": "confiance accrue dans les taux observés et dans la "
                          "titularisation"},
}
SCENARIO_ORDER = ["prudent", "central", "favorable"]


def params(name="central"):
    return SCENARIOS[name]


def horizon_factor(scenario, gw_index):
    """Facteur appliqué à la GW n° gw_index (0 = première GW de l'horizon).
    L'écart entre scénarios s'ouvre avec la distance — l'incertitude croît."""
    return max(0.3, 1.0 + scenario["horizon_decay"] * gw_index)


# --------------------------------------------------- référence d'équipe (CSV) ----

def load_team_reference(path, teams):
    """Charge `data/reference/team_priors.csv` s'il existe.

    Contrat de colonnes : team_name,goals_for,goals_against,matches,division.
    `division` vaut 1 pour la Premier League de la saison précédente, autre
    chose (2, championship, …) pour un club promu. Les clubs du bootstrap
    absents du fichier sont traités comme promus.

    Retourne {team_id: {"gf90", "ga90", "promoted", "source"}} ou None si le
    fichier est absent. Aucune donnée n'est inventée : un fichier absent
    renvoie None et la couche appelante le signale."""
    import csv
    import os
    if not path or not os.path.exists(path):
        return None
    by_name = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("team_name") or "").strip().lower()
            if not name:
                continue
            try:
                matches = float(row.get("matches") or 0)
                gf = float(row.get("goals_for") or 0)
                ga = float(row.get("goals_against") or 0)
            except (TypeError, ValueError):
                continue
            if matches <= 0:
                continue
            by_name[name] = {"gf90": gf / matches, "ga90": ga / matches,
                             "division": (row.get("division") or "1").strip()}
    if not by_name:
        return None
    out = {}
    for t in teams:
        hit = None
        for cand in (t.get("name"), t.get("short_name")):
            hit = by_name.get((cand or "").strip().lower())
            if hit:
                break
        if hit and str(hit["division"]) in ("1", "1.0", "E0", "premier league"):
            out[t["id"]] = {"gf90": hit["gf90"], "ga90": hit["ga90"],
                            "promoted": False, "source": "référence publique locale"}
        else:
            out[t["id"]] = {"gf90": None, "ga90": None, "promoted": True,
                            "source": "promu ou absent de la référence — prior promus"}
    return out
