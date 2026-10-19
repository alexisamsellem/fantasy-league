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

from dataclasses import replace
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


def free_transfers(parsed):
    """Transferts gratuits disponibles pour la prochaine GW, reconstitués
    depuis l'historique public du manager (`entry/{id}/history`).

    Règle FPL depuis 2024/25 [F◦] : un gratuit pour la GW2, puis +1 par GW,
    plafond 5 ; un transfert payé ne consomme rien de plus ; Wildcard et Free
    Hit ne consomment pas les gratuits [H : le +1 de la GW est supposé
    acquis aussi]. Sans historique lisible : 1, l'hypothèse historique."""
    hist = (parsed.get("my") or {}).get("history") or {}
    cur = sorted(hist.get("current") or [], key=lambda h: h["event"])
    if not cur:
        return 1, "historique illisible — 1 gratuit supposé [H]"
    chips = {c.get("event"): c.get("name") for c in hist.get("chips") or []}
    ft = None
    for h in cur:
        g = h["event"]
        if g == 1 or ft is None:
            ft = 1                       # le gratuit de la GW suivante
            continue
        n = h.get("event_transfers") or 0
        if chips.get(g) in ("wildcard", "freehit"):
            n = 0
        ft = min(5, max(0, ft - n) + 1)
    return ft, f"reconstitué sur {len(cur)} GW d'historique public"


def build_from_contract(contract, squad_ids, bank, backend=None, now=None,
                        already_transferred=None, pick_gw=None, gratuits=1):
    """Étapes 2 à 4 : décision, évaluation, mise en forme.

    N'accède à AUCUNE donnée brute : tout vient du contrat et des identifiants
    de l'effectif. `now` est explicite pour que le verdict reste reproductible.
    """
    backend = backend or wiring.selection_backend()
    if backend.weekly is not None and gratuits != 1:
        inner = backend.weekly
        backend = replace(backend, weekly=lambda *a, **k: inner(
            *a, **dict(k, free_transfers=gratuits)))
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
    # L'entrant du transfert recommandé n'est pas dans l'effectif : il doit
    # quand même être affichable, sinon le XI d'après-transfert ne peut pas
    # être montré.
    apres = central.get("apres_transfert")
    besoin = list(read_ids)
    if apres:
        besoin += [e[1]["id"] for e in apres.get("echanges", [(None, apres["in"])])]
    display = {r["id"]: r for r in contract.display_rows(besoin, gw)}

    def shown(rows):
        return [display[r["id"]] for r in rows]

    band = dict(band, captain=display[band["captain"]["id"]],
                vice=display[band["vice"]["id"]],
                alternatives=[dict(a, captain=display[a["captain"]["id"]],
                                   vice=display[a["vice"]["id"]])
                              for a in band["alternatives"]])
    if apres:
        b = apres["armband"]
        apres = dict(
            apres, xi=shown(apres["xi"]), bench=shown(apres["bench"]),
            out=display.get(apres["out"]["id"], apres["out"]),
            **{"in": display[apres["in"]["id"]]},
            armband=dict(b, captain=display[b["captain"]["id"]],
                         vice=display[b["vice"]["id"]]),
            echanges=[(display.get(o["id"], o), display[i["id"]])
                      for o, i in apres.get("echanges", [])],
            xi_in=[display[i] for i in apres["xi_in"]],
            xi_out=[display[i] for i in apres["xi_out"]])
    return {
        "mode": "hebdomadaire",
        "gw": gw, "deadline": contract.deadline, "horizon": gws,
        "squad": [display[pid] for pid in read_ids],
        "xi": shown(central["xi"]), "bench": shown(central["bench"]),
        "armband": band,
        "apres_transfert": apres,
        "transfer": dict(central["transfer"], noms={
            p: contract.players.get(str(p), {}).get("web_name", f"#{p}")
            for e in (central["transfer"].get("plan") or {}).values()
            for p in e["achats"] + e["ventes"]}),
        "bank": bank, "gratuits": gratuits,
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
