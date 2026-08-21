# -*- coding: utf-8 -*-
"""Sélection du XI, ordre du banc, brassard exact, transférer vs conserver."""

from itertools import combinations

# Formations valides : 1 GB + DEF 3..5, MIL 2..5, ATT 1..3, total 10 champs
FORMATIONS = [(d, m, f) for d in range(3, 6) for m in range(2, 6)
              for f in range(1, 4) if d + m + f == 10]

TRANSFER_THRESHOLD = 2.0   # pts d'espérance sur 3 GW pour recommander un
                           # transfert plutôt que la conservation [H, à estimer]
HORIZON_GWS = 3


def pick_xi(squad):
    """squad : liste de dicts {id, element_type, ep, p_play, ...}.
    Retourne (xi, banc) — banc = [GB remplaçant, puis champs par priorité]."""
    by_pos = {t: sorted((p for p in squad if p["element_type"] == t),
                        key=lambda p: -p["ep"]) for t in (1, 2, 3, 4)}
    best, best_score = None, -1.0
    for d, m, f in FORMATIONS:
        if len(by_pos[2]) < d or len(by_pos[3]) < m or len(by_pos[4]) < f:
            continue
        xi = by_pos[1][:1] + by_pos[2][:d] + by_pos[3][:m] + by_pos[4][:f]
        score = sum(p["ep"] for p in xi)
        if score > best_score:
            best, best_score = xi, score
    xi_ids = {p["id"] for p in best}
    bench_gk = [p for p in by_pos[1][1:] if p["id"] not in xi_ids]
    bench_out = sorted((p for p in squad
                        if p["id"] not in xi_ids and p["element_type"] != 1),
                       key=lambda p: -(p["p_play"] * p["ep"]))
    return best, bench_gk + bench_out


def armband(xi):
    """Couple (capitaine, vice) maximisant le bonus additionnel du brassard :
    E = EP_c + P(M_c = 0) × EP_v, joueurs supposés indépendants [H].
    Règle FPL exacte : le vice n'est doublé que si le capitaine joue 0 minute."""
    ranked = sorted(xi, key=lambda p: -p["ep"])
    best = None
    for c in ranked[:5]:
        for v in ranked[:6]:
            if v["id"] == c["id"]:
                continue
            ev = c["ep"] + c["p0"] * v["ep"]
            if best is None or ev > best["ev"]:
                best = {"captain": c, "vice": v, "ev": ev}
    alts = []
    for c in ranked[:4]:
        v = next(p for p in ranked if p["id"] != c["id"])
        alts.append({"captain": c, "vice": v, "ev": c["ep"] + c["p0"] * v["ep"]})
    best["alternatives"] = alts
    return best


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
