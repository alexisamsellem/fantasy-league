# -*- coding: utf-8 -*-
"""Effectif initial : 15 joueurs sous les contraintes FPL exactes.

Ce module ne lit JAMAIS le snapshot, ne recalcule JAMAIS une minute et
n'importe rien de `forecasting`. Il reçoit des lignes issues du contrat de
projections (`ProjectionSet.rows_for`) et résout un problème de sélection sous
contraintes. Il ne décide pas non plus si les prévisions sont crédibles :
`evaluation` s'en charge, en amont.

L'optimiseur est délibérément simple (montée locale par échanges un-pour-un) :
un optimum local sur de bonnes projections vaut mieux qu'un optimum global sur
de mauvaises.
"""

from . import squad as squad_rules

BUDGET = 1000                            # 100,0 M£ en dixièmes — règle FPL
SQUAD_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}   # 2 GB, 5 DEF, 5 MIL, 3 ATT
MAX_PER_CLUB = 3
INITIAL_HORIZON_GWS = 4                  # équipe statique optimisée sur 4 GW [H]
POOL_TOP = 20                            # par poste : meilleurs EP cumulés
POOL_CHEAP = 8                           # par poste : moins chers (banc)
MAX_SWAP_ROUNDS = 80                     # garde-fou de terminaison


def build_pool(rows):
    """Présélection par poste : les POOL_TOP meilleurs par EP CUMULÉE SUR
    L'HORIZON (jamais sur la seule première GW, sinon un joueur sans match en
    GW1 disparaîtrait à tort) + les POOL_CHEAP moins chers."""
    pool, seen = [], set()
    for et in (1, 2, 3, 4):
        of_type = [r for r in rows if r["element_type"] == et]
        top = sorted(of_type, key=lambda r: -r["ep4"])[:POOL_TOP]
        cheap = sorted(of_type, key=lambda r: (r["now_cost"], -r["ep4"]))[:POOL_CHEAP]
        for r in top + cheap:
            if r["id"] not in seen:
                seen.add(r["id"])
                pool.append(r)
    return pool


def squad_value(squad, gws):
    """Espérance totale de l'effectif statique : pour chaque GW, meilleur XI
    + bonus exact du brassard."""
    total = 0.0
    for gw in gws:
        gw_rows = [dict(r, ep=r["eps"][gw]) for r in squad]
        xi, _ = squad_rules.pick_xi(gw_rows)
        total += sum(p["ep"] for p in xi) + squad_rules.armband(xi)["ev"]
    return total


def cheapest_squad(pool, budget=BUDGET):
    """Effectif valide le moins cher : point de départ garanti faisable.

    `budget` est un paramètre parce que l'audit d'effectif reconstruit une
    équipe à la VALEUR D'ÉQUIPE du manager, qui n'est pas les 100,0 M£ du
    départ. La valeur par défaut ne change rien aux appels existants."""
    squad, clubs = [], {}
    for et, quota in SQUAD_QUOTA.items():
        cands = sorted((r for r in pool if r["element_type"] == et),
                       key=lambda r: (r["now_cost"], -r["ep4"]))
        n = 0
        for r in cands:
            if clubs.get(r["team"], 0) >= MAX_PER_CLUB:
                continue
            squad.append(r)
            clubs[r["team"]] = clubs.get(r["team"], 0) + 1
            n += 1
            if n == quota:
                break
        if n < quota:
            raise SystemExit(
                f"BLOCAGE : impossible de remplir le quota du poste {et} "
                "sous la limite de 3 par club — données incomplètes ?")
    cost = sum(r["now_cost"] for r in squad)
    if cost > budget:
        raise SystemExit(
            f"BLOCAGE : l'effectif le moins cher coûte {cost / 10:.1f} M£ > "
            f"{budget / 10:.1f} M£ — vérifier les données de prix.")
    return squad


def optimize_squad(pool, gws, budget=BUDGET, start=None):
    """Montée locale par échanges un-pour-un (même poste), en partant de
    l'effectif le moins cher : chaque échange accepté améliore strictement
    la valeur et respecte budget et limite de club. Retourne (squad, value).

    `start` impose un autre point de départ, à ses risques : une montée locale
    ne rend pas le même optimum selon d'où elle part. L'audit d'effectif s'en
    sert pour repartir aussi de l'équipe détenue — sans quoi la reconstruction
    peut se caler sous elle et annoncer un retard négatif, qui ne mesurerait
    alors rien d'autre que la faiblesse de la montée."""
    squad = list(start) if start is not None else cheapest_squad(pool, budget)
    cost = sum(r["now_cost"] for r in squad)
    value = squad_value(squad, gws)
    for _ in range(MAX_SWAP_ROUNDS):
        squad_ids = {r["id"] for r in squad}
        clubs = {}
        for r in squad:
            clubs[r["team"]] = clubs.get(r["team"], 0) + 1
        best = None
        for i, out in enumerate(squad):
            for inn in pool:
                if inn["id"] in squad_ids or inn["element_type"] != out["element_type"]:
                    continue
                if cost - out["now_cost"] + inn["now_cost"] > budget:
                    continue
                if inn["team"] != out["team"] \
                        and clubs.get(inn["team"], 0) + 1 > MAX_PER_CLUB:
                    continue
                v = squad_value(squad[:i] + [inn] + squad[i + 1:], gws)
                if v > value + 1e-9 and (best is None or v > best[0]):
                    best = (v, i, inn)
        if best is None:
            break
        value, i, inn = best
        cost += inn["now_cost"] - squad[i]["now_cost"]
        squad[i] = inn
    return squad, value


def horizon_from(contract):
    return list(contract.horizon)


def select_squad(contract, scenario="central", pool_ids=None, budget=BUDGET):
    """Contrat → (effectif, valeur, vivier). Seule entrée utilisée en amont.

    `pool_ids` fige la présélection (celle du scénario central) pour qu'une
    comparaison entre scénarios porte sur les projections, pas sur un
    changement de vivier."""
    rows = contract.rows_for(scenario)
    if pool_ids is None:
        pool = build_pool(rows)
    else:
        pool = [r for r in rows if r["id"] in set(pool_ids)]
    squad, value = optimize_squad(pool, horizon_from(contract), budget)
    return squad, value, pool


def legality(squad, budget=BUDGET):
    """Faits bruts sur un effectif — consommés par `evaluation`."""
    clubs = {}
    for r in squad:
        clubs[r["team"]] = clubs.get(r["team"], 0) + 1
    quota = {et: sum(1 for r in squad if r["element_type"] == et) for et in (1, 2, 3, 4)}
    cost = sum(r["now_cost"] for r in squad)
    return {
        "cost": cost, "budget": budget, "budget_ok": cost <= budget,
        "quota": quota, "quota_ok": quota == SQUAD_QUOTA,
        "max_per_club": max(clubs.values()) if clubs else 0,
        "club_ok": (max(clubs.values()) if clubs else 0) <= MAX_PER_CLUB,
        "size": len(squad), "size_ok": len(squad) == 15,
    }
