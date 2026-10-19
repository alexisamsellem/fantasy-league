# -*- coding: utf-8 -*-
"""Plan de transferts exact sur plusieurs GW : programme linéaire en nombres
entiers (PuLP + HiGHS).

Le scan historique (`transfers.transfer_scan`) essaie chaque échange
un-pour-un de la GW de décision, puis garde l'effectif figé sur l'horizon. Il
ne voit ni un deuxième transfert gratuit mis en banque la semaine dernière, ni
un hit (−4) qui paie, ni un transfert qu'il vaut mieux faire la semaine
PROCHAINE. Le programme ci-dessous voit tout cela d'un coup, et rend
l'optimum — pas un sommet local.

Variables, pour chaque joueur p et chaque GW t de l'horizon :

  x[p,t]  dans l'effectif        s[p,t]  dans le XI        c[p,t]  capitaine
  b[p,t]  acheté avant t         v[p,t]  vendu avant t
et par GW : ft[t] transferts gratuits disponibles, h[t] hits, u[t] gratuits
utilisés, z[t] « des hits sont pris ».

Contraintes : quotas de poste (2/5/5/3), au plus 3 par club, valeur d'équipe
constante (prix de vente approximé par le prix affiché, comme le scan), XI
légal (1 GB, 3–5 DEF, 2–5 MIL, 1–3 ATT), un capitaine dans le XI. Règle FPL
des transferts : chaque GW apporte un gratuit de plus, plafonné à 5 ; un hit
n'est possible qu'une fois les gratuits épuisés.

Objectif : Σ_t [EP du XI + EP du capitaine] − 4 × hits + valeur des gratuits
encore en banque à la fin de l'horizon. Cette dernière valeur (`FT_VALUE`)
remplace le seuil fixe du scan : sans elle, l'optimum dépenserait chaque
gratuit pour +0,1 pt en dernière semaine d'horizon.

Garantie : le plan du scan est une solution admissible de ce programme ; son
optimum ne peut donc pas valoir moins que lui, sur le même objectif. C'est
vérifié sur l'archive par `scripts/banc_optimiseur.py`.
"""

from .squad import pick_xi

QUOTAS = {1: 2, 2: 5, 3: 5, 4: 3}
XI_BORNES = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}
PAR_CLUB = 3
MAX_FT = 5
HIT = 4
FT_VALUE = 2.0          # pts : valeur d'un gratuit en banque en fin d'horizon [H]
M = 15                  # grand M des hits : plus de transferts qu'il n'en faut
GAP = 1e-7              # écart relatif toléré à l'optimum prouvé par HiGHS


FIN = 99                # indice de la banque après la dernière GW de l'horizon


def _fabrique(pb):
    """Dictionnaires de variables, quelle que soit la version de PuLP : la 4.x
    les crée par le problème, les versions antérieures par LpVariable."""
    import pulp
    if hasattr(pb, "add_variable_dicts"):
        return lambda n, idx, **kw: pb.add_variable_dicts(n, idx, **kw)
    return lambda n, idx, **kw: pulp.LpVariable.dicts(n, idx, **kw)


def disponible():
    """PuLP et HiGHS sont-ils installés ? Sans eux, l'appelant le dit."""
    try:
        import pulp
        return "HiGHS" in pulp.listSolvers(onlyAvailable=True)
    except ImportError:
        return False


def evaluer(by_id, effectifs, gws, hits, ft_fin, ft_value=FT_VALUE):
    """Valeur d'un plan, sur l'objectif du programme, recalculée sans lui :
    meilleur XI et meilleur capitaine de chaque effectif, moins les hits.

    Rend (valeur sans banque, valeur avec banque). C'est l'arbitre commun du
    scan et du programme : chacun est jugé par la même fonction."""
    v = 0.0
    for g in gws:
        rows = [dict(by_id[p], ep=by_id[p]["eps"].get(g, 0.0))
                for p in effectifs[g] if p in by_id]
        xi, _ = pick_xi(rows)
        v += sum(r["ep"] for r in xi) + max(r["ep"] for r in xi)
    v -= HIT * sum(hits.get(g, 0) for g in gws)
    return v, v + ft_value * ft_fin


def ft_suivant(ft, n):
    """Règle FPL : gratuits de la GW suivante après n transferts."""
    return min(MAX_FT, max(0, ft - n) + 1)


