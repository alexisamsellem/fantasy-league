# -*- coding: utf-8 -*-
"""Recalibration de P(60+) : apprise sur les journées passées, jamais au-delà.

Le défaut est répété : sur chacune des journées GW2–GW6, la tranche 60–80 %
annoncée s'est réalisée nettement plus souvent qu'annoncé (le moteur est trop
prudent sur les titulaires probables). Un défaut qui se répète se corrige ;
un défaut vu une fois ne se corrige pas.

La correction est une recalibration de Platt à deux paramètres :

    p' = σ(a + b · logit(p))

Deux paramètres seulement, parce que l'échantillon est de quelques centaines
de joueurs par journée et qu'une courbe libre (isotonique) apprendrait le
bruit. `b > 1` étire les probabilités loin de 50 %, `a > 0` les relève.

Protocole sans regard vers l'avant (`walk_forward`) : la carte qui note la
journée k est ajustée sur les journées strictement antérieures à k, et sur
elles seules. La carte livrée au moteur est ajustée sur TOUTES les journées
notées à la date de livraison — elle ne sera jugée que sur les suivantes.

Les p exactement nuls (joueur indisponible) ou égaux à 1 sont laissés tels
quels : la recalibration corrige un biais de titularisation, pas un statut
officiel d'infirmerie.
"""

import math

from ..forecasting.minutes import platt

EPS = 1e-4


def logit(p):
    p = min(1 - EPS, max(EPS, p))
    return math.log(p / (1 - p))


def sigma(x):
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    e = math.exp(x)
    return e / (1 + e)


def appliquer(p, a, b):
    """Carte de Platt — la MÊME fonction que celle du moteur."""
    return platt(p, a, b, EPS)


def ajuster(pairs, iterations=50):
    """(a, b) par maximum de vraisemblance (Newton-Raphson) sur [(p, y)].

    Les p hors de ]0, 1[ sont ignorés, comme dans `appliquer`."""
    xs = [(logit(p), y) for p, y in pairs if 0.0 < p < 1.0]
    if len(xs) < 20:
        raise ValueError(f"{len(xs)} paires : trop peu pour ajuster une carte")
    a, b = 0.0, 1.0
    for _ in range(iterations):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in xs:
            q = sigma(a + b * x)
            r = y - q
            w = q * (1 - q)
            ga += r
            gb += r * x
            haa += w
            hab += w * x
            hbb += w * x * x
        det = haa * hbb - hab * hab
        if det <= 0:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a + da, b + db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            break
    return a, b


def walk_forward(pairs_par_gw, min_passe=1):
    """{gw: {"a", "b", "fit_sur", "pairs_cal"}} pour chaque journée notable
    hors échantillon : la carte de la journée k ne voit que les journées < k.

    `pairs_par_gw` : {gw: [(p, y)]}. Les `min_passe` premières journées n'ont
    pas d'historique suffisant et ne sont pas notées."""
    gws = sorted(pairs_par_gw)
    out = {}
    for i, g in enumerate(gws):
        passe = gws[:i]
        if len(passe) < min_passe:
            continue
        a, b = ajuster([pr for h in passe for pr in pairs_par_gw[h]])
        out[g] = {"a": a, "b": b, "fit_sur": passe,
                  "pairs_cal": [(appliquer(p, a, b), y) for p, y in pairs_par_gw[g]]}
    return out
