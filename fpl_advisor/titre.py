# -*- coding: utf-8 -*-
"""P(finir 1er) de chaque mini-ligue : le vrai objectif, ligue par ligue.

Maximiser les points espérés n'est pas gagner une ligue. Un leader avec 30
points d'avance gagne en copiant le peloton ; un chasseur à 40 points ne gagne
qu'en prenant des paris que les autres ne prennent pas. L'espérance ne voit
pas la différence. La probabilité de finir premier, si.

La chaîne, dans l'ordre :

  1. tirages JOINTS des points de chaque joueur sur l'horizon du contrat
     (`ProjectionSet.simulate`) : les buts d'un match sont partagés, donc deux
     managers qui possèdent le même défenseur gagnent ou perdent ensemble ;
  2. les rivaux sont figés sur leurs derniers picks publics (XI, capitaine) :
     on ne connaît pas leurs transferts à venir, on ne les invente pas ;
  3. au-delà de l'horizon, un modèle résiduel par manager, appris sur les
     journées jouées de la ligue : écart moyen au score moyen de la journée
     (rétréci, parce que cinq journées disent peu du talent) + bruit ;
  4. pour chaque option de la semaine (transfert × capitaine), la même
     graine pour tout le monde — nombres aléatoires communs — et on compte,
     tirage par tirage, qui finit premier.

Chaque ligue est calculée séparément. Elles ne sont jamais moyennées : une
option qui aide ici peut nuire là, et c'est précisément l'information.

Ce module ne prévoit rien : il consomme le contrat et des picks publics.
"""

import math
import random

from .optimization.squad import pick_xi
from .optimization.transfers import transfer_scan
from .optimization.weekly import shortlist

N_TIRAGES = 10000
VICTOIRES_MIN = 50      # sous ce nombre de titres simulés, ΔP n'est pas résolu
GRAINE = 20261019
DERNIERE_GW = 38
N_TRANSFERTS = 6        # meilleurs échanges du scan, plus « conserver »
N_CAPITAINES = 3        # meilleurs EP du XI de la GW de décision


# ------------------------------------------------------ modèle résiduel ----

def _points_par_gw(history, gws):
    """{gw: points nets des hits} sur les journées demandées, ou None."""
    cur = {h["event"]: h for h in (history or {}).get("current", [])}
    if not all(g in cur for g in gws):
        return None
    return {g: (cur[g].get("points") or 0) - (cur[g].get("event_transfers_cost") or 0)
            for g in gws}


def modele_residuel(histories, gws):
    """x[m, g] = b_g + a_m + e : b_g moyenne de la ligue à la journée g, a_m
    l'écart moyen du manager, e le bruit. Rend {a (rétréci), sigma, n_gw,
    k_retrecissement}.

    Le rétrécissement est empirique-bayésien : la part de la variance des a_m
    qui dépasse ce que le bruit seul produirait (σ²/G) est jugée réelle, le
    reste est ramené à zéro. Avec peu de journées, k est petit et tout le
    monde a presque le même talent — c'est la lecture prudente."""
    x = {m: p for m, h in histories.items()
         if (p := _points_par_gw(h, gws)) is not None}
    if len(x) < 2 or not gws:
        return {"a": {m: 0.0 for m in histories}, "sigma": 15.0, "n_gw": 0,
                "k": 0.0, "source": "défaut [H] : historique insuffisant"}
    b = {g: sum(x[m][g] for m in x) / len(x) for g in gws}
    a = {m: sum(x[m][g] - b[g] for g in gws) / len(gws) for m in x}
    res = [x[m][g] - b[g] - a[m] for m in x for g in gws]
    ddl = max(1, (len(x) - 1) * (len(gws) - 1))
    sigma = math.sqrt(sum(r * r for r in res) / ddl)
    var_a = sum(v * v for v in a.values()) / max(1, len(a) - 1)
    var_vrai = max(0.0, var_a - sigma ** 2 / len(gws))
    k = var_vrai / (var_vrai + sigma ** 2 / len(gws)) if var_vrai > 0 else 0.0
    out = {m: k * a.get(m, 0.0) for m in histories}
    return {"a": out, "sigma": sigma, "n_gw": len(gws), "k": k,
            "source": f"{len(x)} managers × {len(gws)} journées jouées"}


