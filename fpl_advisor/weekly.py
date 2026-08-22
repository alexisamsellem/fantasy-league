# -*- coding: utf-8 -*-
"""Mode hebdomadaire — orchestration des trois couches.

Jumeau de `initial.py` pour la décision de la semaine. Même ordre imposé, même
frontière :

    snapshot  →  forecasting  →  contrat  →  evaluation  →  optimization  →  rapport

Ce qui change par rapport au mode effectif initial :

- l'effectif n'est pas à construire, il est détenu. Ce qu'on décide, c'est le
  brassard, le XI et l'arbitrage transférer/conserver ;
- l'effectif détenu est une donnée PERSONNELLE : il n'entre jamais dans le
  contrat de projections, qui reste public et sérialisable. Il est passé à part,
  en simples identifiants ;
- la fraîcheur de la collecte et la deadline deviennent des critères de
  publication : à la semaine, une recommandation périmée n'est pas une
  recommandation.
"""

from datetime import datetime, timezone

from . import wiring
from .evaluation import quality, stability
from .forecasting import build_projection_set
from .optimization.transfers import HORIZON_GWS

WEEKLY_HORIZON_GWS = HORIZON_GWS      # 3 GW : horizon de l'arbitrage de transfert


def build_contract(parsed):
    """Étape 1 : snapshot → contrat de projections (couche forecasting)."""
    gw = parsed["next_gw"]
    if gw is None:
        raise SystemExit("Aucune GW future dans le calendrier : saison terminée ?")
    gws = list(range(gw, min(gw + WEEKLY_HORIZON_GWS, 39)))
    return build_projection_set(parsed, gws)


def read_squad(parsed):
    """Effectif détenu → (identifiants dans l'ordre des picks, banque).

    Lève un blocage factuel explicite quand les picks n'existent pas : ils ne
    sont publics qu'après la première deadline passée."""
    picks = (parsed.get("my") or {}).get("picks")
    if not picks or not picks.get("picks"):
        raise SystemExit(
            "BLOCAGE FACTUEL : l'effectif de l'équipe n'est pas lisible — les picks "
            "publics n'existent qu'après la première deadline passée. Relancer "
            "après la clôture de la GW en cours.")
    ids = [pk["element"] for pk in picks["picks"]]
    bank = (picks.get("entry_history") or {}).get("bank", 0) or 0
    return ids, bank


def pending_transfers(parsed, gw):
    """Transferts déjà effectués pour la GW à venir, d'après `entry/transfers`.

    L'API publique ne rend l'effectif que de la DERNIÈRE GW CLOSE. Si le
    manager a déjà transféré pour la GW suivante, les picks lus sont périmés :
    le XI, le brassard et l'arbitrage porteraient sur une équipe qui n'existe
    plus. Le fait est mesurable, donc il est mesuré."""
    faits = (parsed.get("my") or {}).get("transfers") or []
    return [t for t in faits if t.get("event") == gw]


def build_from_contract(contract, squad_ids, bank, backend=None, now=None,
                        already_transferred=None, pick_gw=None):
    """Étapes 2 à 4 : décision, évaluation, mise en forme.

    N'accède à AUCUNE donnée brute : tout vient du contrat et des identifiants
    de l'effectif. `now` est explicite pour que le verdict reste reproductible.
    """
    backend = backend or wiring.selection_backend()
    now = now or datetime.now(timezone.utc)
    gws = list(contract.horizon)
    gw = contract.gw

    # --- optimisation (scénario central)
    central = backend.weekly(contract.rows_for("central"), squad_ids, bank, gws)

    # --- évaluation : les décisions tiennent-elles sous les autres scénarios ?
    scenarios, agreement = stability.decision_stability(
        contract, backend, squad_ids, bank)

    band = central["armband"]
    read_ids = [p["id"] for p in central["squad"]]
    missing = central["missing_ids"]
    facts = dict(agreement)
    facts.update({
        "squad_size": len(read_ids),
        "missing_ids": missing,
        "missing_names": [contract.players.get(str(pid), {}).get("web_name", f"#{pid}")
                          for pid in missing],
        "captain_p60": band["captain"]["p60"],
        "captain_name": band["captain"]["web_name"],
        "already_transferred": len(already_transferred or []),
        "pick_gw": pick_gw,
    })
    verdict = quality.assess_weekly(contract, facts, now=now)

    # Les lignes d'affichage portent ce que le rapport montre (EP si 90',
    # provenance des taux, statut, nouvelles) ; les lignes de décision ne
    # portent que ce dont l'optimiseur a besoin. On rattache les premières aux
    # secondes sans rejouer la décision : mêmes joueurs, même ordre.
    display = {r["id"]: r for r in contract.display_rows(read_ids, gw)}

    def shown(rows):
        return [display[r["id"]] for r in rows]

    band = dict(band, captain=display[band["captain"]["id"]],
                vice=display[band["vice"]["id"]],
                alternatives=[dict(a, captain=display[a["captain"]["id"]],
                                   vice=display[a["vice"]["id"]])
                              for a in band["alternatives"]])
    return {
        "mode": "hebdomadaire",
        "gw": gw, "deadline": contract.deadline, "horizon": gws,
        "squad": [display[pid] for pid in read_ids],
        "xi": shown(central["xi"]), "bench": shown(central["bench"]),
        "armband": band,
        "transfer": central["transfer"], "bank": bank,
        "horizon_eps": central["horizon_eps"], "market_size": central["market_size"],
        "missing_ids": missing, "missing_names": facts["missing_names"],
        "pick_gw": pick_gw, "already_transferred": list(already_transferred or []),
        "scenarios": scenarios, "agreement": agreement,
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
        # Rempli par l'orchestrateur : données personnelles hors contrat.
        "exposure": [], "exposure_meta": {}, "standings": {},
    }
