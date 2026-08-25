# -*- coding: utf-8 -*-
"""Contrat de projections — la frontière figée entre prévoir et décider.

C'est le SEUL objet que l'évaluation et l'optimisation ont le droit de lire.
Ni l'une ni l'autre ne touche au snapshot, au bootstrap ou aux fonctions
internes du moteur de prévision. Conséquences pratiques :

- on peut remplacer entièrement le moteur de prévision sans toucher à
  l'optimiseur, tant que le contrat est respecté ;
- on peut figer un fichier de projections, le relire des jours plus tard et
  reconstruire exactement le même effectif sans recalculer quoi que ce soit ;
- on sait toujours d'où vient un chiffre : chaque ligne porte sa provenance,
  sa confiance, sa date de connaissance et la version du modèle.

Le contrat est volontairement une structure plate et sérialisable en JSON :
pas d'objet vivant, pas de référence au snapshot, aucune fonction embarquée.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import priors
from .minutes import appearance_history, minutes_model
from .projection import project_horizon, project_player
from .teams import team_factors

CONTRACT_VERSION = "1.0"
MODEL_VERSION = "forecasting/0.3.1"

# Minutes forcées servant à isoler le risque de titularisation (colonne
# « EP si 90' » du rapport) : ce n'est pas une prévision, c'est un contrefactuel.
FORCED_START = {"p_play": 1.0, "p60": 1.0, "p_cameo": 0.0, "p0": 0.0,
                "xmin": 90.0, "basis": "forcé titulaire", "avail": 1.0,
                "confidence": "n/a", "n_gw": 0,
                "n_starts_obs": 0, "n_apps_obs": 0}


@dataclass
class PlayerProjection:
    """Une prévision, pour un joueur et une Gameweek."""
    player_id: int
    gw: int
    ep: float                     # points espérés, scénario central
    ep_if_start: float            # contrefactuel : si titulaire 90 minutes
    p0: float                     # probabilité de zéro minute
    p60: float                    # probabilité de jouer au moins 60 minutes
    p_play: float
    n_fixtures: int
    components: dict              # appearance, goals, assists, cs, saves, defcon, bonus, malus
    scenarios: dict               # {"prudent": ep, "central": ep, "favorable": ep}
    confidence: str               # faible | moyenne | n/a
    provenance: dict              # base des minutes, des taux, du DEFCON


@dataclass
class ProjectionSet:
    """Toutes les prévisions d'un snapshot, plus ce qu'il faut pour les juger."""
    contract_version: str
    model_version: str
    as_of: str                    # date de connaissance des données
    horizon: list
    gw: int                       # première GW de l'horizon (GW de décision)
    deadline: str                 # deadline officielle de cette GW
    n_history_gws: int            # profondeur d'historique de minutes disponible
    snapshot: str
    synthetic: bool
    availability: list            # provenance des données (contrat de données)
    data_confidence: str
    data_confidence_why: str
    team_factor_source: str
    scenario_names: list
    scenarios_meta: dict          # nom -> {label, note} : lisible sans priors
    players: dict                 # id (str) -> métadonnées joueur
    teams: dict                   # id (str) -> nom court du club
    rows: list = field(default_factory=list)

    # ------------------------------------------------------------ lecture ----

    def player_ids(self):
        return sorted({r.player_id for r in self.rows})

    def meta(self, player_id):
        return self.players[str(player_id)]

    def rows_for(self, scenario="central"):
        """Vue « optimiseur » : une ligne par joueur, EP par GW sous ce scénario.

        C'est la seule forme que l'optimisation consomme. Elle ne contient
        aucune donnée brute d'API et aucun moyen de recalculer une prévision."""
        by_player = {}
        for r in self.rows:
            m = self.players[str(r.player_id)]
            row = by_player.setdefault(r.player_id, {
                "id": r.player_id, "web_name": m["web_name"],
                "element_type": m["element_type"], "team": m["team"],
                "now_cost": m["now_cost"],
                "p_play": r.p_play, "p60": r.p60, "p0": r.p0,
                "minutes_basis": r.provenance.get("minutes", ""),
                "minutes_confidence": r.confidence,
                "eps": {}, "ep_by_gw": {}, "ep_if_start_by_gw": {},
                "components_by_gw": {},
            })
            row["eps"][r.gw] = r.scenarios[scenario]
            row["ep_by_gw"][r.gw] = r.ep
            row["ep_if_start_by_gw"][r.gw] = r.ep_if_start
            row["components_by_gw"][r.gw] = r.components
        for row in by_player.values():
            row["ep4"] = sum(row["eps"].values())
        return [by_player[pid] for pid in sorted(by_player)]

    def display_rows(self, player_ids, gw):
        """Lignes d'affichage du rapport pour une GW.

        L'ordre de `player_ids` est conservé tel quel : le tri des tables est
        décidé par le rapport, et certains départages (XI, banc) dépendent de
        l'ordre d'entrée sur égalité stricte."""
        order = {pid: i for i, pid in enumerate(player_ids)}
        out = []
        for row in self.rows_for("central"):
            if row["id"] not in order:
                continue
            m = self.players[str(row["id"])]
            r = next(r for r in self.rows if r.player_id == row["id"] and r.gw == gw)
            out.append({
                "id": row["id"], "web_name": row["web_name"],
                "element_type": row["element_type"], "team": row["team"],
                "now_cost": row["now_cost"],
                "ep": r.ep, "ep_if_start": r.ep_if_start,
                "p_play": r.p_play, "p60": r.p60, "p0": r.p0,
                "minutes_basis": r.provenance.get("minutes", ""),
                "minutes_observed": r.provenance.get("minutes_observed") or {},
                "minutes_confidence": r.confidence,
                "rate_basis": r.provenance.get("rates", ""),
                "defcon_basis": r.provenance.get("defcon", ""),
                "components": r.components, "n_fixtures": r.n_fixtures,
                "status": m.get("status", "a"), "news": m.get("news", ""),
                "eps": row["eps"], "ep4": row["ep4"],
            })
        out.sort(key=lambda r: order[r["id"]])
        return out

    # ------------------------------------------------- sérialisation JSON ----

    def to_dict(self):
        d = asdict(self)
        d["rows"] = [asdict(r) if not isinstance(r, dict) else r for r in self.rows]
        return d

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        rows = [PlayerProjection(**r) for r in d.pop("rows", [])]
        obj = cls(**d, rows=rows)
        # Les clés de GW repassent en entiers après un aller-retour JSON.
        for r in obj.rows:
            r.gw = int(r.gw)
        obj.horizon = [int(g) for g in obj.horizon]
        return obj

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1, ensure_ascii=False),
                        encoding="utf-8")
        return path

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ----------------------------------------------------------- construction ----

