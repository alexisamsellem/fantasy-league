# -*- coding: utf-8 -*-
"""Évaluation : vérifier les prévisions avant de laisser publier une équipe.

Ce module ne prévoit rien et ne choisit rien. Il lit le contrat de projections
et rend un verdict déterministe — accepté, avertissement ou bloqué — plus les
éléments de comparaison (baseline publique, stabilité entre scénarios).

Il n'importe jamais `optimization` : mesurer la stabilité exige de
ré-optimiser, donc l'appelant injecte un `SelectionBackend` (voir `backend.py`).

  quality     verdict en trois états et ses seuils de publication
  calibration les probabilités annoncées se réalisent-elles ?
  stability   stabilité entre scénarios : top 15, décisions de la semaine
  baseline    repère public naïf (ep_next, repli selected_by_percent)
  bench       protocole de comparaison figé et son exécution
  benchmark   points réels contre ep et ep_next, intervalle par grappes
  recalibration carte de Platt de P(60+), ajustée sans regard vers l'avant
"""

from . import (backend, baseline, bench, benchmark, calibration,  # noqa: F401
               quality, recalibration, stability)
from .backend import SelectionBackend  # noqa: F401
from .quality import (ACCEPTED, BLOCKED, WARNING, Check, Verdict,  # noqa: F401
                      assess, assess_weekly)
from .stability import decision_stability, top15_stability  # noqa: F401

__all__ = ["quality", "stability", "baseline", "bench", "benchmark", "backend",
           "calibration", "recalibration",
           "SelectionBackend", "assess", "assess_weekly", "Verdict", "Check",
           "top15_stability", "decision_stability",
           "ACCEPTED", "WARNING", "BLOCKED"]
