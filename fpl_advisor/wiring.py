# -*- coding: utf-8 -*-
"""Câblage des couches — le seul endroit qui les connaît toutes les deux.

`evaluation` a besoin de ré-optimiser pour mesurer la stabilité, mais ne doit
pas dépendre de `optimization`. On construit donc ici l'adaptateur qui satisfait
l'interface demandée par l'évaluation à partir de l'optimiseur réel. Un test
peut fabriquer le même objet avec des fonctions factices.
"""

from .evaluation.backend import SelectionBackend
from .optimization import initial as opt_initial
from .optimization import squad as squad_rules
from .optimization import weekly as opt_weekly


def _decisions(squad, gws):
    """XI, banc, capitaine et vice figés pour chaque GW de l'horizon."""
    out = {}
    for gw in gws:
        rows = [dict(r, ep=r["eps"][gw]) for r in squad]
        xi, bench = squad_rules.pick_xi(rows)
        band = squad_rules.armband(xi)
        out[str(gw)] = {
            "xi": [p["id"] for p in xi],
            "bench": [p["id"] for p in bench],
            "captain": band["captain"]["id"],
            "vice": band["vice"]["id"],
        }
    return out


def _select(rows, gws):
    return opt_initial.optimize_squad(opt_initial.build_pool(rows), gws)


def selection_backend():
    """Adaptateur standard : l'optimiseur réel du dépôt."""
    return SelectionBackend(select=_select, value=opt_initial.squad_value,
                            legality=opt_initial.legality, decisions=_decisions,
                            weekly=opt_weekly.weekly_decision)
