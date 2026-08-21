# -*- coding: utf-8 -*-
"""Banc d'essai : projections internes contre baseline publique.

Deux effectifs légaux construits DEPUIS LE MÊME CONTRAT DE PROJECTIONS, avec le
MÊME sélecteur, la seule différence étant la fonction de valeur :

  A. `interne`  : EP cumulée sur l'horizon de la couche de prévision du dépôt.
  B. `baseline` : champ public officiel `ep_next` (ou repli déterministe
     `selected_by_percent`, défini à l'avance).

Utiliser le même sélecteur des deux côtés est délibéré : ce qui est comparé,
ce sont les PROJECTIONS, pas la recherche combinatoire. Ce module n'importe pas
`optimization` — il reçoit un `SelectionBackend` (voir `backend.py`).

Le protocole de comparaison est figé ici, avant toute observation de résultats.
`build_bench()` écrit les deux effectifs et les décisions par GW ;
`score_frozen()` exécute la comparaison une fois les GW jouées.
"""

import json
from pathlib import Path

from .baseline import BASELINE_FALLBACK, BASELINE_PRIMARY, baseline_rows  # noqa: F401
from .quality import assess

COMPARISON_PROTOCOL = {
    "horizon": "les 4 GW suivant la deadline du snapshot",
    "decision_rule": (
        "pour chaque GW, le XI, l'ordre du banc, le capitaine et le vice figés "
        "dans ce fichier sont appliqués tels quels ; aucun transfert, aucun "
        "chip, aucune re-décision en cours de route"),
    "metrics": [
        {"key": "score_total",
         "definition": "somme des points réels des 11 titulaires figés sur les "
                       "4 GW, capitaine doublé (vice doublé à la place si le "
                       "capitaine joue 0 minute, règle FPL exacte)"},
        {"key": "score_hors_capitaine",
         "definition": "même somme sans aucun doublement — isole la qualité de "
                       "la sélection de celle du choix de brassard"},
        {"key": "joueurs_zero_minute",
         "definition": "nombre de couples (joueur titularisé, GW) à 0 minute — "
                       "mesure directe du risque de minutes mal estimé"},
        {"key": "calibration_p60",
         "definition": "score de Brier de P(60+) figée contre l'indicatrice "
                       "réelle minutes >= 60, sur les 15 joueurs × 4 GW, plus "
                       "un tableau de fiabilité par tranches de 20 % ; c'est le "
                       "juge de niveau 1 du système (section 12 du dossier)"},
    ],
    "auto_subs": "NON simulés — limite assumée : le score réel FPL appliquerait "
                 "les remplacements automatiques, ce protocole ne les modélise "
                 "pas et sous-estime donc les deux effectifs de la même façon",
    "verdict_rule": (
        "aucun verdict de qualité ne peut être tiré d'un écart de score sur "
        "4 GW (bruit largement supérieur à l'écart attendu) ; la métrique "
        "décisive est la calibration de P(60+), puis le nombre de joueurs à "
        "0 minute. Le score cumulé est reporté, pas interprété seul."),
}




def _squad_payload(squad, gws, label, backend):
    return {
        "label": label,
        "players": [{"id": r["id"], "web_name": r["web_name"],
                     "element_type": r["element_type"], "team": r["team"],
                     "now_cost": r["now_cost"],
                     "p60": round(r["p60"], 4), "p_play": round(r["p_play"], 4),
                     "eps": {str(g): round(r["eps"][g], 4) for g in gws}}
                    for r in sorted(squad, key=lambda r: (r["element_type"], -r["ep4"]))],
        "legality": backend.legality(squad),
        "decisions_par_gw": backend.decisions(squad, gws),
        # Valeur selon la fonction de valeur PROPRE à cet effectif : les deux
        # nombres ne sont PAS comparables entre eux (unités différentes —
        # points projetés d'un côté, ep_next répété de l'autre). Seul le
        # protocole ci-dessous, exécuté sur résultats réels, les départage.
        "value4_selon_sa_propre_fonction": round(backend.value(squad, gws), 4),
        "avertissement_valeur": "non comparable à l'autre effectif ; voir protocole",
    }


