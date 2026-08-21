# -*- coding: utf-8 -*-
"""Test d'acceptation : projections internes contre baseline publique.

Deux effectifs légaux construits DEPUIS LE MÊME SNAPSHOT, avec le MÊME
optimiseur, la seule différence étant la fonction de valeur :

  A. `interne`  : EP cumulée GW1→GW4 de la couche de projection du dépôt.
  B. `baseline` : champ public officiel `ep_next` (FPL). Repli déterministe
     défini À L'AVANCE si `ep_next` est absent ou nul : `selected_by_percent`
     (sagesse de la foule, publique, sans modèle). Si aucun des deux n'est
     exploitable, on ARRÊTE — on ne bricole pas une troisième baseline après
     avoir vu les résultats.

Utiliser le même optimiseur des deux côtés est délibéré : ce qui est comparé,
ce sont les PROJECTIONS, pas la recherche combinatoire.

Le protocole de comparaison est figé ici, avant toute observation de résultats
(COMPARISON_PROTOCOL). `freeze()` écrit les deux effectifs et les décisions par
GW ; `score_frozen()` exécute la comparaison une fois les GW jouées. Rien dans
ce module ne prétend qu'un effectif est meilleur : il rend la comparaison
exécutable et falsifiable.
"""

import json
from pathlib import Path

from . import initial, model, priors, team

BASELINE_PRIMARY = "ep_next"
BASELINE_FALLBACK = "selected_by_percent"

# Protocole figé AVANT observation des résultats. Toute modification après coup
# invalide la comparaison et doit être datée explicitement.
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


def _float(v):
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def baseline_field(parsed):
    """(champ retenu, raison) — décidé par disponibilité, pas par résultat."""
    elements = parsed["bootstrap"]["elements"]
    if any(_float(e.get(BASELINE_PRIMARY)) > 0 for e in elements):
        return BASELINE_PRIMARY, "champ officiel FPL ep_next présent"
    if any(_float(e.get(BASELINE_FALLBACK)) > 0 for e in elements):
        return (BASELINE_FALLBACK,
                "ep_next absent ou nul → repli public déterministe défini à "
                "l'avance : selected_by_percent")
    return None, ("ni ep_next ni selected_by_percent exploitables — "
                  "comparaison impossible sur ce snapshot")


def baseline_rows(parsed, gws):
    """Lignes de la baseline publique : la valeur publique est répétée à
    l'identique sur les 4 GW (le champ ep_next ne porte que la GW suivante —
    la baseline est volontairement naïve, c'est ce qui en fait une baseline)."""
    field, why = baseline_field(parsed)
    if field is None:
        raise SystemExit(f"BLOCAGE BASELINE : {why}")
    rows = []
    for p in parsed["bootstrap"]["elements"]:
        if p.get("status") == "u":
            continue
        val = _float(p.get(field))
        hist, _ = model.appearance_history(parsed, p["id"])
        minutes = model.minutes_model(p, hist, parsed=parsed)
        rows.append({
            "id": p["id"], "web_name": p.get("web_name", f"#{p['id']}"),
            "element_type": p["element_type"], "team": p["team"],
            "now_cost": p["now_cost"],
            "p_play": minutes["p_play"], "p60": minutes["p60"],
            "p0": minutes["p0"],
            "eps": {gw: val for gw in gws}, "ep4": val * len(gws),
        })
    return rows, field, why


def _pool_from_rows(rows):
    """Même règle de présélection que le mode initial, appliquée à la baseline."""
    pool, seen = [], set()
    for et in (1, 2, 3, 4):
        of_type = [r for r in rows if r["element_type"] == et]
        top = sorted(of_type, key=lambda r: -r["ep4"])[:initial.POOL_TOP]
        cheap = sorted(of_type, key=lambda r: (r["now_cost"], -r["ep4"]))[:initial.POOL_CHEAP]
        for r in top + cheap:
            if r["id"] not in seen:
                seen.add(r["id"])
                pool.append(r)
    return pool


