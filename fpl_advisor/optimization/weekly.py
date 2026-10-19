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

from . import milp
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


def _transfer_milp(rows, by_id, squad, squad_ids, bank, gws, free_transfers):
    """Arbitrage par le programme exact, rendu sous la forme du scan.

    Le plan optimal est comparé au meilleur plan qui n'agit PAS à la GW de
    décision. `delta3` est leur écart sur le XI (hits déduits, banque non
    comptée) : c'est le gain d'agir maintenant, et il se lit contre le même
    seuil que le scan — la valeur d'un gratuit gardé en banque. Sous
    « conserver », le meilleur échange immédiat est calculé quand même, pour
    dire de combien il manque."""
    gw = gws[0]
    kw = {"free_transfers": free_transfers}
    plan = milp.plan_transferts(rows, squad_ids, bank, gws, **kw)
    impose = False
    if plan["achats"][gw]:
        try:
            ref = milp.plan_transferts(rows, squad_ids, bank, gws,
                                       sans_transfert_a=gw, **kw)
        except ValueError:          # effectif illégal sans transfert
            ref, impose = plan, True
        montre = plan
    else:
        ref = plan
        try:
            montre = milp.plan_transferts(rows, squad_ids, bank, gws,
                                          au_moins_un_a=gw, **kw)
        except ValueError:
            montre = None
    gain = (montre["valeur"] - ref["valeur"]) if montre else 0.0
    cands = []
    if montre:
        ventes = sum(by_id[o]["now_cost"] for o in montre["ventes"][gw] if o in by_id)
        achats = sum(by_id[i]["now_cost"] for i in montre["achats"][gw])
        for o, i in milp.echanges(montre, by_id, gw):
            out = next((p for p in squad if p["id"] == o), None) or dict(
                by_id.get(o, {"id": o, "web_name": f"#{o}", "element_type": 0,
                              "now_cost": 0, "team": 0}), ep=0.0)
            cands.append({"out": out, "in": dict(by_id[i], ep=by_id[i]["eps"][gw]),
                          "delta3": gain, "delta3_brut": gain,
                          "cost_after": bank + ventes - achats})
    resume = {g: {"achats": plan["achats"][g], "ventes": plan["ventes"][g],
                  "hits": plan["hits"][g], "gratuits": plan["ft"][g]} for g in gws}
    return {"decision": "transférer" if plan["achats"][gw] else "conserver",
            "threshold": milp.FT_VALUE, "candidates": cands,
            "horizon": len(gws), "xi_based": True, "optimiseur": "milp",
            "impose": impose,
            "hits": (montre or plan)["hits"][gw], "gratuits": plan["ft"][gw],
            "gratuits_fin": plan["ft_fin"], "plan": resume,
            "valeur_plan": plan["valeur_banque"]}


def executes(transfer):
    """Les échanges À FAIRE. Pour le scan, `candidates` liste des
    alternatives (seule la première est jouée) ; pour le programme exact,
    c'est l'ensemble des échanges de la GW de décision."""
    cands = transfer.get("candidates") or []
    if transfer.get("decision") != "transférer":
        return []
    return cands if transfer.get("optimiseur") == "milp" else cands[:1]


def libelle(transfer):
    """« A → B + C → D (1 hit, −4) » — tous les échanges de la GW de décision."""
    cands = executes(transfer)
    if not cands:
        return "aucun"
    txt = " + ".join(f"{c['out']['web_name']} → {c['in']['web_name']}" for c in cands)
    h = transfer.get("hits") or 0
    return txt + (f" ({h} hit{'s' if h > 1 else ''}, −{milp.HIT * h})" if h else "")


def weekly_decision(rows, squad_ids, bank, gws, per_position=MARKET_PER_POSITION,
                    optimiseur=None, free_transfers=1):
    """XI, banc, brassard et arbitrage de transfert pour la GW `gws[0]`.

    `optimiseur` : « milp » (programme exact, défaut quand PuLP + HiGHS sont
    installés) ou « scan » (échange un-pour-un historique, conservé comme
    témoin et comme repli). `free_transfers` : gratuits disponibles à la GW
    de décision — le programme seul sait en tirer parti.

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
    if optimiseur is None:
        optimiseur = "milp" if milp.disponible() else "scan"
    if optimiseur == "milp":
        transfer = _transfer_milp(rows, by_id, squad, squad_ids, bank, gws,
                                  free_transfers)
        for c in transfer["candidates"]:
            horizon_eps.setdefault(c["in"]["id"],
                                   {g: by_id[c["in"]["id"]]["eps"][g] for g in gws})
    else:
        transfer = dict(transfer_scan(squad, market, horizon_eps, bank),
                        optimiseur="scan")

    top = transfer["candidates"][0] if transfer["candidates"] else None

    # Le XI d'AVANT n'est pas celui d'APRÈS. Un entrant meilleur que le sortant
    # entre presque toujours dans le onze, et il en déplace un autre — parfois
    # en changeant la formation. Afficher le seul XI d'avant à côté d'un
    # transfert recommandé donne une feuille de match fausse, et laisse le
    # joueur vendu sur le banc affiché. Le second XI est donc calculé ici, là
    # où l'échange est décidé.
    apres = None
    if top and transfer["decision"] == "transférer":
        faits = executes(transfer)
        remplace = {c["out"]["id"]: c["in"] for c in faits}
        squad_apres = [remplace.get(p["id"], p) for p in squad]
        # Joueur détenu absent du contrat : sa place reprise par un achat.
        deja = {p["id"] for p in squad_apres}
        squad_apres += [c["in"] for c in faits
                        if c["in"]["id"] not in deja and c["out"]["id"] not in
                        {p["id"] for p in squad}]
        xi_a, bench_a = pick_xi(squad_apres)
        band_a = armband(xi_a)
        apres = {"squad": squad_apres, "xi": xi_a, "bench": bench_a,
                 "armband": band_a, "out": top["out"], "in": top["in"],
                 "echanges": [(c["out"], c["in"]) for c in faits],
                 "captain_change": band_a["captain"]["id"] != band["captain"]["id"],
                 "xi_in": [p["id"] for p in xi_a
                           if p["id"] not in {x["id"] for x in xi}],
                 "xi_out": [p["id"] for p in xi
                            if p["id"] not in {x["id"] for x in xi_a}]}

    return {
        "gw": gw, "horizon": list(gws),
        "squad": squad, "xi": xi, "bench": bench, "armband": band,
        "apres_transfert": apres,
        "transfer": transfer, "horizon_eps": horizon_eps,
        "market_size": len(market), "missing_ids": missing,
        # Empreinte comparable d'un scénario à l'autre (voir evaluation).
        "captain_id": band["captain"]["id"],
        "xi_ids": {p["id"] for p in xi},
        "decision": transfer["decision"],
        # Le couple n'est comparable entre scénarios que s'il est RECOMMANDÉ :
        # sous « conserver », deux meilleurs candidats sous le seuil qui
        # diffèrent décrivent la même action — ne rien faire.
        "swap": (None if not executes(transfer)
                 else (top["out"]["id"], top["in"]["id"]) if len(executes(transfer)) == 1
                 else tuple(sorted((c["out"]["id"], c["in"]["id"])
                                   for c in executes(transfer)))),
    }
