# -*- coding: utf-8 -*-
"""Barème FPL 2026/27 utilisé par les projections.

STATUT [F◦] : valeurs issues des règles officielles telles que rapportées ;
à confronter au rapport J0 (Help/Rules) avant toute confiance. Toute divergence
relevée par J0 se corrige ICI et nulle part ailleurs. Le rapport de
recommandation affiche ce barème pour que l'écart éventuel soit visible.
"""

# element_type FPL : 1=GB, 2=DEF, 3=MIL, 4=ATT
GOAL_POINTS = {1: 10, 2: 6, 3: 5, 4: 4}     # but marqué (GB à 10 depuis 2025/26 [F◦])
ASSIST_POINTS = 3
CS_POINTS = {1: 4, 2: 4, 3: 1, 4: 0}        # clean sheet, exige ≥ 60 minutes
APPEARANCE_LT60 = 1
APPEARANCE_GE60 = 2
SAVES_PER_POINT = 3                          # GB : 1 pt par 3 arrêts
DEFCON_POINTS = 2
DEFCON_THRESHOLD = {1: None, 2: 10, 3: 12, 4: 12}   # CBIT (DEF) / CBIRT (MIL-ATT)
GOALS_CONCEDED_MALUS_EVERY = 2               # GB/DEF : −1 par tranche de 2 encaissés
YELLOW_MALUS = -1
RED_MALUS = -3
OWN_GOAL_MALUS = -2
PEN_MISS_MALUS = -2

# Moyenne de buts par équipe et par match, prior de calibration du modèle
# d'équipe [H — ordre de grandeur Premier League, à réestimer sur données]
LEAGUE_AVG_GOALS = 1.45
