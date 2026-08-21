# -*- coding: utf-8 -*-
"""Optimisation : choisir la meilleure équipe pour des points DÉJÀ prévus.

Ce module résout des problèmes de sélection sous contraintes. Il ne produit
aucune prévision et ne porte aucun jugement sur leur crédibilité : il consomme
le contrat de projections et applique les règles FPL.

  squad       XI, ordre du banc, capitaine et vice
  transfers   transférer ou conserver
  initial     effectif initial de 15 joueurs
"""

from . import initial, squad, transfers  # noqa: F401
from .squad import FORMATIONS, armband, pick_xi  # noqa: F401
from .transfers import HORIZON_GWS, TRANSFER_THRESHOLD, transfer_scan  # noqa: F401

__all__ = ["squad", "transfers", "initial", "pick_xi", "armband", "FORMATIONS",
           "transfer_scan", "TRANSFER_THRESHOLD", "HORIZON_GWS"]