def build_bench(contract, backend):
    """Construit les deux effectifs figés + le protocole. Déterministe."""
    gws = list(contract.horizon)
    internal_squad, _ = backend.select(contract.rows_for("central"), gws)
    base_rows, field, why = baseline_rows(contract)
    baseline_squad, _ = backend.select(base_rows, gws)

    ids_i = {r["id"] for r in internal_squad}
    ids_b = {r["id"] for r in baseline_squad}
    return {
        "snapshot": contract.snapshot,
        "synthetic": bool(contract.synthetic),
        "contract_version": contract.contract_version,
        "model_version": contract.model_version,
        "as_of": contract.as_of,
        "avertissement": (
            "DÉMO SYNTHÉTIQUE — ce banc d'essai ne vaut AUCUNE validation de "
            "qualité : il vérifie des invariants sur des données fabriquées."
            if contract.synthetic else
            "Banc d'essai sur snapshot réel — la comparaison n'est exécutable "
            "qu'après les 4 GW."),
        "horizon": gws,
        "baseline_field": field, "baseline_reason": why,
        "confiance_projections": contract.data_confidence,
        "confiance_pourquoi": contract.data_confidence_why,
        "sources": [{"key": r["key"], "present": r["present"], "detail": r["detail"]}
                    for r in contract.availability],
        "squads": {
            "interne": _squad_payload(internal_squad, gws,
                                      "projections internes sur l'horizon", backend),
            "baseline": _squad_payload(baseline_squad, gws,
                                       f"baseline publique ({field})", backend),
        },
        "recouvrement": len(ids_i & ids_b),
        # Verdict portant sur les PROJECTIONS seules (couverture, fallbacks,
        # priors plats). Le verdict complet — qui ajoute stabilité, budget et
        # plausibilité du capitaine — est rendu par le mode `initial-squad`.
        "verdict_qualite_projections": assess(contract, squad_ids=sorted(ids_i)).to_dict(),
        "protocole": COMPARISON_PROTOCOL,
    }


def write_bench(bench, data_dir="data"):
    out = Path(data_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"GW{bench['horizon'][0]}-banc-essai-initial.json"
    path.write_text(json.dumps(bench, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ------------------------------------------------------------- exécution ----

def _points(live_by_gw, gw, pid):
    stats = (live_by_gw.get(gw) or {}).get(pid) or {}
    return int(stats.get("total_points", 0) or 0)


def _minutes(live_by_gw, gw, pid):
    stats = (live_by_gw.get(gw) or {}).get(pid) or {}
    return int(stats.get("minutes", 0) or 0)


def score_frozen(bench, live_by_gw):
    """Exécute le protocole figé sur des résultats réels.

    `live_by_gw` : {gw: {element_id: {"total_points", "minutes"}}}. Retourne
    les quatre métriques par effectif. Aucune re-décision : on applique les
    choix figés, y compris quand ils se révèlent mauvais."""
    out = {}
    for key, sq in bench["squads"].items():
        p60 = {p["id"]: p["p60"] for p in sq["players"]}
        ids = list(p60)
        total = no_cap = zeros = 0
        brier_terms, bins = [], {}
        for gw_s, dec in sq["decisions_par_gw"].items():
            gw = int(gw_s)
            for pid in dec["xi"]:
                pts = _points(live_by_gw, gw, pid)
                total += pts
                no_cap += pts
                if _minutes(live_by_gw, gw, pid) == 0:
                    zeros += 1
            cap, vice = dec["captain"], dec["vice"]
            doubled = cap if _minutes(live_by_gw, gw, cap) > 0 else vice
            total += _points(live_by_gw, gw, doubled)
            for pid in ids:
                actual = 1.0 if _minutes(live_by_gw, gw, pid) >= 60 else 0.0
                pred = p60.get(pid, 0.0)
                brier_terms.append((pred - actual) ** 2)
                b = min(4, int(pred * 5))
                bins.setdefault(b, {"n": 0, "pred": 0.0, "obs": 0.0})
                bins[b]["n"] += 1
                bins[b]["pred"] += pred
                bins[b]["obs"] += actual
        reliability = [
            {"tranche": f"{20*b}–{20*(b+1)} %", "n": v["n"],
             "p60_moyenne_predite": round(v["pred"] / v["n"], 3),
             "frequence_observee": round(v["obs"] / v["n"], 3)}
            for b, v in sorted(bins.items())]
        out[key] = {
            "score_total": total,
            "score_hors_capitaine": no_cap,
            "joueurs_zero_minute": zeros,
            "calibration_p60": {
                "brier": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
                "n": len(brier_terms), "fiabilite": reliability},
        }
    return out
