# -*- coding: utf-8 -*-
"""Sélection du XI, ordre du banc et brassard, à partir de points déjà prévus.

Ce module ne sait pas d'où viennent les points : il reçoit des lignes portant
un `ep`, un `p0` et un poste, et il applique les règles FPL. Il ne juge jamais
si les prévisions sont crédibles — c'est le rôle de `evaluation`.
"""

# Formations valides : 1 GB + DEF 3..5, MIL 2..5, ATT 1..3, total 10 champs
FORMATIONS = [(d, m, f) for d in range(3, 6) for m in range(2, 6)
              for f in range(1, 4) if d + m + f == 10]


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
    if best is None:
        raise ValueError(
            "aucune formation FPL légale avec cet effectif : "
            + ", ".join(f"{n} au poste {t}" for t, n in
                        sorted((t, len(v)) for t, v in by_pos.items())))
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
