# -*- coding: utf-8 -*-
"""Stabilité du top 15 entre scénarios.

Une équipe qui change beaucoup selon le jeu de priors retenu n'est pas une
recommandation : c'est une option parmi plusieurs équivalentes. On le mesure en
ré-optimisant un effectif complet sous chaque scénario, à vivier figé.
"""


def top15_stability(contract, backend, central_ids, pool_ids):
    """Retourne (lignes par scénario, recouvrement minimal avec le central).

    Le vivier est figé (celui du scénario central) pour que la comparaison
    porte sur les projections, pas sur un changement de présélection."""
    gws = list(contract.horizon)
    central_ids = set(central_ids)
    pool_ids = set(pool_ids)
    rows, min_overlap = [], len(central_ids)
    for name in contract.scenario_names:
        scored = [r for r in contract.rows_for(name) if r["id"] in pool_ids]
        squad, value = backend.select(scored, gws)
        ids = {r["id"] for r in squad}
        overlap = len(ids & central_ids)
        min_overlap = min(min_overlap, overlap)
        central_rows = [r for r in scored if r["id"] in central_ids]
        meta = contract.scenarios_meta.get(name, {})
        rows.append({
            "name": name, "label": meta.get("label", name),
            "note": meta.get("note", ""),
            "own_value": value, "overlap": overlap,
            "central_value": (backend.value(central_rows, gws)
                              if len(central_rows) == len(central_ids) else None),
            "squad_ids": ids,
        })
    return rows, min_overlap