def controle_residuel(histories, gws):
    """Le modèle prédit-il la dispersion de la journée suivante ?

    Pour chaque journée k ≥ 3, modèle ajusté sur les journées < k, écart
    standardisé z = (x − b_k − a_m) / σ. Un modèle bien calibré donne un écart
    type de z proche de 1 ; plus grand, il sous-estime le bruit et rend les
    probabilités de titre trop tranchées."""
    zs = []
    for i in range(2, len(gws)):
        mod = modele_residuel(histories, gws[:i])
        g = gws[i]
        pts = {m: p[g] for m, h in histories.items()
               if (p := _points_par_gw(h, [g])) is not None}
        if len(pts) < 2:
            continue
        bg = sum(pts.values()) / len(pts)
        zs += [(v - bg - mod["a"].get(m, 0.0)) / mod["sigma"] for m, v in pts.items()]
    if len(zs) < 2:
        return None
    mz = sum(zs) / len(zs)
    return {"n": len(zs), "sd_z": math.sqrt(sum((z - mz) ** 2 for z in zs) / (len(zs) - 1))}


# --------------------------------------------------------------- options ----

def _at(row, gw):
    return dict(row, ep=row["eps"].get(gw, 0.0))


def options_semaine(contract, squad_ids, bank, n_transferts=N_TRANSFERTS,
                    n_capitaines=N_CAPITAINES):
    """Options de la semaine : conserver ou l'un des meilleurs échanges du
    scan, croisés avec les meilleurs capitaines du XI correspondant.

    Chaque option porte son plan de jeu sur l'horizon (XI et capitaine par
    GW) et sa valeur en points espérés — celle que le moteur classe déjà."""
    rows = contract.rows_for("central")
    by_id = {r["id"]: r for r in rows}
    gws = list(contract.horizon)
    gw0 = gws[0]
    ids = [p for p in squad_ids if p in by_id]
    squad = [_at(by_id[p], gw0) for p in ids]
    market = shortlist(rows, set(squad_ids), gw0)
    horizon_eps = {r["id"]: {g: by_id[r["id"]]["eps"][g] for g in gws}
                   for r in squad + market}
    scan = transfer_scan(squad, market, horizon_eps, bank, max_candidates=n_transferts)
    echanges = [None] + [(c["out"]["id"], c["in"]["id"]) for c in scan["candidates"]]

    options = []
    for ech in echanges:
        apres = [ech[1] if (ech and p == ech[0]) else p for p in ids]
        plan, ep_base = {}, 0.0
        for g in gws:
            xi, _ = pick_xi([_at(by_id[p], g) for p in apres])
            cap = max(xi, key=lambda r: r["ep"])
            plan[g] = {"xi": [r["id"] for r in xi], "cap": cap["id"]}
            ep_base += sum(r["ep"] for r in xi) + (cap["ep"] if g != gw0 else 0.0)
        xi0 = sorted((_at(by_id[p], gw0) for p in plan[gw0]["xi"]), key=lambda r: -r["ep"])
        for cap in xi0[:n_capitaines]:
            pl = {g: dict(v) for g, v in plan.items()}
            pl[gw0]["cap"] = cap["id"]
            nom = (f"{by_id[ech[0]]['web_name']} → {by_id[ech[1]]['web_name']}"
                   if ech else "conserver")
            options.append({"echange": ech, "label": nom,
                            "capitaine": cap["id"], "capitaine_nom": cap["web_name"],
                            "plan": pl, "ep": ep_base + cap["ep"], "cout": 0})
    return options


