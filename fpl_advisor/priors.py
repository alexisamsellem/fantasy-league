# -*- coding: utf-8 -*-
"""FAÇADE DE COMPATIBILITÉ — voir `fpl_advisor.forecasting.priors`."""

from .forecasting.priors import *      # noqa: F401,F403
from .forecasting.priors import (CONTRACT_BY_KEY, DATA_CONTRACT,  # noqa: F401
                                 SCENARIO_ORDER, SCENARIOS,
                                 availability_report, confidence_level,
                                 horizon_factor, load_team_reference,
                                 missing_required, params, recency_weights,
                                 shrink, shrink_per90)
