# -*- coding: utf-8 -*-
"""Stabilité entre scénarios — effectif initial et décisions de la semaine.

Une décision qui change selon le jeu de priors retenu n'est pas une
recommandation : c'est une option parmi plusieurs équivalentes. On le mesure en
rejouant la décision sous chaque scénario, à données figées.

  top15_stability       mode effectif initial : recouvrement du top 15
  decision_stability    mode hebdomadaire : capitaine, XI et transfert
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


def decision_stability(contract, backend, squad_ids, bank, reference="central"):
    """Rejoue la semaine sous chaque scénario, effectif détenu figé.

    L'effectif ne bouge pas d'un scénario à l'autre — c'est celui du manager.
    Ce qui bouge, ce sont les décisions : qui porte le brassard, qui joue, et
    faut-il transférer. Retourne (lignes par scénario, résumé des accords).

    L'accord se compte sur ce qui est réellement actionnable : l'identité du
    capitaine, la décision transférer/conserver, et — quand elle vaut
    « transférer » — le couple sortant/entrant exact. Deux scénarios qui
    concluent « transférer » vers deux joueurs différents ne sont PAS d'accord.
    """
    if backend.weekly is None:
        raise ValueError("le backend ne fournit pas de fonction `weekly` : "
                         "impossible de mesurer la stabilité des décisions")
    gws = list(contract.horizon)
    squad_ids = list(squad_ids)

    per_scenario = {}
    for name in contract.scenario_names:
        per_scenario[name] = backend.weekly(contract.rows_for(name), squad_ids,
                                            bank, gws)
    ref = per_scenario[reference]

    rows, captain_ok, decision_ok, swap_ok = [], 0, 0, 0
    xi_min = len(ref["xi_ids"])
    for name in contract.scenario_names:
        d = per_scenario[name]
        meta = contract.scenarios_meta.get(name, {})
        same_captain = d["captain_id"] == ref["captain_id"]
        same_decision = d["decision"] == ref["decision"]
        # Le couple exact ne se compare que si les deux scénarios transfèrent.
        same_swap = same_decision and d["swap"] == ref["swap"]
        overlap = len(d["xi_ids"] & ref["xi_ids"])
        captain_ok += same_captain
        decision_ok += same_decision
        swap_ok += same_swap
        xi_min = min(xi_min, overlap)
        top = d["transfer"]["candidates"][0] if d["transfer"]["candidates"] else None
        rows.append({
            "name": name, "label": meta.get("label", name),
            "note": meta.get("note", ""),
            "captain_id": d["captain_id"],
            "captain_name": d["armband"]["captain"]["web_name"],
            "captain_ep": d["armband"]["captain"]["ep"],
            "decision": d["decision"],
            "swap_label": (f"{top['out']['web_name']} → {top['in']['web_name']} "
                           f"(+{top['delta3']:.2f})") if top else "—",
            "xi_overlap": overlap,
            "same_captain": same_captain, "same_decision": same_decision,
        })

    n = len(contract.scenario_names)
    summary = {"n_scenarios": n, "reference": reference,
               "captain_agree": captain_ok, "decision_agree": decision_ok,
               "swap_agree": swap_ok, "xi_min_overlap": xi_min,
               "xi_size": len(ref["xi_ids"])}
    return rows, summary
