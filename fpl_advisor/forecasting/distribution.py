# -*- coding: utf-8 -*-
"""Distributions de points simulées, aléa partagé au sein de chaque équipe.

L'espérance dit combien un joueur marque EN MOYENNE. Elle ne dit ni la chance
d'un retour à 2 points, ni celle d'un 15, ni — surtout — que deux défenseurs
d'une même équipe gagnent ou perdent leur clean sheet ENSEMBLE. Les trois
scénarios (prudent, central, favorable) ne le disent pas non plus : ce sont
trois jeux de priors, pas trois issues de match.

Le simulateur tire, pour chaque match et chaque tirage :

  1. les buts de chaque équipe, Poisson(λ) — le λ même du moteur. C'est
     l'aléa PARTAGÉ : il porte le clean sheet et le malus d'encaissés de toute
     la défense, et multiplie les buts et passes de toute l'attaque ;
  2. l'état de minutes de chaque joueur : 0, entrée (25 min), 60+ — avec les
     probabilités du contrat ;
  3. les événements individuels, conditionnés par 1 et 2.

Chaque composante garde EXACTEMENT l'espérance du contrat (aux arrondis de
Monte-Carlo près) : le simulateur ajoute une forme, il ne change pas la
moyenne. Ce qui est simplifié, et dit : bonus et arrêts indépendants des buts,
cartons rouges, penalties et buts contre son camp ignorés (le moteur les
ignore aussi).

Entrée : uniquement des lignes du contrat de projections, le calendrier de la
GW et les λ par match. La même fonction sert donc à produire la distribution
d'un contrat neuf et à migrer un contrat figé de version 1.0.
"""

import math
import random

from .. import scoring

N_TIRAGES = 1000
GRAINE = 20260827
CAMEO_SHARE = 25 / 90.0
QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


def _poisson(rng, lam):
    """Knuth : exact, et rapide pour les λ d'un match de football (< 5)."""
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    seuil, k, p = math.exp(-lam), 0, rng.random()
    while p > seuil:
        k += 1
        p *= rng.random()
    return k


