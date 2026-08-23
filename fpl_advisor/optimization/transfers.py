# -*- coding: utf-8 -*-
"""Transférer ou conserver, à partir de points déjà prévus.

Le gain d'un transfert se mesure sur le MEILLEUR XI, pas sur les points du
joueur échangé. La différence n'est pas cosmétique : sortir un remplaçant qui
ne joue pas ne rapporte pas ses points « manquants », puisqu'il n'en marquait
aucun pour l'équipe. Un entrant ne rapporte que ce qu'il ajoute au XI — c'est
à dire l'écart avec le titulaire qu'il déplace, pas avec le joueur vendu.

Comparer les points individuels surestime donc tout échange dont le sortant
est sur le banc, d'autant plus que ce sortant est peu probable de jouer.
"""

from .squad import pick_xi

TRANSFER_THRESHOLD = 2.0   # pts d'espérance sur 3 GW pour recommander un
                           # transfert plutôt que la conservation [H, à estimer]
HORIZON_GWS = 3


def _horizon(horizon_eps):
    return sorted({g for v in horizon_eps.values() for g in v})


def best_xi_total(rows, horizon_eps, gws):
    """Somme, sur l'horizon, du meilleur XI de chaque GW.

    C'est l'objectif réel : ce que l'effectif rapporte, brassard exclu. Rend
    None si l'effectif ne permet aucune formation légale — le cas ne se produit
    pas sur un effectif FPL valide, mais l'appelant doit pouvoir le distinguer
    d'un gain nul."""
    total = 0.0
    for g in gws:
        scored = [dict(r, ep=horizon_eps.get(r["id"], {}).get(g, 0.0)) for r in rows]
        try:
            xi, _ = pick_xi(scored)
        except ValueError:
            return None
        total += sum(x["ep"] for x in xi)
    return total


def transfer_scan(squad, market, horizon_eps, bank, max_candidates=3):
    """Compare 'transférer' vs 'conserver' sur l'horizon des projections.

    squad/market : dicts joueurs avec id, element_type, team, now_cost, web_name.
    horizon_eps : id -> {gw: ep} pour squad ∪ marché présélectionné.
    bank : budget en dixièmes de M£. Prix de vente approximé par now_cost
    (le vrai prix de vente peut différer : vérifier dans l'app avant d'agir).

    Chaque candidat porte deux chiffres :
      delta3      gain sur le meilleur XI — c'est lui qui décide ;
      delta3_brut différence des points individuels, conservée pour montrer
                  l'écart quand le sortant ne joue pas.
    """
    squad_ids = {p["id"] for p in squad}
    gws = _horizon(horizon_eps)
    clubs = {}
    for p in squad:
        clubs[p["team"]] = clubs.get(p["team"], 0) + 1

    def ep3(pid):
        return sum(horizon_eps.get(pid, {}).values())

    base = best_xi_total(squad, horizon_eps, gws)
    xi_based = base is not None

    candidates = []
    for out in squad:
        sell = out["now_cost"]
        reste = [p for p in squad if p["id"] != out["id"]]
        for inn in market:
            if inn["id"] in squad_ids or inn["element_type"] != out["element_type"]:
                continue
            if inn["now_cost"] > sell + bank:
                continue
            same_club_ok = clubs.get(inn["team"], 0) + (0 if inn["team"] == out["team"] else 1) <= 3
            if not same_club_ok:
                continue
            brut = ep3(inn["id"]) - ep3(out["id"])
            if brut <= 0:            # un entrant plus faible ne peut rien ajouter
                continue
            if xi_based:
                apres = best_xi_total(reste + [inn], horizon_eps, gws)
                delta = 0.0 if apres is None else apres - base
            else:
                delta = brut
            if delta > 0:
                candidates.append({"out": out, "in": inn, "delta3": delta,
                                   "delta3_brut": brut,
                                   "cost_after": bank + sell - inn["now_cost"]})
    candidates.sort(key=lambda c: (-c["delta3"], -c["delta3_brut"]))
    top = candidates[:max_candidates]
    decision = "transférer" if top and top[0]["delta3"] > TRANSFER_THRESHOLD else "conserver"
    return {"decision": decision, "threshold": TRANSFER_THRESHOLD,
            "candidates": top, "horizon": len(gws), "xi_based": xi_based}
