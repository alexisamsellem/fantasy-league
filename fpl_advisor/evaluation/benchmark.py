# -*- coding: utf-8 -*-
"""Banc d'essai honnête : points réels contre `ep` du moteur et `ep_next` FPL.

La calibration des minutes dit si les probabilités de présence se réalisent.
Elle ne dit pas si le moteur prévoit mieux les POINTS que le repère public
gratuit. C'est la seule question qui justifie son existence : si `ep_next`,
publié par FPL au même instant, prévoit aussi bien, le moteur ne sert à rien.

Règles, toutes non négociables :

  - on ne note que des contrats FIGÉS avant la deadline (`as_of < deadline`),
    lus tels quels — aucune projection recalculée ;
  - les deux prévisions viennent du MÊME fichier : `ep` (moteur, GW de
    décision) et `ep_next` (FPL, stocké dans `players`) ont la même date de
    connaissance ;
  - les résultats viennent de `resultats-observes/` (live FPL validé) ;
  - l'incertitude est mesurée par grappes : les joueurs d'une même équipe dans
    un même match ne sont pas indépendants (un 4-0 touche onze joueurs). Le
    bootstrap rééchantillonne donc des couples (GW, équipe), pas des joueurs ;
  - Diebold-Mariano sur la série des journées, en contre-épreuve : avec cinq
    journées il a peu de puissance, et c'est dit.

Ce module ne lit que des contrats et des résultats figés. Il ne prévoit rien.
"""

import gzip
import json
import math
import random
from pathlib import Path

B_DEFAUT = 10000
NIVEAU = 0.95
SEUIL_PERTINENT = 2.0      # pts : sous-population « joueurs envisageables »,
                           # définie AVANT les matchs sur les deux prévisions


# ------------------------------------------------------------- données ----

def charger_resultats(gw, dossier="resultats-observes"):
    """Résultat figé d'une GW (`scripts/figer_resultats.py`), ou None."""
    p = Path(dossier) / f"resultats-GW{gw}.json.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def paires_points(contract, resultats):
    """Une ligne par joueur évaluable de la GW de décision.

    Exclus et comptés : les joueurs sans match (le contrat le dit) et ceux
    absents du live. Un `ep_next` illisible exclut aussi la ligne — les deux
    prévisions doivent porter sur la même population, sinon la comparaison
    est truquée par construction."""
    if str(contract.as_of) >= str(contract.deadline):
        raise ValueError(
            f"GW{contract.gw} : contrat figé le {contract.as_of}, après la "
            f"deadline {contract.deadline} — non notable.")
    obs = resultats["players"]
    lignes, exclus = [], {"sans_match": 0, "non_observes": 0, "ep_next": 0}
    for r in contract.rows:
        if r.gw != contract.gw:
            continue
        if not r.n_fixtures:
            exclus["sans_match"] += 1
            continue
        o = obs.get(str(r.player_id))
        if o is None:
            exclus["non_observes"] += 1
            continue
        meta = contract.players[str(r.player_id)]
        epn = _float(meta.get("ep_next"))
        if epn is None:
            exclus["ep_next"] += 1
            continue
        lignes.append({"gw": r.gw, "player_id": r.player_id,
                       "team": meta["team"], "element_type": meta["element_type"],
                       "ep": float(r.ep), "ep_next": epn,
                       "y": float(o["total_points"]), "minutes": o["minutes"]})
    return lignes, exclus


# ---------------------------------------------------------- statistiques ----

def _quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = q * (len(xs) - 1)
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def bootstrap_grappes(lignes, stat, b=B_DEFAUT, seed=20260827, niveau=NIVEAU):
    """IC percentile d'une statistique appariée, rééchantillonnage par grappes
    (GW, équipe) stratifié par GW : chaque réplique garde autant d'équipes par
    journée que l'original. `stat(lignes) -> float`."""
    grappes = {}
    for l in lignes:
        grappes.setdefault(l["gw"], {}).setdefault(l["team"], []).append(l)
    par_gw = {g: list(t.values()) for g, t in grappes.items()}
    rng = random.Random(seed)
    tirages = []
    for _ in range(b):
        echant = []
        for gs in par_gw.values():
            for _ in range(len(gs)):
                echant.extend(gs[rng.randrange(len(gs))])
        tirages.append(stat(echant))
    a = (1 - niveau) / 2
    return _quantile(tirages, a), _quantile(tirages, 1 - a)


def _betacf(a, b, x):
    """Fraction continue de la bêta incomplète (Numerical Recipes, 6.4)."""
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-30 else 1e-30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-30 else 1e-30
        de = d * c
        h *= de
        if abs(de - 1) < 1e-12:
            break
    return h


