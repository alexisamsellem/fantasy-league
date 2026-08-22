# -*- coding: utf-8 -*-
"""Décisions de la semaine, à partir de points DÉJÀ prévus.

Même contrat que les autres modules d'optimisation : on reçoit les lignes du
contrat de projections sous un scénario donné, on applique les règles FPL, on
ne juge jamais si les prévisions sont crédibles — c'est le rôle de
`evaluation`. Aucune donnée brute, aucun snapshot, aucun accès réseau.

Une seule fonction publique, `weekly_decision`, parce que l'évaluation doit
pouvoir rejouer TOUTE la décision de la semaine sous chaque scénario en un
appel : capitaine et arbitrage de transfert changent ensemble, les mesurer
séparément donnerait une stabilité fausse.
"""

from .squad import armband, pick_xi
from .transfers import transfer_scan

MARKET_PER_POSITION = 15   # présélection du marché pour le scan de transfert


def _at_gw(row, gw):
    """Ligne de contrat vue à une GW : `ep` devient l'EP de cette GW seule."""
    return dict(row, ep=row["eps"][gw])


def shortlist(rows, squad_ids, gw, per_position=MARKET_PER_POSITION):
    """Présélection du marché : meilleurs EP de la GW de décision, par poste.

    Une présélection, pas un optimum : le scan d'échange qui suit est un
    voisinage un-pour-un, il n'a pas vocation à explorer tout le marché."""
    ranked = sorted((_at_gw(r, gw) for r in rows if r["id"] not in squad_ids),
                    key=lambda r: -r["ep"])
    out = []
    for et in (1, 2, 3, 4):
        out.extend([r for r in ranked if r["element_type"] == et][:per_position])
    return out


def weekly_decision(rows, squad_ids, bank, gws, per_position=MARKET_PER_POSITION):
    """XI, banc, brassard et arbitrage de transfert pour la GW `gws[0]`.

    `rows` : lignes du contrat sous UN scénario (`ProjectionSet.rows_for`).
    `squad_ids` : les 15 joueurs réellement détenus, dans l'ordre d'entrée.

    `missing_ids` remonte les joueurs de l'effectif absents du contrat — radiés
    du championnat, ou identifiants inconnus. Ils ne sont pas projetables ; le
    fait est retourné tel quel, jamais absorbé en silence.
    """
    gw = gws[0]
    by_id = {r["id"]: r for r in rows}
    squad_ids = list(squad_ids)
    missing = [pid for pid in squad_ids if pid not in by_id]
    squad = [_at_gw(by_id[pid], gw) for pid in squad_ids if pid in by_id]

    xi, bench = pick_xi(squad)
    band = armband(xi)

    market = shortlist(rows, set(squad_ids), gw, per_position)
    horizon_eps = {r["id"]: {g: by_id[r["id"]]["eps"][g] for g in gws}
                   for r in squad + market}
    transfer = transfer_scan(squad, market, horizon_eps, bank)

    top = transfer["candidates"][0] if transfer["candidates"] else None
    return {
        "gw": gw, "horizon": list(gws),
        "squad": squad, "xi": xi, "bench": bench, "armband": band,
        "transfer": transfer, "horizon_eps": horizon_eps,
        "market_size": len(market), "missing_ids": missing,
        # Empreinte comparable d'un scénario à l'autre (voir evaluation).
        "captain_id": band["captain"]["id"],
        "xi_ids": {p["id"] for p in xi},
        "decision": transfer["decision"],
        # Le couple n'est comparable entre scénarios que s'il est RECOMMANDÉ :
        # sous « conserver », deux meilleurs candidats sous le seuil qui
        # diffèrent décrivent la même action — ne rien faire.
        "swap": ((top["out"]["id"], top["in"]["id"])
                 if top and transfer["decision"] == "transférer" else None),
    }
