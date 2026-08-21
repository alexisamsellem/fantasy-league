# -*- coding: utf-8 -*-
"""Sélection de l'effectif initial : 15 joueurs sous les contraintes FPL.

Aucune équipe ni ligue requise : seules les données publiques alimentent le
même moteur de projection que le mode hebdomadaire (`model`) et la même
sélection XI/banc/brassard (`team`). Seule l'optimisation combinatoire de
l'effectif est propre à ce mode.

L'optimiseur est délibérément simple (montée locale par échanges un-pour-un) :
un optimum local sur de bonnes projections vaut mieux qu'un optimum global sur
de mauvaises. L'effort porte sur la couche de projection (`priors`, `model`) et
sur la représentation de l'incertitude (trois scénarios + stabilité du top 15),
pas sur la recherche.
"""

from . import model, priors, team
from .advise import _player_row

BUDGET = 1000                            # 100,0 M£ en dixièmes — règle FPL
SQUAD_QUOTA = {1: 2, 2: 5, 3: 5, 4: 3}   # 2 GB, 5 DEF, 5 MIL, 3 ATT
MAX_PER_CLUB = 3
INITIAL_HORIZON_GWS = 4                  # équipe statique optimisée sur 4 GW [H]
POOL_TOP = 20                            # par poste : meilleurs EP cumulés
POOL_CHEAP = 8                           # par poste : moins chers (banc)
MAX_SWAP_ROUNDS = 80                     # garde-fou de terminaison
STABILITY_MIN_OVERLAP = 12               # < 12/15 communs → effectif dit instable


def _rows(parsed, gws, scenario):
    """Une ligne par joueur sélectionnable, avec EP par GW sous ce scénario."""
    elements = parsed["bootstrap"]["elements"]
    rows = []
    for p in elements:
        if p.get("status") == "u":        # parti du championnat
            continue
        hist, _ = model.appearance_history(parsed, p["id"])
        minutes = model.minutes_model(p, hist, parsed=parsed, scenario=scenario)
        eps = model.project_horizon(parsed, p, gws, scenario=scenario)
        rows.append({
            "id": p["id"], "web_name": p.get("web_name", f"#{p['id']}"),
            "element_type": p["element_type"], "team": p["team"],
            "now_cost": p["now_cost"],
            "p_play": minutes["p_play"], "p60": minutes["p60"],
            "p0": minutes["p0"], "minutes_basis": minutes["basis"],
            "minutes_confidence": minutes["confidence"],
            "eps": eps, "ep4": sum(eps.values()),
        })
    return rows


def build_pool(parsed, gws, teams_by_id=None, means=None, scenario=None):
    """Candidats présélectionnés par poste : les POOL_TOP meilleurs par EP
    CUMULÉE SUR L'HORIZON (jamais sur la seule première GW, sinon un joueur
    sans match en GW1 disparaîtrait à tort) + les POOL_CHEAP moins chers."""
    scenario = scenario or priors.params("central")
    rows = _rows(parsed, gws, scenario)
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


def rescore_pool(parsed, pool, gws, scenario):
    """Re-projette le MÊME vivier sous un autre scénario.

    Le vivier est figé (celui du scénario central) pour que la comparaison
    porte sur les projections, pas sur un changement de présélection."""
    elements = {e["id"]: e for e in parsed["bootstrap"]["elements"]}
    out = []
    for r in pool:
        eps = model.project_horizon(parsed, elements[r["id"]], gws, scenario=scenario)
        out.append(dict(r, eps=eps, ep4=sum(eps.values())))
    return out