def student_p_bilateral(t, df):
    """P(|T| ≥ |t|) pour T ~ Student(df), sans scipy."""
    x = df / (df + t * t)
    a, b = df / 2.0, 0.5
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta) if 0 < x < 1 else 0.0
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    if x < (a + 1) / (a + b + 2):
        ib = front * _betacf(a, b, x) / a
    else:
        ib = 1 - front * _betacf(b, a, 1 - x) / b
    return ib


def diebold_mariano(d_par_periode):
    """Test DM sur la série des écarts de perte moyens par journée.

    Horizon d'une journée → pas de correction d'autocorrélation (HAC lag 0) ;
    loi de Student à n−1 ddl (correction de Harvey, Leybourne et Newbold pour
    petit échantillon). Rend {d_moy, t, ddl, p} ou None sous deux journées."""
    n = len(d_par_periode)
    if n < 2:
        return None
    m = sum(d_par_periode) / n
    var = sum((d - m) ** 2 for d in d_par_periode) / (n - 1)
    if var == 0:
        return {"d_moy": m, "t": math.inf if m else 0.0, "ddl": n - 1,
                "p": 0.0 if m else 1.0}
    t = m / math.sqrt(var / n)
    return {"d_moy": m, "t": t, "ddl": n - 1, "p": student_p_bilateral(t, n - 1)}


# ------------------------------------------------------------- verdict ----

def _mse(lignes, champ):
    return sum((l[champ] - l["y"]) ** 2 for l in lignes) / len(lignes)


def _mae(lignes, champ):
    return sum(abs(l[champ] - l["y"]) for l in lignes) / len(lignes)


def _dmse(lignes):
    return _mse(lignes, "ep") - _mse(lignes, "ep_next")


def _dmae(lignes):
    return _mae(lignes, "ep") - _mae(lignes, "ep_next")


def resume(lignes):
    """Erreurs des deux prévisions et biais sur un ensemble de lignes."""
    n = len(lignes)
    moy = lambda k: sum(l[k] for l in lignes) / n
    return {"n": n,
            "mse_ep": _mse(lignes, "ep"), "mse_ep_next": _mse(lignes, "ep_next"),
            "mae_ep": _mae(lignes, "ep"), "mae_ep_next": _mae(lignes, "ep_next"),
            "biais_ep": moy("ep") - moy("y"),
            "biais_ep_next": moy("ep_next") - moy("y"),
            "y_moy": moy("y")}


def verdict(ic, dm):
    """Oui seulement si le bootstrap ET Diebold-Mariano le disent au même
    seuil ; non si les deux disent l'inverse ; sinon non prouvé.

    `ic` porte sur Δ = perte(moteur) − perte(ep_next) : négatif = moteur
    meilleur."""
    lo, hi = ic
    dm_ok = dm is not None and dm["p"] < 1 - NIVEAU
    if hi < 0 and dm_ok and dm["d_moy"] < 0:
        return "oui"
    if lo > 0 and dm_ok and dm["d_moy"] > 0:
        return "non"
    return "non prouvé"


def evaluer(lignes_par_gw, b=B_DEFAUT, seed=20260827, filtre=None):
    """Banc d'essai complet. `lignes_par_gw` : {gw: lignes}. `filtre(l)`
    restreint la population (décidé sur les prévisions, jamais sur y)."""
    par_gw = {g: [l for l in ls if filtre is None or filtre(l)]
              for g, ls in sorted(lignes_par_gw.items())}
    par_gw = {g: ls for g, ls in par_gw.items() if ls}
    toutes = [l for ls in par_gw.values() for l in ls]
    out = {"par_gw": {}, "global": None}
    for g, ls in par_gw.items():
        r = resume(ls)
        r["ic_dmse"] = bootstrap_grappes(ls, _dmse, b=b, seed=seed + g)
        out["par_gw"][g] = r
    if not toutes:
        return out
    glob = resume(toutes)
    glob["dmse"] = _dmse(toutes)
    glob["dmae"] = _dmae(toutes)
    glob["ic_dmse"] = bootstrap_grappes(toutes, _dmse, b=b, seed=seed)
    glob["ic_dmae"] = bootstrap_grappes(toutes, _dmae, b=b, seed=seed + 1)
    glob["dm_mse"] = diebold_mariano([_dmse(ls) for ls in par_gw.values()])
    glob["dm_mae"] = diebold_mariano([_dmae(ls) for ls in par_gw.values()])
    glob["verdict_mse"] = verdict(glob["ic_dmse"], glob["dm_mse"])
    glob["verdict_mae"] = verdict(glob["ic_dmae"], glob["dm_mae"])
    out["global"] = glob
    return out


def pertinent(l):
    """Joueur envisageable : l'une des deux prévisions atteint le seuil."""
    return max(l["ep"], l["ep_next"]) >= SEUIL_PERTINENT
