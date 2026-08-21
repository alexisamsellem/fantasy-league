# -*- coding: utf-8 -*-
"""Interface de sélection fournie PAR L'APPELANT.

`evaluation` doit pouvoir juger une équipe sans jamais importer `optimization` :
la direction des dépendances va de l'évaluation vers l'optimisation, pas
l'inverse. Mesurer la stabilité du top 15 exige pourtant de ré-optimiser sous
chaque scénario. On inverse donc la dépendance : l'orchestrateur passe les
trois fonctions dont l'évaluation a besoin, et l'évaluation ne connaît que
leur signature.

Effet de bord utile : un test peut injecter un sélecteur factice et vérifier
les verdicts sans faire tourner le vrai optimiseur.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class SelectionBackend:
    """Quatre fonctions, fournies par l'orchestrateur :

      select(rows, gws)    -> (effectif, valeur)
      value(squad, gws)    -> valeur d'un effectif donné
      legality(squad)      -> faits FPL (coût, quotas, joueurs par club)
      decisions(squad, gws)-> XI, banc, capitaine et vice figés par GW
    """
    select: Callable
    value: Callable
    legality: Callable
    decisions: Callable          # (squad, gws) -> {gw: {xi, bench, captain, vice}}