def plan_transferts(rows, squad_ids, bank, gws, free_transfers=1,
                    ft_value=FT_VALUE, time_limit=120, msg=False,
                    sans_transfert_a=None, au_moins_un_a=None):
    """Plan optimal sur `gws`. `rows` : lignes du contrat (un scénario).

    Rend {status, effectifs, achats, ventes, hits, ft, ft_fin, xi, capitaines,
    valeur, valeur_banque}. Un joueur détenu absent du contrat est traité comme
    déjà parti : sa place doit être reprise, ce qui coûte un transfert.
    `sans_transfert_a` interdit tout transfert à cette GW (plan d'attente) ;
    `au_moins_un_a` en impose au moins un (meilleur échange immédiat)."""
    import pulp

    by_id = {r["id"]: r for r in rows}
    P = sorted(by_id)
    S0 = {p for p in squad_ids if p in by_id}
    valeur = bank + sum(by_id[p]["now_cost"] for p in S0)
    T = list(gws)

    pb = pulp.LpProblem("plan_transferts", pulp.LpMaximize)
    var = _fabrique(pb)
    x, s, c, b, v = (var(n, (P, T), cat="Binary") for n in "xscbv")
    ft = var("ft", T + [FIN], lowBound=0, upBound=MAX_FT, cat="Integer")
    h = var("h", T, lowBound=0, upBound=M, cat="Integer")
    u = var("u", T, lowBound=0, upBound=MAX_FT, cat="Integer")
    z = var("z", T, cat="Binary")

    ep = lambda p, t: by_id[p]["eps"].get(t, 0.0)
    pb += (pulp.lpSum(ep(p, t) * (s[p][t] + c[p][t]) for p in P for t in T)
           - HIT * pulp.lpSum(h[t] for t in T) + ft_value * ft[FIN])

    pb += ft[T[0]] == min(MAX_FT, max(0, int(free_transfers)))
    clubs = sorted({by_id[p]["team"] for p in P})
    for i, t in enumerate(T):
        for p in P:
            avant = (1 if p in S0 else 0) if i == 0 else x[p][T[i - 1]]
            pb += x[p][t] - avant == b[p][t] - v[p][t]
            pb += b[p][t] + v[p][t] <= 1
            pb += s[p][t] <= x[p][t]
            pb += c[p][t] <= s[p][t]
        for et, q in QUOTAS.items():
            pb += pulp.lpSum(x[p][t] for p in P if by_id[p]["element_type"] == et) == q
            lo, hi = XI_BORNES[et]
            n_xi = pulp.lpSum(s[p][t] for p in P if by_id[p]["element_type"] == et)
            pb += n_xi >= lo
            pb += n_xi <= hi
        for k in clubs:
            pb += pulp.lpSum(x[p][t] for p in P if by_id[p]["team"] == k) <= PAR_CLUB
        pb += pulp.lpSum(by_id[p]["now_cost"] * x[p][t] for p in P) <= valeur
        pb += pulp.lpSum(s[p][t] for p in P) == 11
        pb += pulp.lpSum(c[p][t] for p in P) == 1
        # Transferts : n = gratuits utilisés + hits ; hit seulement si plus
        # aucun gratuit (z = 1 ⇒ u = ft) ; banque de la GW suivante.
        n = pulp.lpSum(b[p][t] for p in P)
        if t == sans_transfert_a:
            pb += n == 0
        if t == au_moins_un_a:
            pb += n >= 1
        pb += n == u[t] + h[t]
        pb += u[t] <= ft[t]
        pb += h[t] <= M * z[t]
        pb += u[t] >= ft[t] - MAX_FT * (1 - z[t])
        suivant = ft[T[i + 1]] if i + 1 < len(T) else ft[FIN]
        pb += suivant <= ft[t] - u[t] + 1

    res = pb.solve(pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=GAP))
    # PuLP 4.x rend un objet de statistiques, les versions antérieures un code.
    code = int(getattr(res, "status", res))
    status = "Optimal" if code == 1 else f"code {code}"
    if status != "Optimal":
        raise ValueError(f"programme de transferts : statut {status}")

    val = lambda var: int(round(var.value() or 0))
    out = {"status": status, "effectifs": {}, "achats": {}, "ventes": {},
           "hits": {}, "ft": {}, "xi": {}, "capitaines": {}}
    for t in T:
        out["effectifs"][t] = [p for p in P if val(x[p][t])]
        out["achats"][t] = [p for p in P if val(b[p][t])]
        out["ventes"][t] = [p for p in P if val(v[p][t])]
        out["hits"][t] = val(h[t])
        out["ft"][t] = val(ft[t])
        out["xi"][t] = [p for p in P if val(s[p][t])]
        out["capitaines"][t] = next(p for p in P if val(c[p][t]))
    # Banque de fin recalculée par la règle, pas lue dans le solveur : la
    # contrainte est une inégalité, l'optimum la sature, la règle le garantit.
    f = out["ft"][T[0]]
    for t in T:
        f = ft_suivant(f, len(out["achats"][t]))
    out["ft_fin"] = f
    out["valeur"], out["valeur_banque"] = evaluer(
        by_id, out["effectifs"], T, out["hits"], f, ft_value)
    return out


def echanges(plan, by_id, gw):
    """Ventes et achats d'une GW appariés par poste, pour l'affichage."""
    ventes = sorted(plan["ventes"][gw], key=lambda p: by_id[p]["element_type"]) \
        if gw in plan["ventes"] else []
    achats = sorted(plan["achats"][gw], key=lambda p: by_id[p]["element_type"])
    out, restants = [], list(achats)
    for o in ventes:
        et = by_id[o]["element_type"] if o in by_id else None
        i = next((k for k, a in enumerate(restants) if by_id[a]["element_type"] == et), 0)
        out.append((o, restants.pop(i)))
    return out
