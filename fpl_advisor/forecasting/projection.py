# -*- coding: utf-8 -*-
"""Assemblage final : composantes de points par joueur et par GW.

Combine minutes, taux et adversité. C'est la seule fonction qui produit
des points espérés ; tout le reste du dépôt consomme son résultat via le
contrat de projections (`contract.py`)."""

import math

from .. import scoring
from . import priors
from .minutes import appearance_history, minutes_model
from .rates import _num, attack_rates, bonus_rate, defcon_rate, yellow_rate
from .teams import (expected_conceded_malus, fixture_lambdas, team_factors,
                    team_fixtures_for_gw)

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