# ------------------------------------------------------------ simulation ----

def _rival_plan(picks):
    """Derniers picks publics → (XI, capitaine). Triple capitaine ramené à
    double, banc ignoré même sous Bench Boost : un chip ne se rejoue pas."""
    pk = (picks or {}).get("picks") or []
    pos = lambda i, p: p.get("position") or i + 1     # ordre des picks à défaut
    xi = [p["element"] for i, p in enumerate(pk) if pos(i, p) <= 11]
    cap = next((p["element"] for p in pk if p.get("is_captain")), None)
    return xi, cap


def _points_plan(tir, plan_par_gw, n):
    out = [0.0] * n
    for g, (xi, cap) in plan_par_gw.items():
        t = tir[g]
        for pid in xi:
            s = t.get(pid)
            if s is None:
                continue
            mult = 2 if pid == cap else 1
            for k in range(n):
                out[k] += mult * s[k]
    return out


def p_premier(contract, ligues, team_id, options, histories, gws_jouees,
              n=N_TIRAGES, seed=GRAINE):
    """P(finir 1er) de chaque option, dans chaque ligue, séparément.

    `ligues` : [{id, name, standings: [{entry, total, …}], rivals: {rid:
    {picks}}}]. `histories` : {entry: history} — y compris le mien.
    Rend une vue par ligue : options triées par ΔP(1er) par rapport à
    « conserver + meilleur capitaine EP », et le rang EP de chacune."""
    gws = list(contract.horizon)
    reste = max(0, DERNIERE_GW - gws[-1])
    besoin = {p for o in options for v in o["plan"].values() for p in v["xi"]}
    for l in ligues:
        for r in l.get("rivals", {}).values():
            besoin.update(_rival_plan(r.get("picks"))[0])
    tir = {g: contract.simulate(g, n=n, seed=seed, ids=besoin) for g in gws}

    pts_options = [_points_plan(tir, {g: (o["plan"][g]["xi"], o["plan"][g]["cap"])
                                      for g in gws}, n) for o in options]
    ref = max(range(len(options)),
              key=lambda i: (options[i]["echange"] is None, options[i]["ep"]))

    vues = []
    for l in ligues:
        managers = [r for r in l.get("standings", []) if r.get("entry")]
        me = next((r for r in managers if r["entry"] == team_id), None)
        if me is None:
            vues.append({"id": l.get("id"), "name": l.get("name"), "erreur":
                         "mon équipe est absente de ce classement"})
            continue
        hist_ligue = {m["entry"]: histories.get(m["entry"]) for m in managers}
        mod = modele_residuel(hist_ligue, gws_jouees)
        ctl = controle_residuel(hist_ligue, gws_jouees)
        sig = mod["sigma"] * math.sqrt(reste)

        def futur(entry):
            rng = random.Random(seed * 7919 + entry)
            a = mod["a"].get(entry, 0.0) * reste
            return [a + sig * rng.gauss(0, 1) for _ in range(n)]

        rivaux = []
        for m in managers:
            if m["entry"] == team_id:
                continue
            xi, cap = _rival_plan((l["rivals"].get(m["entry"]) or {}).get("picks"))
            pts = _points_plan(tir, {g: (xi, cap) for g in gws}, n)
            fut = futur(m["entry"])
            rivaux.append([(m.get("total") or 0) + pts[k] + fut[k] for k in range(n)])
        meilleur = [max(r[k] for r in rivaux) if rivaux else -math.inf for k in range(n)]
        nb_ex = [sum(1 for r in rivaux if r[k] == meilleur[k]) for k in range(n)]
        mon = futur(team_id)
        base = (me.get("total") or 0)

        gains = []
        for o, pts in zip(options, pts_options):
            g = []
            for k in range(n):
                s = base + pts[k] + mon[k] - o["cout"]
                g.append(1.0 if s > meilleur[k] else
                         (1.0 / (nb_ex[k] + 1) if s == meilleur[k] else 0.0))
            gains.append(g)
        p_ref = sum(gains[ref]) / n
        lignes = []
        rang_ep = {i: r for r, i in enumerate(
            sorted(range(len(options)), key=lambda i: -options[i]["ep"]), 1)}
        for i, (o, g) in enumerate(zip(options, gains)):
            d = [x - y for x, y in zip(g, gains[ref])]
            md = sum(d) / n
            se = math.sqrt(sum((x - md) ** 2 for x in d) / (n * (n - 1))) if n > 1 else 0.0
            lignes.append({"i": i, "label": o["label"], "capitaine": o["capitaine_nom"],
                           "p1": sum(g) / n, "dp1": md, "se": se,
                           "ep": o["ep"], "dep": o["ep"] - options[ref]["ep"],
                           "rang_ep": rang_ep[i], "reference": i == ref})
        lignes.sort(key=lambda r: (-r["dp1"], r["rang_ep"]))
        for r, ligne in enumerate(lignes, 1):
            ligne["rang_p1"] = r
        vues.append({"id": l.get("id"), "name": l.get("name"),
                     "n_managers": len(managers), "rang": me.get("rank"),
                     "p1_reference": p_ref, "options": lignes,
                     "modele": mod, "controle": ctl, "reste": reste, "n": n,
                     "resolu": p_ref * n >= VICTOIRES_MIN,
                     "desaccord": _desaccord(lignes, gains)})
    return vues


