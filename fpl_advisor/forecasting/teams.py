# -*- coding: utf-8 -*-
"""Forces d'équipe et adversité : λ de buts par match, malus encaissés.

Remplaçable indépendamment (ratings FPL, référence publique locale, ou
toute autre source) sans toucher aux minutes ni aux taux joueurs."""

import math

from .. import scoring
from . import priors

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


