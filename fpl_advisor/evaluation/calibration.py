# -*- coding: utf-8 -*-
"""Calibration : les probabilités annoncées se réalisent-elles ?

C'est le juge du système. Un effectif qui marque beaucoup peut n'être que
chanceux ; des probabilités bien calibrées, elles, se vérifient. Quand le
moteur dit « 60 % », il faut qu'environ 60 % de ces joueurs jouent vraiment
60 minutes — sinon les points espérés sont faux, même si le classement paraît
raisonnable.

Deux mesures, aucune interprétation généreuse :

  score de Brier      moyenne des (p − résultat)² — plus bas est meilleur
  score de compétence 1 − Brier / Brier_référence, la référence étant « annoncer
                      le taux de base pour tout le monde ». NÉGATIF signifie que
                      le moteur fait pire qu'un modèle qui ne sait rien.

Le tableau de fiabilité découpe les prédictions en tranches et compare, tranche
par tranche, la probabilité annoncée à la fréquence observée. C'est lui qui dit
OÙ le moteur se trompe : trop confiant sur les titulaires, trop prudent sur les
remplaçants, ou l'inverse.

Ce module ne lit que le contrat de projections et des minutes observées. Il ne
prévoit rien, ne choisit personne, et n'importe pas l'optimiseur.
"""

BUCKETS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))
MIN_PAIRS = 50          # en dessous, on refuse de conclure quoi que ce soit

METRICS = {
    "p60": {"label": "P(60+ minutes)", "seuil": 60,
            "note": "la mesure décisive : elle porte les points de présence, "
                    "les clean sheets et l'essentiel du risque de capitaine"},
    "p_play": {"label": "P(jouer au moins une minute)", "seuil": 1,
               "note": "plus facile à prévoir, donc moins discriminante"},
}


def brier(pairs):
    """Moyenne des (probabilité − résultat)². Rend None sur une liste vide."""
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def reliability(pairs, buckets=BUCKETS):
    """Par tranche de probabilité annoncée : effectif, moyenne annoncée,
    fréquence observée, écart. Les tranches vides sont conservées et marquées
    — une tranche jamais utilisée est une information, pas un trou."""
    rows = []
    for lo, hi in buckets:
        # La dernière tranche est fermée à droite pour ne perdre aucun p = 1.
        dedans = [(p, y) for p, y in pairs
                  if (lo <= p < hi) or (hi >= 1.0 and p >= hi)]
        n = len(dedans)
        annonce = sum(p for p, _ in dedans) / n if n else None
        observe = sum(y for _, y in dedans) / n if n else None
        rows.append({
            "lo": lo, "hi": hi, "n": n,
            "annonce": annonce, "observe": observe,
            "ecart": None if n == 0 else observe - annonce,
        })
    return rows


def _pairs(contract, minutes_by_id, gw, champ, seuil):
    """(probabilité, résultat) pour chaque joueur réellement évaluable.

    Exclus, et comptés à part : les joueurs sans match cette GW (le contrat le
    dit par `n_fixtures`) et ceux absents des données observées. Sans cette
    exclusion, un report de match compterait comme une absence prédite ratée."""
    pairs, sans_match, non_observes = [], 0, 0
    for r in contract.rows:
        if r.gw != gw:
            continue
        if not r.n_fixtures:
            sans_match += 1
            continue
        mins = minutes_by_id.get(r.player_id)
        if mins is None:
            non_observes += 1
            continue
        pairs.append((float(getattr(r, champ)), 1.0 if mins >= seuil else 0.0))
    return pairs, sans_match, non_observes


def score_metric(contract, minutes_by_id, gw, champ):
    meta = METRICS[champ]
    pairs, sans_match, non_observes = _pairs(
        contract, minutes_by_id, gw, champ, meta["seuil"])
    n = len(pairs)
    taux_base = (sum(y for _, y in pairs) / n) if n else None
    b = brier(pairs)
    # Référence : annoncer le taux de base pour tout le monde. C'est le modèle
    # qui ne sait rien mais connaît la population — battre ça est le minimum.
    b_ref = None if taux_base is None else taux_base * (1 - taux_base)
    competence = None if not b_ref else 1 - b / b_ref
    return {
        "champ": champ, "label": meta["label"], "note": meta["note"],
        "n": n, "assez": n >= MIN_PAIRS,
        "sans_match": sans_match, "non_observes": non_observes,
        "taux_base": taux_base, "brier": b, "brier_reference": b_ref,
        "competence": competence,
        "annonce_moyenne": (sum(p for p, _ in pairs) / n) if n else None,
        "fiabilite": reliability(pairs),
    }


def assess(contract, minutes_by_id, gw=None):
    """Contrat figé + minutes réellement jouées → verdict de calibration.

    `minutes_by_id` : {player_id: minutes} de la GW évaluée, tel que lu dans un
    snapshot postérieur au match. `gw` par défaut : la GW de décision du contrat.
    """
    gw = gw if gw is not None else contract.gw
    if gw not in contract.horizon:
        raise SystemExit(
            f"GW{gw} absente de l'horizon du contrat {list(contract.horizon)} : "
            "ce contrat ne contient aucune prédiction pour cette journée.")
    if not minutes_by_id:
        raise SystemExit(
            f"Aucune minute observée pour la GW{gw} : la journée n'est pas "
            "jouée, ou le snapshot ne contient pas event-{gw}-live.json.")
    metriques = {c: score_metric(contract, minutes_by_id, gw, c) for c in METRICS}
    joue = sum(1 for m in minutes_by_id.values() if m)
    return {
        "gw": gw,
        "as_of_projections": contract.as_of,
        "model_version": contract.model_version,
        "contract_version": contract.contract_version,
        "snapshot_projections": contract.snapshot,
        "synthetic": contract.synthetic,
        "n_observes": len(minutes_by_id),
        "n_ayant_joue": joue,
        "metriques": metriques,
        "conclusion": _conclusion(metriques),
    }


def _conclusion(metriques):
    """Une phrase, sans complaisance. La calibration d'une seule GW ne prouve
    rien : elle peut seulement révéler un défaut grossier."""
    p60 = metriques["p60"]
    if not p60["assez"]:
        return (f"Échantillon insuffisant ({p60['n']} joueurs, minimum "
                f"{MIN_PAIRS}) : aucune conclusion.")
    c = p60["competence"]
    if c is None:
        return "Taux de base dégénéré : le score de compétence n'a pas de sens."
    if c < 0:
        return (f"ÉCHEC sur cette journée : score de compétence {c:+.3f} — le "
                "moteur fait PIRE qu'annoncer le taux de base à tout le monde. "
                "Un seul point de mesure ne condamne pas le modèle, mais il "
                "interdit de le présenter comme calibré.")
    if c < 0.05:
        return (f"Sans valeur ajoutée mesurable : score de compétence {c:+.3f}, "
                "à peine mieux que le taux de base. À confirmer sur plusieurs "
                "journées avant d'en conclure quoi que ce soit.")
    return (f"Score de compétence {c:+.3f} sur cette journée : le moteur bat le "
            "taux de base. UNE journée ne démontre pas la calibration — il faut "
            "la répétition, et le tableau de fiabilité pour savoir où il se "
            "trompe encore.")
