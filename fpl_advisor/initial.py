# -*- coding: utf-8 -*-
"""Mode effectif initial — orchestration des trois couches.

Ce fichier ne contient aucune règle métier : il câble le pipeline dans le seul
ordre autorisé.

    snapshot  →  forecasting  →  contrat  →  evaluation  →  optimization  →  rapport

Chaque étape ne connaît que la précédente par son contrat. On peut donc :
  - remplacer le moteur de prévision sans toucher à l'optimiseur ;
  - refuser de publier une équipe sans empêcher de la calculer ;
  - repartir d'un contrat figé sur disque, sans snapshot ni recalcul.

Les noms historiques (`BUDGET`, `optimize_squad`, `build_pool`…) restent
exportés ici par compatibilité : ils vivent désormais dans
`fpl_advisor.optimization.initial`.
"""

from . import wiring
from .optimization import initial as opt_initial
from .evaluation import quality, stability
from .forecasting import build_projection_set
from .optimization import squad as squad_rules
from .optimization.initial import (BUDGET, INITIAL_HORIZON_GWS,  # noqa: F401
                                   MAX_PER_CLUB, MAX_SWAP_ROUNDS, POOL_CHEAP,
                                   POOL_TOP, SQUAD_QUOTA, build_pool,
                                   cheapest_squad, legality, optimize_squad,
                                   squad_value)

STABILITY_MIN_OVERLAP = quality.STABILITY_MIN_OVERLAP   # compatibilité


def build_contract(parsed):
    """Étape 1 : snapshot → contrat de projections (couche forecasting)."""
    gw = parsed["next_gw"]
    if gw is None:
        raise SystemExit("Aucune GW future dans le calendrier : saison terminée ?")
    gws = list(range(gw, min(gw + INITIAL_HORIZON_GWS, 39)))
    return build_projection_set(parsed, gws)


def build_from_contract(contract, backend=None):
    """Étapes 2 à 4 : optimisation, évaluation, mise en forme.

    N'accède à AUCUNE donnée brute : tout vient du contrat. C'est exactement le
    chemin emprunté quand on repart d'un fichier de projections figé."""
    backend = backend or wiring.selection_backend()
    gws = list(contract.horizon)
    gw = contract.gw

    # --- optimisation (scénario central)
    squad, value, pool = opt_initial.select_squad(contract, "central")
    central_ids = {r["id"] for r in squad}
    facts = legality(squad)

    # --- évaluation : stabilité entre scénarios, puis verdict
    scenarios, min_overlap = stability.top15_stability(
        contract, backend, central_ids, [r["id"] for r in pool])

    display = contract.display_rows([r["id"] for r in squad], gw)
    xi, bench = squad_rules.pick_xi(display)
    band = squad_rules.armband(xi)

    facts.update({"captain_p60": band["captain"]["p60"],
                  "captain_name": band["captain"]["web_name"]})
    verdict = quality.assess(contract, min_overlap=min_overlap, squad_facts=facts,
                             squad_ids=sorted(central_ids))

    return {
        "mode": "initial",
        "gw": gw, "deadline": contract.deadline, "horizon": gws,
        "squad": display, "xi": xi, "bench": bench, "armband": band,
        "budget": BUDGET, "cost": facts["cost"], "bank": BUDGET - facts["cost"],
        "value4": value, "pool_size": len(pool),
        "scenarios": scenarios, "min_overlap": min_overlap,
        "stable": min_overlap >= STABILITY_MIN_OVERLAP,
        "stability_threshold": STABILITY_MIN_OVERLAP,
        "verdict": verdict,
        "contract_version": contract.contract_version,
        "model_version": contract.model_version,
        "availability": contract.availability,
        "confidence": contract.data_confidence,
        "confidence_why": contract.data_confidence_why,
        "team_factor_source": contract.team_factor_source,
        "teams": {int(k): v for k, v in contract.teams.items()},
        "run_dir": contract.snapshot,
        "synthetic": contract.synthetic,
        "n_history_gws": contract.n_history_gws,
    }


def build_initial_recommendation(parsed):
    """Chemin complet : snapshot → rapport. Conservé pour compatibilité."""
    return build_from_contract(build_contract(parsed))
