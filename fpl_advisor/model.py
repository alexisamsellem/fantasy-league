# -*- coding: utf-8 -*-
"""FAÇADE DE COMPATIBILITÉ — le moteur vit désormais dans `fpl_advisor.forecasting`.

Ce fichier ne contient plus aucune logique : il ré-exporte les fonctions à leur
ancien emplacement pour ne casser aucun import existant. Pour du code nouveau,
importer directement :

    from fpl_advisor.forecasting import build_projection_set   # contrat complet
    from fpl_advisor.forecasting import minutes, rates, teams, projection
"""

from .forecasting.minutes import (CAMEO_MINUTES, SEASON_MATCHES,  # noqa: F401
                                  appearance_history, availability, live_index,
                                  minutes_history, minutes_model, past_seasons)
from .forecasting.projection import project_horizon, project_player  # noqa: F401
from .forecasting.rates import (attack_rates, bonus_rate, defcon_rate,  # noqa: F401
                                set_piece_bonus, yellow_rate)
from .forecasting.teams import (expected_conceded_malus, fixture_lambdas,  # noqa: F401
                                team_factors, team_fixtures_for_gw, team_strengths)
