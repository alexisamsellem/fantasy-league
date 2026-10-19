# -*- coding: utf-8 -*-
"""Le marché des paris comme juge des probabilités d'équipe du moteur.

Un bookmaker affiche des cotes qui contiennent sa marge : les probabilités
implicites 1/cote somment à plus de 1 (souvent 1,03 à 1,06). On retire cette
marge par normalisation multiplicative — chaque probabilité implicite est
divisée par leur somme — puis on cherche les deux intensités de Poisson
(λ_domicile, λ_extérieur) qui reproduisent au mieux les trois prix les plus
liquides : victoire domicile, victoire extérieur, plus de 2,5 buts.

Source : football-data.co.uk, colonnes `Avg*` (moyenne du marché, relevée le
vendredi après-midi pour un match du week-end, le mardi pour un match de
semaine — donc avant le coup d'envoi, à une heure proche de la deadline FPL).
Les colonnes `AvgC*` (cotes de clôture) sont postérieures à la deadline : le
banc d'essai ne les utilise pas.

Les probabilités d'équipe du moteur ne sont pas stockées telles quelles dans
le contrat figé, mais elles s'y lisent exactement : la composante clean sheet
d'un gardien ou d'un défenseur vaut P(60+) × e^(−λ_contre) × 4. On en tire
λ_contre de chaque équipe, donc λ_pour de son adversaire (`lambdas_moteur`).

Le module ne lit aucun fichier : il reçoit des contrats et des lignes CSV.
"""

import math

from .. import scoring

# Noms football-data.co.uk → nom court FPL (bootstrap teams[].short_name).
FD_TO_FPL = {
    "Arsenal": "ARS", "Aston Villa": "AVL", "Bournemouth": "BOU",
    "Brentford": "BRE", "Brighton": "BHA", "Chelsea": "CHE",
    "Coventry": "COV", "Crystal Palace": "CRY", "Everton": "EVE",
    "Fulham": "FUL", "Hull": "HUL", "Ipswich": "IPS", "Leeds": "LEE",
    "Liverpool": "LIV", "Man City": "MCI", "Man United": "MUN",
    "Newcastle": "NEW", "Nott'm Forest": "NFO", "Tottenham": "TOT",
    "Sunderland": "SUN",
    # Clubs d'autres saisons, pour que le fichier d'une saison passée se lise.
    "Burnley": "BUR", "Leicester": "LEI", "Southampton": "SOU",
    "West Ham": "WHU", "Wolves": "WOL", "Luton": "LUT", "Sheffield United": "SHU",
}

MAX_GOALS = 12


def devig(cotes):
    """Cotes décimales → probabilités sans marge (normalisation
    multiplicative). Rend (probas, marge)."""
    imp = [1.0 / c for c in cotes]
    s = sum(imp)
    return [p / s for p in imp], s - 1.0


def _pmf(lam):
    out, p = [], math.exp(-lam)
    for k in range(MAX_GOALS + 1):
        out.append(p)
        p *= lam / (k + 1)
    return out


def match_probs(lam_h, lam_a):
    """(P(domicile), P(nul), P(extérieur), P(plus de 2,5 buts)) — Poisson
    indépendants, le modèle même du moteur (`teams.fixture_lambdas`)."""
    ph, pa = _pmf(lam_h), _pmf(lam_a)
    h = d = a = under = 0.0
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            q = x * y
            if i > j:
                h += q
            elif i == j:
                d += q
            else:
                a += q
            if i + j <= 2:
                under += q
    return h, d, a, 1.0 - under


def fit_lambdas(p_home, p_away, p_over):
    """(λ_h, λ_a) minimisant l'écart quadratique aux trois probabilités.

    Gauss-Newton sur (log λ_h, log λ_a), dérivées numériques : deux inconnues,
    trois équations, une solution par moindres carrés."""
    cible = (p_home, p_away, p_over)
    x = [math.log(1.4), math.log(1.1)]

    def resid(v):
        h, _, a, o = match_probs(math.exp(v[0]), math.exp(v[1]))
        return [h - cible[0], a - cible[1], o - cible[2]]

    for _ in range(60):
        r = resid(x)
        eps = 1e-6
        jac = []
        for k in range(2):
            v = list(x)
            v[k] += eps
            rk = resid(v)
            jac.append([(rk[i] - r[i]) / eps for i in range(3)])
        # JᵀJ δ = −Jᵀr
        a11 = sum(j * j for j in jac[0])
        a12 = sum(p * q for p, q in zip(jac[0], jac[1]))
        a22 = sum(j * j for j in jac[1])
        b1 = -sum(p * q for p, q in zip(jac[0], r))
        b2 = -sum(p * q for p, q in zip(jac[1], r))
        det = a11 * a22 - a12 * a12
        if det <= 1e-18:
            break
        d1 = (a22 * b1 - a12 * b2) / det
        d2 = (a11 * b2 - a12 * b1) / det
        x = [x[0] + max(-1.0, min(1.0, d1)), x[1] + max(-1.0, min(1.0, d2))]
        if abs(d1) < 1e-9 and abs(d2) < 1e-9:
            break
    return math.exp(x[0]), math.exp(x[1])