def _floor_half_mean(lam):
    """E[⌊X/2⌋], X ~ Poisson(λ) — même formule que teams.expected_conceded_malus."""
    out, p = 0.0, math.exp(-lam)
    for k in range(0, 11):
        out += p * (k // 2)
        p *= lam / (k + 1)
    return out


def lambdas_contre(rows, players, gw):
    """{team_id: λ_contre} relu dans les composantes clean sheet d'une GW
    simple : cs = P(60+) × e^(−λ) × CS_POINTS. Exact, aucune donnée externe."""
    lam = {}
    for r in rows:
        if r.gw != gw or r.n_fixtures != 1:
            continue
        m = players[str(r.player_id)]
        et = m["element_type"]
        if et not in (1, 2) or r.p60 < 0.05 or r.components["cs"] <= 0:
            continue
        lam.setdefault(m["team"], []).append(
            -math.log(r.components["cs"] / (scoring.CS_POINTS[et] * r.p60)))
    return {t: sum(v) / len(v) for t, v in lam.items()}


def _profil(r, et, lam_contre):
    """Taux conditionnels par unité de temps de jeu, déduits du contrat.

    `share` = E[fraction de match jouée]. Diviser une espérance par `share`
    donne le taux « par match plein » ; le tirage le remultiplie par la
    fraction réellement jouée, ce qui rend l'espérance exacte."""
    c = r.components
    p60 = r.p60
    p_cameo = max(0.0, r.p_play - p60)
    share = p60 + CAMEO_SHARE * p_cameo
    n = max(1, r.n_fixtures)
    if share <= 0:
        return None
    malus = -c["malus"] / n
    if et in (1, 2):
        # Malus = cartons (∝ share) + encaissés (∝ P(60+)). La part encaissés
        # se recalcule exactement depuis λ_contre ; le reste est le carton.
        malus -= p60 * _floor_half_mean(lam_contre)
    return {
        "p60": p60, "p_cameo": p_cameo,
        "g": c["goals"] / n / scoring.GOAL_POINTS[et] / share,
        "a": c["assists"] / n / scoring.ASSIST_POINTS / share,
        "b": c["bonus"] / n / share,
        "s": c["saves"] / n / share,
        "y": max(0.0, malus) / share,
        "dc": (min(1.0, c["defcon"] / n / (r.p_play * scoring.DEFCON_POINTS))
               if r.p_play > 0 else 0.0),
    }


def simulate_gw(rows, players, gw, fixtures, lam_par_match=None,
                n=N_TIRAGES, seed=GRAINE, partage=True):
    """{player_id: [points par tirage]} pour la GW `gw`.

    `fixtures` : [(team_h, team_a)] de la GW. `lam_par_match` : {(h, a):
    (λ_h, λ_a)} ; à défaut, relu dans les composantes (GW simple seulement).
    `partage=False` tire les buts d'équipe indépendamment pour CHAQUE joueur :
    mêmes marges, aucune corrélation — sert de témoin au banc d'essai."""
    rng = random.Random(seed * 1000 + gw)
    if lam_par_match is None:
        lc = lambdas_contre(rows, players, gw)
        avg = scoring.LEAGUE_AVG_GOALS
        lam_par_match = {(h, a): (lc.get(a, avg), lc.get(h, avg)) for h, a in fixtures}
    # Pour chaque équipe : ses matchs, avec (λ_pour, λ_contre, index du match).
    matchs_equipe = {}
    for i, (h, a) in enumerate(fixtures):
        lh, la = lam_par_match[(h, a)]
        matchs_equipe.setdefault(h, []).append((i, lh, la, 0))
        matchs_equipe.setdefault(a, []).append((i, la, lh, 1))

    joueurs = []
    for r in rows:
        if r.gw != gw:
            continue
        m = players[str(r.player_id)]
        ms = matchs_equipe.get(m["team"], []) if r.n_fixtures else []
        profils = [(mt, _profil(r, m["element_type"], mt[2])) for mt in ms]
        joueurs.append((r.player_id, m["element_type"], profils))

    et_cs = scoring.CS_POINTS
    out = {pid: [0] * n for pid, _, _ in joueurs}
    for t in range(n):
        buts = [(_poisson(rng, lam_par_match[f][0]), _poisson(rng, lam_par_match[f][1]))
                for f in fixtures]
        for pid, et, profils in joueurs:
            pts = 0
            for (i, lam_pour, lam_contre, cote), pr in profils:
                if pr is None:
                    continue
                u = rng.random()
                if u < pr["p60"]:
                    f, pts_app = 1.0, scoring.APPEARANCE_GE60
                elif u < pr["p60"] + pr["p_cameo"]:
                    f, pts_app = CAMEO_SHARE, scoring.APPEARANCE_LT60
                else:
                    continue
                if partage:
                    pour, contre = buts[i][cote], buts[i][1 - cote]
                else:
                    pour, contre = _poisson(rng, lam_pour), _poisson(rng, lam_contre)
                pts += pts_app
                ratio = pour / lam_pour if lam_pour > 0 else 0.0
                if pr["g"] and pour:
                    pts += scoring.GOAL_POINTS[et] * _poisson(rng, pr["g"] * f * ratio)
                if pr["a"] and pour:
                    pts += scoring.ASSIST_POINTS * _poisson(rng, pr["a"] * f * ratio)
                if f == 1.0 and et in (1, 2, 3):
                    if contre == 0:
                        pts += et_cs[et]
                    elif et in (1, 2):
                        pts -= contre // scoring.GOALS_CONCEDED_MALUS_EVERY
                if pr["s"]:
                    pts += _poisson(rng, pr["s"] * f)
                if pr["b"]:
                    q = min(1.0, pr["b"] * f / 3.0)
                    pts += sum(1 for _ in range(3) if rng.random() < q)
                if pr["y"] and rng.random() < pr["y"] * f:
                    pts -= 1
                if pr["dc"] and rng.random() < pr["dc"]:
                    pts += scoring.DEFCON_POINTS
            out[pid][t] = pts
    return out


def summarize(samples):
    """Résumé sérialisable d'une distribution simulée."""
    xs = sorted(samples)
    n = len(xs)
    q = [xs[min(n - 1, int(p * n))] for p in QUANTILES]
    return {"mean": sum(xs) / n, "q": q,
            "p_ge_6": sum(1 for x in xs if x >= 6) / n,
            "p_ge_10": sum(1 for x in xs if x >= 10) / n}


def crps(samples, y):
    """CRPS empirique : E|X − y| − ½ E|X − X'|. Plus bas est meilleur ; pour
    une distribution ponctuelle, c'est l'erreur absolue."""
    xs = sorted(samples)
    n = len(xs)
    e1 = sum(abs(x - y) for x in xs) / n
    # E|X − X'| = (2 / n²) Σ (2i − n + 1) x_(i), i de 0 à n − 1
    e2 = 2.0 * sum((2 * i - n + 1) * x for i, x in enumerate(xs)) / (n * n)
    return e1 - 0.5 * e2
