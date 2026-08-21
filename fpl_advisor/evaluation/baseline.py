# -*- coding: utf-8 -*-
"""Baseline publique : ce qu'un repère naïf et gratuit aurait choisi.

Les valeurs publiques (`ep_next`, `selected_by_percent`) voyagent dans le
contrat de projections, comme repères connus à la date de décision. Ce module
n'ouvre donc jamais le snapshot.
"""

BASELINE_PRIMARY = "ep_next"
BASELINE_FALLBACK = "selected_by_percent"


def _float(v):
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def baseline_field(contract):
    """(champ retenu, raison) — décidé par disponibilité, pas par résultat."""
    metas = contract.players.values()
    if any(_float(m.get(BASELINE_PRIMARY)) > 0 for m in metas):
        return BASELINE_PRIMARY, "champ officiel FPL ep_next présent"
    if any(_float(m.get(BASELINE_FALLBACK)) > 0 for m in metas):
        return (BASELINE_FALLBACK,
                "ep_next absent ou nul → repli public déterministe défini à "
                "l'avance : selected_by_percent")
    return None, ("ni ep_next ni selected_by_percent exploitables — "
                  "comparaison impossible sur ce snapshot")


def baseline_rows(contract):
    """Lignes de la baseline : la valeur publique est répétée à l'identique sur
    les 4 GW (le champ ep_next ne porte que la GW suivante — la baseline est
    volontairement naïve, c'est ce qui en fait une baseline)."""
    field, why = baseline_field(contract)
    if field is None:
        raise SystemExit(f"BLOCAGE BASELINE : {why}")
    gws = list(contract.horizon)
    rows = []
    for r in contract.rows_for("central"):
        val = _float(contract.players[str(r["id"])].get(field))
        rows.append(dict(r, eps={gw: val for gw in gws}, ep4=val * len(gws)))
    return rows, field, why
