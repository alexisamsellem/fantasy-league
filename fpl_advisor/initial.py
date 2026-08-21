# -*- coding: utf-8 -*-
"""Sélection de l'effectif initial : 15 joueurs sous les contraintes FPL.

Aucune équipe ni ligue requise : seules les données publiques (bootstrap,
fixtures, live éventuel) alimentent le même moteur de projection que le mode
hebdomadaire (`model`) et la même sélection XI/banc/brassard (`team`). Seule
l'optimisation combinatoire de l'effectif est nouvelle.

Objectif : une équipe STATIQUE (aucun transfert) maximisant, sur les
INITIAL_HORIZON_GWS premières GW à venir, la somme par GW du meilleur XI
possible plus le bonus exact du brassard. Optimisation par montée locale
(échanges un-pour-un depuis l'effectif le moins cher) : optimum local, pas
d'optimum global garanti [H].
"""

from . import model, team
from .advise import _player_row

BUDGET = 1000                            # 100,0 M£ en dixièmes — règle FPL
SQUAD_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}   # 2 GB, 5 DEF, 5 MIL, 3 ATT
MAX_PER_CLUB = 3
INITIAL_HORIZON_GWS = 4                  # équipe statique optimisée sur 4 GW [H]
POOL_TOP = 20                            # par poste : meilleurs EP cumulés
POOL_CHEAP = 8                           # par poste : moins chers (banc)
MAX_SWAP_ROUNDS = 80                     # garde-fou de terminaison


def build_pool(parsed, gws, teams_by_id, means):
    """Candidats présélectionnés par poste : les POOL_TOP meilleurs par EP
    cumulée sur l'horizon + les POOL_CHEAP moins chers (joueurs de banc).
    Chaque ligne porte eps (EP par GW) et les probabilités de minutes."""
    elements = parsed["bootstrap"]["elements"]
    rows = []
    for p in elements:
        if p.get("status") == "u":        # parti du championnat
            continue
        minutes = model.minutes_model(p, model.minutes_history(parsed, p["id"]),
                                      elements)
        eps = model.project_horizon(parsed, p, gws, teams_by_id, means)
        rows.append({
            "id": p["id"], "web_name": p.get("web_name", f"#{p['id']}"),
            "element_type": p["element_type"], "team": p["team"],
            "now_cost": p["now_cost"],
            "p_play": minutes["p_play"], "p60": minutes["p60"],
            "p0": minutes["p0"], "minutes_basis": minutes["basis"],
            "eps": eps, "ep4": sum(eps.values()),
        })
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
    (team.pick_xi sur les EP de cette GW) + bonus exact du brassard."""
    total = 0.0
    for gw in gws:
        gw_rows = [dict(r, ep=r["eps"][gw]) for r in squad]
        xi, _ = team.pick_xi(gw_rows)
        total += sum(p["ep"] for p in xi) + team.armband(xi)["ev"]
    return total


def cheapest_squad(pool):
    """Effectif valide le moins cher : point de départ garanti faisable."""
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
    if cost > BUDGET:
        raise SystemExit(
            f"BLOCAGE : l'effectif le moins cher coûte {cost / 10:.1f} M£ > "
            f"{BUDGET / 10:.1f} M£ — vérifier les données de prix.")
    return squad


def optimize_squad(pool, gws):
    """Montée locale par échanges un-pour-un (même poste), en partant de
    l'effectif le moins cher : chaque échange accepté améliore strictement
    la valeur et respecte budget et limite de club. Retourne (squad, value)."""
    squad = cheapest_squad(pool)
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
                if cost - out["now_cost"] + inn["now_cost"] > BUDGET:
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


def build_initial_recommendation(parsed):
    """parsed public (sans équipe ni ligue) → recommandation d'effectif
    initial : 15 joueurs, XI, banc ordonné, capitaine/vice, budget."""
    boot = parsed["bootstrap"]
    elements = {e["id"]: e for e in boot["elements"]}
    teams_by_id, means = model.team_strengths(boot)
    gw = parsed["next_gw"]
    if gw is None:
        raise SystemExit("Aucune GW future dans le calendrier : saison terminée ?")
    gws = list(range(gw, min(gw + INITIAL_HORIZON_GWS, 39)))

    pool = build_pool(parsed, gws, teams_by_id, means)
    squad, value = optimize_squad(pool, gws)
    cost = sum(r["now_cost"] for r in squad)

    # Lignes d'affichage : mêmes colonnes que le mode hebdomadaire (EP de la
    # première GW, EP si 90') + EP par GW de l'horizon.
    by_id = {r["id"]: r for r in squad}
    display = []
    for r in squad:
        row = _player_row(parsed, elements[r["id"]], gw, teams_by_id, means)
        row["eps"] = by_id[r["id"]]["eps"]
        row["ep4"] = by_id[r["id"]]["ep4"]
        display.append(row)

    xi, bench = team.pick_xi(display)
    band = team.armband(xi)
    deadline = next((e.get("deadline_time") for e in parsed["events"]
                     if e["id"] == gw), None)

    return {
        "mode": "initial",
        "gw": gw, "deadline": deadline, "horizon": gws,
        "squad": display, "xi": xi, "bench": bench, "armband": band,
        "budget": BUDGET, "cost": cost, "bank": BUDGET - cost,
        "value4": value, "pool_size": len(pool),
        "teams": {t["id"]: t.get("short_name", str(t["id"]))
                  for t in boot.get("teams", [])},
        "run_dir": parsed.get("run_dir", ""),
        "n_history_gws": len(parsed.get("live", {})),
    }
