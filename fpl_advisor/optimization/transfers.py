# -*- coding: utf-8 -*-
"""Transférer ou conserver, à partir de points déjà prévus."""

TRANSFER_THRESHOLD = 2.0   # pts d'espérance sur 3 GW pour recommander un
                           # transfert plutôt que la conservation [H, à estimer]
HORIZON_GWS = 3


def transfer_scan(squad, market, horizon_eps, bank, max_candidates=3):
    """Compare 'transférer' vs 'conserver' sur HORIZON_GWS.

    squad/market : dicts joueurs avec id, element_type, team, now_cost, web_name.
    horizon_eps : id -> {gw: ep} pour squad ∪ marché présélectionné.
    bank : budget en dixièmes de M£. Prix de vente approximé par now_cost
    (le vrai prix de vente peut différer : vérifier dans l'app avant d'agir).
    """
    squad_ids = {p["id"] for p in squad}
    clubs = {}
    for p in squad:
        clubs[p["team"]] = clubs.get(p["team"], 0) + 1

    def ep3(pid):
        return sum(horizon_eps.get(pid, {}).values())

    candidates = []
    for out in squad:
        sell = out["now_cost"]
        for inn in market:
            if inn["id"] in squad_ids or inn["element_type"] != out["element_type"]:
                continue
            if inn["now_cost"] > sell + bank:
                continue
            same_club_ok = clubs.get(inn["team"], 0) + (0 if inn["team"] == out["team"] else 1) <= 3
            if not same_club_ok:
                continue
            delta = ep3(inn["id"]) - ep3(out["id"])
            if delta > 0:
                candidates.append({"out": out, "in": inn, "delta3": delta,
                                   "cost_after": bank + sell - inn["now_cost"]})
    candidates.sort(key=lambda c: -c["delta3"])
    top = candidates[:max_candidates]
    decision = "transférer" if top and top[0]["delta3"] > TRANSFER_THRESHOLD else "conserver"
    return {"decision": decision, "threshold": TRANSFER_THRESHOLD,
            "candidates": top, "horizon": HORIZON_GWS}
