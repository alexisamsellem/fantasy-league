# -*- coding: utf-8 -*-
"""Prévision : transformer des données joueurs et équipes en points espérés.

C'est le SEUL endroit du dépôt qui produit une prévision. Rien d'autre ne doit
lire le snapshot pour en déduire des points. La sortie publique est le contrat
de projections (`contract.ProjectionSet`).

Sous-modules, séparés parce qu'ils se testent et se remplacent un par un :
  priors      priors de poste, contrat de données, scénarios
  minutes     disponibilité et distribution de minutes
  teams       forces d'équipe, adversité, buts encaissés
  rates       attaque, bonus, cartons, DEFCON
  projection  assemblage des composantes de points
  contract    structure figée et sérialisable consommée par le reste
"""

from . import minutes, priors, projection, rates, teams  # noqa: F401
from .contract import (CONTRACT_VERSION, MODEL_VERSION, PlayerProjection,
                       ProjectionSet, build_projection_set)  # noqa: F401

__all__ = ["priors", "minutes", "teams", "rates", "projection",
           "ProjectionSet", "PlayerProjection", "build_projection_set",
           "CONTRACT_VERSION", "MODEL_VERSION"]
