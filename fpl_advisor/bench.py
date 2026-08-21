# -*- coding: utf-8 -*-
"""FAÇADE DE COMPATIBILITÉ — le banc d'essai vit dans `fpl_advisor.evaluation`.

Les fonctions de `evaluation` consomment un contrat de projections. Cette
façade accepte aussi un snapshot brut : elle construit alors le contrat pour
l'appelant, ce qui évite de casser les usages existants.
"""

from . import wiring
from .evaluation.baseline import (BASELINE_FALLBACK, BASELINE_PRIMARY,  # noqa: F401
                                  baseline_field as _baseline_field,
                                  baseline_rows as _baseline_rows)
from .evaluation.bench import COMPARISON_PROTOCOL  # noqa: F401
from .evaluation.bench import build_bench as _build_bench
from .evaluation.bench import score_frozen, write_bench  # noqa: F401


def _as_contract(source):
    """Accepte un contrat de projections ou un snapshot brut."""
    if hasattr(source, "rows_for"):
        return source
    from .initial import build_contract
    return build_contract(source)


def build_bench(source, backend=None):
    return _build_bench(_as_contract(source), backend or wiring.selection_backend())


def baseline_field(source):
    return _baseline_field(_as_contract(source))


def baseline_rows(source, gws=None):
    return _baseline_rows(_as_contract(source))