def build_projection_set(parsed, gws, as_of=None):
    """Snapshot → contrat de projections. Seul point d'entrée du forecasting.

    Calcule, pour chaque joueur sélectionnable et chaque GW de l'horizon, les
    trois scénarios, le contrefactuel « si titulaire » et la provenance."""
    boot = parsed["bootstrap"]
    availability = priors.availability_report(parsed)
    blocking = priors.missing_required(availability)
    if blocking:
        raise SystemExit(
            "BLOCAGE DONNÉES : source obligatoire absente — "
            + " ; ".join(f"{b['key']} ({b['source']})" for b in blocking))
    conf, why = priors.confidence_level(availability)
    factors = team_factors(parsed)

    players, rows = {}, []
    for p in boot["elements"]:
        if p.get("status") == "u":            # parti du championnat
            continue
        pid = p["id"]
        players[str(pid)] = {
            "web_name": p.get("web_name", f"#{pid}"),
            "element_type": p["element_type"], "team": p["team"],
            "now_cost": p["now_cost"], "status": p.get("status", "a"),
            "news": p.get("news") or "",
            # Repères publics externes, connus à la date de décision : ils
            # servent de baseline à `evaluation`, qui n'a ainsi jamais besoin
            # de rouvrir le snapshot.
            "ep_next": p.get("ep_next"),
            "selected_by_percent": p.get("selected_by_percent"),
        }
        hist, _ = appearance_history(parsed, pid)
        per_scenario = {}
        for name in priors.SCENARIO_ORDER:
            sc = priors.params(name)
            per_scenario[name] = project_horizon(parsed, p, gws, scenario=sc)
        minutes = minutes_model(p, hist, parsed=parsed)
        for gw in gws:
            central = project_player(parsed, p, gw, minutes=minutes)
            forced = project_player(parsed, p, gw, minutes=FORCED_START)
            rows.append(PlayerProjection(
                player_id=pid, gw=gw,
                ep=central["ep"], ep_if_start=forced["ep"],
                p0=minutes["p0"], p60=minutes["p60"], p_play=minutes["p_play"],
                n_fixtures=central["n_fixtures"],
                components=central["components"],
                scenarios={n: per_scenario[n][gw] for n in priors.SCENARIO_ORDER},
                confidence=minutes["confidence"],
                provenance={"minutes": minutes["basis"],
                            "rates": central.get("rate_basis", ""),
                            "defcon": central.get("defcon_basis", ""),
                            "team": factors.get(p["team"], {}).get("source", ""),
                            # Fait observé, pas estimation : combien de GW
                            # regardées, combien démarrées, combien jouées.
                            "minutes_observed": {
                                "gws": minutes["n_gw"],
                                "starts": minutes["n_starts_obs"],
                                "apps": minutes["n_apps_obs"]}},
            ))

    return ProjectionSet(
        contract_version=CONTRACT_VERSION, model_version=MODEL_VERSION,
        as_of=as_of or parsed.get("as_of")
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        horizon=list(gws), gw=gws[0],
        deadline=next((e.get("deadline_time") for e in parsed.get("events", [])
                       if e.get("id") == gws[0]), None),
        n_history_gws=len(parsed.get("live", {})),
        snapshot=parsed.get("run_dir", ""),
        synthetic=bool(parsed.get("synthetic")),
        availability=availability, data_confidence=conf, data_confidence_why=why,
        team_factor_source=next(iter(factors.values()), {}).get("source", "inconnu"),
        scenario_names=list(priors.SCENARIO_ORDER),
        scenarios_meta={n: {"label": priors.params(n)["label"],
                            "note": priors.params(n)["note"]}
                        for n in priors.SCENARIO_ORDER},
        players=players,
        teams={str(t["id"]): t.get("short_name", str(t["id"]))
               for t in boot.get("teams", [])},
        rows=rows,
    )