def scenario_analysis(parsed, pool, gws, central_ids):
    """Optimise sous chaque scénario et mesure la stabilité du top 15.

    Retourne (lignes de scénario, recouvrement minimal). Une équipe qui change
    beaucoup d'un scénario à l'autre est une équipe instable : le rapport doit
    le dire, pas le masquer."""
    rows, min_overlap = [], 15
    for name in priors.SCENARIO_ORDER:
        sc = priors.params(name)
        scored = pool if name == "central" else rescore_pool(parsed, pool, gws, sc)
        squad, value = optimize_squad(scored, gws)
        ids = {r["id"] for r in squad}
        overlap = len(ids & central_ids)
        min_overlap = min(min_overlap, overlap)
        # Valeur de l'effectif CENTRAL évalué sous ce scénario (ce que l'on
        # gagnerait/perdrait en gardant l'équipe recommandée si le monde
        # ressemble à ce scénario).
        central_rows = [r for r in scored if r["id"] in central_ids]
        rows.append({
            "name": name, "label": sc["label"], "note": sc["note"],
            "own_value": value, "overlap": overlap,
            "central_value": squad_value(central_rows, gws) if len(central_rows) == 15 else None,
            "squad_ids": ids,
        })
    return rows, min_overlap


def build_initial_recommendation(parsed):
    """parsed public (sans équipe ni ligue) → recommandation d'effectif
    initial : 15 joueurs, XI, banc ordonné, capitaine/vice, budget, scénarios,
    stabilité et provenance des données."""
    boot = parsed["bootstrap"]
    elements = {e["id"]: e for e in boot["elements"]}
    gw = parsed["next_gw"]
    if gw is None:
        raise SystemExit("Aucune GW future dans le calendrier : saison terminée ?")
    gws = list(range(gw, min(gw + INITIAL_HORIZON_GWS, 39)))

    availability = priors.availability_report(parsed)
    blocking = priors.missing_required(availability)
    if blocking:
        raise SystemExit(
            "BLOCAGE DONNÉES : source obligatoire absente — "
            + " ; ".join(f"{b['key']} ({b['source']})" for b in blocking))
    confidence, confidence_why = priors.confidence_level(availability)

    central = priors.params("central")
    pool = build_pool(parsed, gws, scenario=central)
    squad, value = optimize_squad(pool, gws)
    cost = sum(r["now_cost"] for r in squad)
    central_ids = {r["id"] for r in squad}

    scenarios, min_overlap = scenario_analysis(parsed, pool, gws, central_ids)
    stable = min_overlap >= STABILITY_MIN_OVERLAP

    # Lignes d'affichage : mêmes colonnes que le mode hebdomadaire.
    by_id = {r["id"]: r for r in squad}
    display = []
    for r in squad:
        row = _player_row(parsed, elements[r["id"]], gw)
        row["eps"] = by_id[r["id"]]["eps"]
        row["ep4"] = by_id[r["id"]]["ep4"]
        row["minutes_confidence"] = by_id[r["id"]]["minutes_confidence"]
        display.append(row)

    xi, bench = team.pick_xi(display)
    band = team.armband(xi)
    deadline = next((e.get("deadline_time") for e in parsed["events"]
                     if e["id"] == gw), None)
    factors = model.team_factors(parsed)
    factor_source = next(iter(factors.values()), {}).get("source", "inconnu")

    return {
        "mode": "initial",
        "gw": gw, "deadline": deadline, "horizon": gws,
        "squad": display, "xi": xi, "bench": bench, "armband": band,
        "budget": BUDGET, "cost": cost, "bank": BUDGET - cost,
        "value4": value, "pool_size": len(pool),
        "scenarios": scenarios, "min_overlap": min_overlap, "stable": stable,
        "stability_threshold": STABILITY_MIN_OVERLAP,
        "availability": availability, "confidence": confidence,
        "confidence_why": confidence_why, "team_factor_source": factor_source,
        "teams": {t["id"]: t.get("short_name", str(t["id"]))
                  for t in boot.get("teams", [])},
        "run_dir": parsed.get("run_dir", ""),
        "synthetic": bool(parsed.get("synthetic")),
        "n_history_gws": len(parsed.get("live", {})),
    }
