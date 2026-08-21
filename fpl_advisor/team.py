# -*- coding: utf-8 -*-
"""FAÇADE DE COMPATIBILITÉ — voir `fpl_advisor.optimization`.

    from fpl_advisor.optimization.squad import pick_xi, armband
    from fpl_advisor.optimization.transfers import transfer_scan
"""

from .optimization.squad import FORMATIONS, armband, pick_xi  # noqa: F401
from .optimization.transfers import (HORIZON_GWS, TRANSFER_THRESHOLD,  # noqa: F401
                                     transfer_scan)