def _decisions(squad, gws):
    """XI, banc et brassard figés pour chaque GW de l'horizon."""
    out = {}
    for gw in gws:
        rows = [dict(r, ep=r["eps"][gw]) for r in squad]
        xi, bench = team.pick_xi(rows)
        band = team.armband(xi)
        out[str(gw)] = {
            "xi": [p["id"] for p in xi],
            "bench": [p["id"] for p in bench],
            "captain": band["captain"]["id"],
            "vice": band["vice"]["id"],
        }
    return out


def _legality(squad):
    clubs = {}
    for r in squad:
        clubs[r["team"]] = clubs.get(r["team"], 0) + 1
    quota = {et: sum(1 for r in squad if r["element_type"] == et) for et in (1, 2, 3, 4)}
    cost = sum(r["now_cost"] for r in squad)
    return {
        "cost": cost, "budget": initial.BUDGET, "budget_ok": cost <= initial.BUDGET,
        "quota": quota, "quota_ok": quota == initial.SQUAD_QUOTA,
        "max_per_club": max(clubs.values()) if clubs else 0,
        "club_ok": (max(clubs.values()) if clubs else 0) <= initial.MAX_PER_CLUB,
        "size": len(squad), "size_ok": len(squad) == 15,
    }


def _squad_payload(squad, gws, label):
    return {
        "label": label,
        "players": [{"id": r["id"], "web_name": r["web_name"],
                     "element_type": r["element_type"], "team": r["team"],
                     "now_cost": r["now_cost"],
                     "p60": round(r["p60"], 4), "p_play": round(r["p_play"], 4),
                     "eps": {str(g): round(r["eps"][g], 4) for g in gws}}
                    for r in sorted(squad, key=lambda r: (r["element_type"], -r["ep4"]))],
        "legality": _legality(squad),
        "decisions_par_gw": _decisions(squad, gws),
        # Valeur selon la fonction de valeur PROPRE à cet effectif : les deux
        # nombres ne sont PAS comparables entre eux (unités différentes —
        # points projetés d'un côté, ep_next répété de l'autre). Seul le
        # protocole ci-dessous, exécuté sur résultats réels, les départage.
        "value4_selon_sa_propre_fonction": round(initial.squad_value(squad, gws), 4),
        "avertissement_valeur": "non comparable à l'autre effectif ; voir protocole",
    }


def build_bench(parsed):
    """Construit les deux effectifs figés + le protocole. Déterministe."""
    gw = parsed["next_gw"]
    if gw is None:
        raise SystemExit("Aucune GW future : impossible de figer un banc d'essai.")
    gws = list(range(gw, min(gw + initial.INITIAL_HORIZON_GWS, 39)))

    internal_pool = initial.build_pool(parsed, gws)
    internal_squad, _ = initial.optimize_squad(internal_pool, gws)

    base_rows, field, why = baseline_rows(parsed, gws)
    baseline_squad, _ = initial.optimize_squad(_pool_from_rows(base_rows), gws)

    ids_i = {r["id"] for r in internal_squad}
    ids_b = {r["id"] for r in baseline_squad}
    avail = priors.availability_report(parsed)
    confidence, why_conf = priors.confidence_level(avail)

    return {
        "snapshot": parsed.get("run_dir", ""),
        "synthetic": bool(parsed.get("synthetic")),
        "avertissement": (
            "DÉMO SYNTHÉTIQUE — ce banc d'essai ne vaut AUCUNE validation de "
            "qualité : il vérifie des invariants sur des données fabriquées."
            if parsed.get("synthetic") else
            "Banc d'essai sur snapshot réel — la comparaison n'est exécutable "
            "qu'après les 4 GW."),
        "horizon": gws,
        "baseline_field": field, "baseline_reason": why,
        "confiance_projections": confidence, "confiance_pourquoi": why_conf,
        "sources": [{"key": r["key"], "present": r["present"], "detail": r["detail"]}
                    for r in avail],
        "squads": {
            "interne": _squad_payload(internal_squad, gws, "projections internes GW1→GW4"),
            "baseline": _squad_payload(baseline_squad, gws, f"baseline publique ({field})"),
        },
        "recouvrement": len(ids_i & ids_b),
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
