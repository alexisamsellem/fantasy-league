# -*- coding: utf-8 -*-
"""Audit d'effectif comparatif — orchestration des trois couches.

Troisième mode, à côté de `initial.py` (acheter 15 joueurs) et `weekly.py`
(décider la semaine). Il répond à une question qu'aucun des deux ne pose : mon
effectif est-il encore celui que le moteur choisirait, et si non, de combien de
points cela me coûte-t-il sur quatre journées ?

    snapshot  →  forecasting  →  contrat  →  evaluation  →  optimization  →  rapport

Même frontière que le mode hebdomadaire : l'effectif détenu et la banque sont
des données PERSONNELLES, passées à part en identifiants, jamais versées au
contrat de projections. Le contrat figé par ce mode est donc rejouable et
publiable — il ne dit pas de qui est l'équipe.

Ce que l'audit N'EST PAS : un plan de transferts. Reconstruire de zéro suppose
quinze transferts simultanés, c'est-à-dire un wildcard. Le rapport le dit en
tête, et le chemin de transferts qui suit est là précisément pour montrer
quelle part de l'écart un transfert gratuit par semaine récupère réellement.
"""

from datetime import datetime, timezone

from . import wiring
from .evaluation import quality, stability
from .forecasting import build_projection_set
from .optimization import audit as opt_audit
from .optimization import initial as opt_initial
from .weekly import pending_transfers, read_squad

AUDIT_HORIZON_GWS = opt_audit.AUDIT_HORIZON_GWS   # 4 GW
PATH_WEEKS = opt_audit.PATH_WEEKS                 # 4 transferts gratuits


def build_contract(parsed):
    """Étape 1 : snapshot → contrat de projections sur l'horizon de l'audit.

    Quatre GW et non trois : on compare deux effectifs STATIQUES, comme le mode
    effectif initial. Trois journées mesureraient l'écart d'une semaine, pas
    celui d'une équipe."""
    gw = parsed["next_gw"]
    if gw is None:
        raise SystemExit("Aucune GW future dans le calendrier : saison terminée ?")
    gws = list(range(gw, min(gw + AUDIT_HORIZON_GWS, 39)))
    return build_projection_set(parsed, gws)


def build_from_contract(contract, squad_ids, bank, now=None, weeks=PATH_WEEKS,
                        already_transferred=None, pick_gw=None):
    """Étapes 2 à 4 : reconstruction, écart, chemin, verdict.

    N'accède à AUCUNE donnée brute. `now` est explicite pour que le verdict
    reste reproductible."""
    now = now or datetime.now(timezone.utc)
    gws = list(contract.horizon)
    rows = contract.rows_for("central")

    res = opt_audit.audit(rows, squad_ids, bank, gws, weeks)

    # Stabilité de l'effectif RECONSTRUIT : le budget de l'audit est celui du
    # manager, il doit être lié au backend avant de rejouer les scénarios.
    backend = wiring.selection_backend(res["budget"])
    rebuilt_ids = [r["id"] for r in res["rebuilt"]]
    scenarios, min_overlap = stability.top15_stability(
        contract, backend, rebuilt_ids, [r["id"] for r in opt_initial.build_pool(rows)])

    facts = dict(opt_initial.legality(res["rebuilt"], res["budget"]))
    facts.update({
        "min_overlap": min_overlap,
        "rebuilt_ids": rebuilt_ids,
        "squad_size": len(res["owned"]),
        "missing_ids": res["missing_ids"],
        "missing_names": [contract.players.get(str(pid), {}).get("web_name", f"#{pid}")
                          for pid in res["missing_ids"]],
        "already_transferred": len(already_transferred or []),
        "pick_gw": pick_gw,
    })
    verdict = quality.assess_audit(contract, facts, now=now)

    # Lignes d'affichage : mêmes joueurs, même ordre, sans rejouer la décision.
    gw = contract.gw
    besoin = list(dict.fromkeys(
        [r["id"] for r in res["owned"]] + rebuilt_ids
        + [e["out"]["id"] for e in (res["chemin"] or {}).get("etapes", [])]
        + [e["in"]["id"] for e in (res["chemin"] or {}).get("etapes", [])]))
    display = {r["id"]: r for r in contract.display_rows(besoin, gw)}

    def shown(rows_):
        return [display[r["id"]] for r in rows_ if r["id"] in display]

    div = res["divergence"]
    chemin = res["chemin"]
    if chemin:
        chemin = dict(chemin, etapes=[
            dict(e, out=display[e["out"]["id"]], in_=display[e["in"]["id"]])
            for e in chemin["etapes"]])

    return {
        "mode": "audit d'effectif",
        "gw": gw, "deadline": contract.deadline, "horizon": gws,
        "owned": shown(res["owned"]), "rebuilt": shown(res["rebuilt"]),
        "missing_ids": res["missing_ids"], "missing_names": facts["missing_names"],
        "bank": res["bank"], "budget": res["budget"],
        "budget_initial": res["budget_initial"],
        "cout_detenu": res["cout_detenu"], "cout_ideal": res["cout_ideal"],
        "valeur_detenue": res["valeur_detenue"], "valeur_ideale": res["valeur_ideale"],
        "retard": res["retard"], "part_rattrapee": res["part_rattrapee"],
        "recouvrement": div["recouvrement"],
        "detenus_ecartes": shown(div["detenus_ecartes"]),
        "retenus_non_detenus": shown(div["retenus_non_detenus"]),
        "par_poste": {et: {
            "communs": v["communs"],
            "detenus_ecartes": shown(v["detenus_ecartes"]),
            "retenus_non_detenus": shown(v["retenus_non_detenus"]),
        } for et, v in div["par_poste"].items()},
        "chemin": chemin, "semaines": weeks,
        "scenarios": scenarios, "min_overlap": min_overlap,
        "legality": {k: facts[k] for k in
                     ("cost", "budget", "budget_ok", "quota", "quota_ok",
                      "max_per_club", "club_ok", "size", "size_ok")},
        "pick_gw": pick_gw, "already_transferred": list(already_transferred or []),
        "verdict": verdict,
        "as_of": contract.as_of, "now": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "contract_version": contract.contract_version,
        "model_version": contract.model_version,
        "availability": contract.availability,
        "confidence": contract.data_confidence,
        "confidence_why": contract.data_confidence_why,
        "team_factor_source": contract.team_factor_source,
        "teams": {int(k): v for k, v in contract.teams.items()},
        "run_dir": contract.snapshot,
        "synthetic": contract.synthetic,
        "n_history_gws": contract.n_history_gws,
    }


def build_audit(parsed, now=None, freeze_to=None, weeks=PATH_WEEKS):
    """Snapshot → audit complet. `freeze_to` écrit le contrat de projections :
    trace auditable, sans aucune donnée personnelle."""
    squad_ids, bank = read_squad(parsed)
    contract = build_contract(parsed)
    frozen = contract.save(freeze_to) if freeze_to else None
    res = build_from_contract(
        contract, squad_ids, bank, now=now, weeks=weeks,
        already_transferred=pending_transfers(parsed, contract.gw),
        pick_gw=parsed.get("last_closed_gw"))
    res["frozen_projections"] = str(frozen) if frozen else None
    return res