def market_lambdas(row, prefix="Avg"):
    """Ligne football-data → {home, away, lam_h, lam_a, marge_1x2, marge_ou}
    ou None si une cote manque."""
    try:
        h, d, a = (float(row[f"{prefix}{k}"]) for k in ("H", "D", "A"))
        over, under = float(row[f"{prefix}>2.5"]), float(row[f"{prefix}<2.5"])
    except (KeyError, TypeError, ValueError):
        return None
    (ph, _, pa), m1 = devig([h, d, a])
    (po, _), m2 = devig([over, under])
    lam_h, lam_a = fit_lambdas(ph, pa, po)
    return {"home": FD_TO_FPL.get(row.get("HomeTeam"), row.get("HomeTeam")),
            "away": FD_TO_FPL.get(row.get("AwayTeam"), row.get("AwayTeam")),
            "lam_h": lam_h, "lam_a": lam_a, "marge_1x2": m1, "marge_ou": m2}


def lambdas_moteur(contract):
    """{team_id: λ_contre} lu dans les composantes figées de la GW de décision.

    Seules les journées simples sont lisibles (un match par équipe) : sur une
    double journée, la composante somme deux matchs. Les équipes absentes
    (aucun GB/DEF à P(60+) > 5 %) ne figurent pas dans le résultat."""
    lam = {}
    for r in contract.rows:
        if r.gw != contract.gw or r.n_fixtures != 1:
            continue
        m = contract.players[str(r.player_id)]
        et = m["element_type"]
        if et not in (1, 2) or r.p60 < 0.05 or r.components["cs"] <= 0:
            continue
        lam.setdefault(m["team"], []).append(
            -math.log(r.components["cs"] / (scoring.CS_POINTS[et] * r.p60)))
    return {t: sum(v) / len(v) for t, v in lam.items()}


def perte_buts(lam, k):
    """−log P(X = k), X ~ Poisson(λ) : log-loss du nombre de buts marqués."""
    return lam - k * math.log(lam) + math.lgamma(k + 1)


def perte_cs(lam_contre, cs):
    """Log-loss binaire du clean sheet : P(cs) = e^(−λ_contre)."""
    p = math.exp(-lam_contre)
    return -math.log(p) if cs else -math.log(1 - p)


def cotes_par_match(lignes_csv, prefix="Avg"):
    """{(nom court domicile, nom court extérieur): {lam_h, lam_a, gh, ga, …}}."""
    out = {}
    for row in lignes_csv:
        m = market_lambdas(row, prefix)
        if m is None:
            continue
        m["gh"], m["ga"] = int(row["FTHG"]), int(row["FTAG"])
        out[(m["home"], m["away"])] = m
    return out


def comparer(contract, resultats, cotes):
    """Une ligne par CÔTÉ de match (deux par match) : pertes du moteur et du
    marché sur les buts marqués et le clean sheet, mêmes matchs pour les deux.

    Un match absent des cotes, ou dont le score diffère entre FPL et
    football-data, est exclu et compté — jamais noté sur une seule source."""
    lam = lambdas_moteur(contract)
    lignes, exclus = [], 0
    for f in resultats["fixtures"]:
        h, a = contract.teams[str(f["team_h"])], contract.teams[str(f["team_a"])]
        m = cotes.get((h, a))
        if (m is None or f["team_h"] not in lam or f["team_a"] not in lam
                or (m["gh"], m["ga"]) != (f["team_h_score"], f["team_a_score"])):
            exclus += 1
            continue
        # λ_contre(X) est ce que X encaisse, donc ce que son adversaire marque.
        cotes_match = (
            # (λ_pour moteur, λ_pour marché, λ_contre moteur, λ_contre marché,
            #  buts marqués, buts encaissés)
            (lam[f["team_a"]], m["lam_h"], lam[f["team_h"]], m["lam_a"],
             f["team_h_score"], f["team_a_score"]),
            (lam[f["team_h"]], m["lam_a"], lam[f["team_a"]], m["lam_h"],
             f["team_a_score"], f["team_h_score"]),
        )
        for pour_e, pour_m, contre_e, contre_m, marque, encaisse in cotes_match:
            lignes.append({
                "gw": contract.gw, "team": f["id"],     # grappe = le match
                "buts_moteur": perte_buts(pour_e, marque),
                "buts_marche": perte_buts(pour_m, marque),
                "cs_moteur": perte_cs(contre_e, encaisse == 0),
                "cs_marche": perte_cs(contre_m, encaisse == 0),
                "lam_moteur": pour_e, "lam_marche": pour_m, "buts": marque,
            })
    return lignes, exclus