def _spearman(a, b):
    n = len(a)
    if n < 3:
        return None
    d2 = sum((x - y) ** 2 for x, y in zip(a, b))
    return 1 - 6 * d2 / (n * (n * n - 1))


def _desaccord(lignes, gains):
    """Où le classement par P(1er) contredit le classement par EP.

    L'écart entre les deux têtes porte son erreur Monte-Carlo APPARIÉE (mêmes
    tirages) : sous deux erreurs, le désaccord est indiscernable du hasard
    de la simulation et le rapport le dit."""
    top_p1 = min(lignes, key=lambda r: r["rang_p1"])
    top_ep = min(lignes, key=lambda r: r["rang_ep"])
    d = [x - y for x, y in zip(gains[top_p1["i"]], gains[top_ep["i"]])]
    n = len(d)
    md = sum(d) / n
    se = math.sqrt(sum((x - md) ** 2 for x in d) / (n * (n - 1))) if n > 1 else 0.0
    return {"meme_tete": top_p1 is top_ep,
            "tete_p1": f"{top_p1['label']} (C {top_p1['capitaine']})",
            "tete_ep": f"{top_ep['label']} (C {top_ep['capitaine']})",
            "ecart_p1_tetes": md, "se_ecart": se,
            "discernable": abs(md) > 2 * se,
            "spearman": _spearman([r["rang_p1"] for r in lignes],
                                  [r["rang_ep"] for r in lignes])}


def depuis_snapshot(parsed, contract, squad_ids, bank, n=N_TIRAGES):
    """Rattache le calcul au snapshot : ligues, historiques, journées jouées.

    Les historiques et les picks sont des données PERSONNELLES : ils restent
    dans le rapport, jamais dans le contrat."""
    ligues = parsed.get("leagues") or [{
        "id": parsed.get("league_id"), "name": "mini-ligue",
        "standings": parsed.get("standings", []),
        "rivals": parsed.get("rivals", {})}]
    tid = parsed.get("team_id")
    histories = {tid: (parsed.get("my") or {}).get("history")}
    for l in ligues:
        for rid, r in (l.get("rivals") or {}).items():
            histories[rid] = r.get("history")
    jouees = sorted(e["id"] for e in parsed.get("events", []) if e.get("finished"))
    options = options_semaine(contract, squad_ids, bank)
    return p_premier(contract, ligues, tid, options, histories, jouees, n=n)
