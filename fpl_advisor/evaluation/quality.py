# -*- coding: utf-8 -*-
"""Contrôle qualité des projections : accepté, avertissement ou bloqué.

Ce module répond à une seule question : « a-t-on le droit d'appeler ça une
recommandation ? » Il ne produit aucune prévision et ne choisit aucun joueur.
Il lit le contrat de projections et des FAITS sur l'effectif candidat (coût,
capitaine, recouvrements), jamais les données brutes ni l'optimiseur.

Le verdict est déterministe : mêmes entrées, même état. Un effectif reste
toujours calculable pour le diagnostic — mais si le verdict est « bloqué », le
rapport doit l'appeler « candidat technique », pas « recommandation ».
"""

from dataclasses import asdict, dataclass, field

ACCEPTED = "accepté"
WARNING = "avertissement"
BLOCKED = "bloqué"
ORDER = {ACCEPTED: 0, WARNING: 1, BLOCKED: 2}

# Seuils du contrôle qualité. Ce sont des règles de publication, pas des
# paramètres de modèle : les changer ne change aucune projection.
STABILITY_MIN_OVERLAP = 12       # < 12/15 communs entre scénarios → bloqué
WEAK_SHARE_WARN = 0.30           # part de joueurs à minutes « faible confiance »
WEAK_SHARE_BLOCK = 0.70
BUDGET_WARN = 950                # < 95,0 M£ utilisés → suspect
BUDGET_BLOCK = 850               # < 85,0 M£ utilisés → anormal
CAPTAIN_P60_WARN = 0.50
CAPTAIN_P60_BLOCK = 0.30
BASELINE_OVERLAP_WARN = 2        # ≤ 2/15 communs avec la baseline publique
FLAT_PRIOR_MARK = "prior de poste plat"
FLAT_SHARE_BLOCK = 0.60          # top 15 dominé par des priors plats


@dataclass
class Check:
    key: str
    state: str
    detail: str


@dataclass
class Verdict:
    state: str
    checks: list = field(default_factory=list)
    summary: str = ""

    @property
    def publishable(self):
        return self.state != BLOCKED

    @property
    def label(self):
        """Comment le rapport doit nommer l'effectif."""
        return "candidat technique" if self.state == BLOCKED else "recommandation"

    def reasons(self, state=None):
        return [c for c in self.checks if state is None or c.state == state]

    def to_dict(self):
        return {"state": self.state, "summary": self.summary, "label": self.label,
                "checks": [asdict(c) for c in self.checks]}


def _worst(checks):
    return max((c.state for c in checks), key=lambda s: ORDER[s], default=ACCEPTED)


def _data_coverage(contract):
    """Couverture des données, telle que déclarée par le contrat."""
    absent = [r["key"] for r in contract.availability if not r["present"]]
    conf = contract.data_confidence
    if conf == "bloqué":
        state = BLOCKED
    elif conf == "faible":
        state = BLOCKED          # priors plats : le classement n'est pas fondé
    elif conf == "moyen":
        state = WARNING
    else:
        state = ACCEPTED
    detail = f"confiance des données « {conf} » — {contract.data_confidence_why}"
    if absent:
        detail += f" ; sources absentes : {', '.join(absent)}"
    return Check("couverture_donnees", state, detail)


def _weak_fallbacks(contract):
    """Part de joueurs dont les minutes reposent sur un repli faible."""
    rows = contract.rows_for("central")
    if not rows:
        return Check("fallbacks_faibles", BLOCKED, "aucune projection")
    weak = [r for r in rows if r["minutes_confidence"] == "faible"]
    share = len(weak) / len(rows)
    state = (BLOCKED if share >= WEAK_SHARE_BLOCK
             else WARNING if share >= WEAK_SHARE_WARN else ACCEPTED)
    return Check("fallbacks_faibles", state,
                 f"{len(weak)}/{len(rows)} joueurs ({share:.0%}) en confiance "
                 f"faible sur les minutes")


