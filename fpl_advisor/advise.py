# -*- coding: utf-8 -*-
"""Orchestration : parsed → recommandation complète pour la prochaine GW."""

from . import model, team
from .rivals import local_exposure, standings_summary

MARKET_PER_POSITION = 15   # présélection du marché pour le scan de transfert


def _player_row(parsed, p, gw, teams, means):
    proj = model.project_player(parsed, p, gw, teams, means)
    forced = {"p_play": 1.0, "p60": 1.0, "p_cameo": 0.0, "p0": 0.0,
              "xmin": 90.0, "basis": "forcé titulaire", "avail": 1.0}
    if_start = model.project_player(parsed, p, gw, teams, means, minutes=forced)
    m = proj["minutes"]
    return {
        "id": p["id"], "web_name": p.get("web_name", f"#{p['id']}"),
        "element_type": p["element_type"], "team": p["team"],
        "now_cost": p["now_cost"],
        "ep": proj["ep"], "ep_if_start": if_start["ep"],
        "p_play": m["p_play"], "p60": m["p60"], "p0": m["p0"],
        "minutes_basis": m["basis"], "rate_basis": proj.get("rate_basis", ""),
        "defcon_basis": proj.get("defcon_basis", ""),
        "components": proj["components"], "n_fixtures": proj["n_fixtures"],
        "status": p.get("status", "a"),
        "news": p.get("news") or "",
    }


def build_recommendation(parsed):
    boot = parsed["bootstrap"]
    elements = {e["id"]: e for e in boot["elements"]}
    teams_by_id, means = model.team_strengths(boot)
    gw = parsed["next_gw"]
    if gw is None:
        raise SystemExit("Aucune GW future dans le calendrier : saison terminée ?")
    if not parsed.get("my", {}).get("picks"):
        raise SystemExit(
            "BLOCAGE FACTUEL : l'effectif de l'équipe n'est pas lisible — les picks "
            "publics n'existent qu'après la première deadline passée. Relancer "
            "après la clôture de la GW en cours.")

    horizon = [g for g in range(gw, min(gw + team.HORIZON_GWS, 39))]

    # Effectif
    my_picks = parsed["my"]["picks"]
    squad = [_player_row(parsed, elements[pk["element"]], gw, teams_by_id, means)
             for pk in my_picks["picks"]]

    # Marché : EP prochaine GW pour tous, présélection par poste
    market_rows = []
    for p in boot["elements"]:
        if p["id"] in {s["id"] for s in squad}:
            continue
        if p.get("status") in ("u",):     # parti du championnat
            continue
        market_rows.append(_player_row(parsed, p, gw, teams_by_id, means))
    market_rows.sort(key=lambda r: -r["ep"])
    shortlist = []
    for et in (1, 2, 3, 4):
        shortlist.extend([r for r in market_rows if r["element_type"] == et][:MARKET_PER_POSITION])

    # Projections d'horizon (3 GW) pour effectif + présélection
    horizon_eps = {}
    for row in squad + shortlist:
        horizon_eps[row["id"]] = model.project_horizon(
            parsed, elements[row["id"]], horizon, teams_by_id, means)

    # XI, banc, brassard
    xi, bench = team.pick_xi(squad)
    band = team.armband(xi)

    # Transfert vs conservation
    bank = (my_picks.get("entry_history") or {}).get("bank", 0) or 0
    transfer = team.transfer_scan(squad, shortlist, horizon_eps, bank)

    # Rivaux (post-deadline uniquement)
    exposure, expo_meta = local_exposure(parsed)
    standings = standings_summary(parsed)

    deadline = next((e.get("deadline_time") for e in parsed["events"]
                     if e["id"] == gw), None)

    return {
        "gw": gw, "deadline": deadline, "horizon": horizon,
        "squad": squad, "xi": xi, "bench": bench, "armband": band,
        "transfer": transfer, "bank": bank,
        "horizon_eps": horizon_eps,
        "exposure": exposure, "exposure_meta": expo_meta,
        "standings": standings,
        "teams": {t["id"]: t.get("short_name", str(t["id"]))
                  for t in boot.get("teams", [])},
        "run_dir": parsed.get("run_dir", "(démo)"),
        "n_history_gws": len(parsed.get("live", {})),
    }