def _flat_priors(contract, squad_ids):
    """Le top 15 est-il dominé par des priors de poste plats ?"""
    if not squad_ids:
        return None
    rows = {r["id"]: r for r in contract.rows_for("central")}
    flat = [pid for pid in squad_ids
            if FLAT_PRIOR_MARK in (rows.get(pid, {}).get("minutes_basis") or "")]
    share = len(flat) / len(squad_ids)
    state = BLOCKED if share >= FLAT_SHARE_BLOCK else ACCEPTED
    return Check("priors_plats", state,
                 f"{len(flat)}/{len(squad_ids)} joueurs retenus classés sur un "
                 f"prior de poste plat ({share:.0%})")


def _stability(min_overlap, squad_size=15):
    if min_overlap is None:
        return Check("stabilite_top15", WARNING, "stabilité non mesurée")
    state = ACCEPTED if min_overlap >= STABILITY_MIN_OVERLAP else BLOCKED
    return Check("stabilite_top15", state,
                 f"recouvrement minimal entre scénarios : {min_overlap}/{squad_size} "
                 f"(seuil {STABILITY_MIN_OVERLAP}/{squad_size})")


def _budget(facts):
    cost = facts.get("cost")
    if cost is None:
        return None
    state = (BLOCKED if cost < BUDGET_BLOCK
             else WARNING if cost < BUDGET_WARN else ACCEPTED)
    return Check("budget_utilise", state,
                 f"{cost / 10:.1f} M£ engagés sur {facts.get('budget', 1000) / 10:.1f}")


def _captain(facts):
    p60 = facts.get("captain_p60")
    if p60 is None:
        return None
    state = (BLOCKED if p60 < CAPTAIN_P60_BLOCK
             else WARNING if p60 < CAPTAIN_P60_WARN else ACCEPTED)
    return Check("capitaine_plausible", state,
                 f"capitaine {facts.get('captain_name', '?')} : "
                 f"P(60+) = {p60:.0%}")


def _legality(facts):
    problems = [k for k in ("size_ok", "budget_ok", "quota_ok", "club_ok")
                if facts.get(k) is False]
    if not problems:
        return None
    return Check("legalite_fpl", BLOCKED,
                 "contraintes FPL violées : " + ", ".join(problems))


def _baseline(overlap, squad_size=15):
    if overlap is None:
        return None
    state = WARNING if overlap <= BASELINE_OVERLAP_WARN else ACCEPTED
    detail = f"recouvrement avec la baseline publique : {overlap}/{squad_size}"
    if state == WARNING:
        detail += (" — écart quasi total ; vérifier échelle, normalisation et "
                   "objectif avant d'y voir une supériorité du modèle")
    return Check("baseline_publique", state, detail)


def assess(contract, min_overlap=None, squad_facts=None, baseline_overlap=None,
           squad_ids=None):
    """Verdict déterministe. Toutes les entrées sont facultatives sauf le
    contrat : on peut juger les projections seules, avant toute optimisation."""
    facts = squad_facts or {}
    checks = [_data_coverage(contract), _weak_fallbacks(contract),
              _stability(min_overlap)]
    for maybe in (_flat_priors(contract, squad_ids or []), _legality(facts),
                  _budget(facts), _captain(facts), _baseline(baseline_overlap)):
        if maybe is not None:
            checks.append(maybe)

    state = _worst(checks)
    blocking = [c.key for c in checks if c.state == BLOCKED]
    warning = [c.key for c in checks if c.state == WARNING]
    if state == BLOCKED:
        summary = ("Publication refusée : " + ", ".join(blocking)
                   + ". L'effectif reste calculé pour le diagnostic, mais il "
                     "doit être appelé « candidat technique », pas « recommandation ».")
    elif state == WARNING:
        summary = ("Publiable avec avertissements : " + ", ".join(warning)
                   + ". À lire comme une baseline non calibrée.")
    else:
        summary = ("Aucun défaut détecté par le contrôle qualité. Cela ne "
                   "démontre pas que les projections sont justes : la "
                   "calibration se mesure après coup.")
    return Verdict(state=state, checks=checks, summary=summary)
