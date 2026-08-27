# -*- coding: utf-8 -*-
"""Contrôle qualité des projections : accepté, avertissement ou bloqué.

Ce module répond à une seule question : « a-t-on le droit d'appeler ça une
recommandation ? » Il ne produit aucune prévision et ne choisit aucun joueur.
Il lit le contrat de projections et des FAITS sur la décision candidate (coût,
capitaine, recouvrements, accords entre scénarios), jamais les données brutes
ni l'optimiseur.

Deux portes, mêmes trois états :
  assess()         mode effectif initial — juge un top 15 construit de zéro
  assess_weekly()  mode hebdomadaire — juge les décisions de la semaine sur un
                   effectif déjà détenu (brassard, XI, transférer ou conserver)

Elles partagent les contrôles qui portent sur les projections elles-mêmes et
divergent sur le reste : le budget engagé ne veut rien dire quand l'effectif
est celui du manager, et la fraîcheur de la collecte est vitale à la semaine
alors qu'elle est secondaire avant la GW1.

Le verdict est déterministe : mêmes entrées, même état. Un effectif reste
toujours calculable pour le diagnostic — mais si le verdict est « bloqué », le
rapport doit l'appeler « candidat technique », pas « recommandation ».
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

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

# Seuils propres au mode hebdomadaire. Ce sont encore des règles de
# publication : les changer ne change aucune projection. [H, NON CALIBRÉ]
SNAPSHOT_AGE_WARN_H = 24         # collecte d'hier : statuts et prix ont bougé
SNAPSHOT_AGE_BLOCK_H = 72
SCENARIO_AGREE_BLOCK = 2         # < 2 scénarios sur 3 d'accord → bloqué
XI_OVERLAP_WARN = 10             # sur 11 titulaires
SQUAD_SIZE = 15
LIVE_GWS_REPLACING_HISTORY = 3   # journées jouées à partir desquelles la saison
                                 # en cours porte seule la hiérarchie
MAX_PROMUS_PLAUSIBLE = 4         # une saison de PL n'en promeut que 3 ; au-delà,
                                 # ce sont des noms qui ne correspondent pas


@dataclass
class Check:
    key: str
    state: str
    detail: str


KIND_SQUAD = "effectif"
KIND_DECISION = "décision"
BLOCKED_LABEL = {KIND_SQUAD: "candidat technique",
                 KIND_DECISION: "décision technique"}


@dataclass
class Verdict:
    state: str
    checks: list = field(default_factory=list)
    summary: str = ""
    kind: str = KIND_SQUAD

    @property
    def publishable(self):
        return self.state != BLOCKED

    @property
    def label(self):
        """Comment le rapport doit nommer ce qui a été calculé."""
        if self.state != BLOCKED:
            return "recommandation"
        return BLOCKED_LABEL.get(self.kind, BLOCKED_LABEL[KIND_SQUAD])

    def reasons(self, state=None):
        return [c for c in self.checks if state is None or c.state == state]

    def to_dict(self):
        return {"state": self.state, "summary": self.summary, "label": self.label,
                "kind": self.kind, "checks": [asdict(c) for c in self.checks]}


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


def _team_reference(contract):
    """Le fichier de référence d'équipe est-il réellement apparié ?

    Il n'échoue jamais bruyamment : un club dont le nom ne correspond pas au
    bootstrap tombe en silence dans le panier « promu » et reçoit un prior
    générique. Un fichier à moitié faux est pire qu'un fichier absent — absent,
    au moins, c'est signalé par `couverture_donnees`."""
    row = next((r for r in contract.availability
                if r["key"] == "team_reference"), None)
    if row is None or not row.get("present"):
        return None                      # absence déjà couverte ailleurs
    promus = row.get("promus")
    if promus is None:
        return None
    state = WARNING if promus > MAX_PROMUS_PLAUSIBLE else ACCEPTED
    detail = f"{row.get('apparies')} clubs appariés, {promus} traités comme promus"
    if state == WARNING:
        detail += (f" — plus de {MAX_PROMUS_PLAUSIBLE} : une saison de Premier "
                   "League n'en promeut que 3, ce sont probablement des noms qui "
                   "ne correspondent pas au bootstrap FPL")
    return Check("reference_equipe", state, detail)


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


def _conclude(checks, kind):
    """État global et phrase de verdict, communs aux deux portes."""
    state = _worst(checks)
    blocking = [c.key for c in checks if c.state == BLOCKED]
    warning = [c.key for c in checks if c.state == WARNING]
    quoi = "L'effectif reste calculé" if kind == KIND_SQUAD \
        else "Les décisions restent calculées"
    if state == BLOCKED:
        summary = ("Publication refusée : " + ", ".join(blocking)
                   + f". {quoi} pour le diagnostic, mais il faut les appeler "
                     f"« {BLOCKED_LABEL[kind]} », pas « recommandation ».")
    elif state == WARNING:
        summary = ("Publiable avec avertissements : " + ", ".join(warning)
                   + ". À lire comme une baseline non calibrée.")
    else:
        summary = ("Aucun défaut détecté par le contrôle qualité. Cela ne "
                   "démontre pas que les projections sont justes : la "
                   "calibration se mesure après coup.")
    return Verdict(state=state, checks=checks, summary=summary, kind=kind)


def assess(contract, min_overlap=None, squad_facts=None, baseline_overlap=None,
           squad_ids=None):
    """Verdict déterministe. Toutes les entrées sont facultatives sauf le
    contrat : on peut juger les projections seules, avant toute optimisation."""
    facts = squad_facts or {}
    checks = [_data_coverage(contract), _weak_fallbacks(contract),
              _stability(min_overlap)]
    for maybe in (_team_reference(contract),
                  _flat_priors(contract, squad_ids or []), _legality(facts),
                  _budget(facts), _captain(facts), _baseline(baseline_overlap)):
        if maybe is not None:
            checks.append(maybe)

    return _conclude(checks, KIND_SQUAD)


# --------------------------------------------------- contrôles hebdomadaires ----

def _parse_iso(ts):
    """Horodatage ISO tolérant : None, « Z » final, absence de fuseau."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _freshness(contract, now):
    """Âge de la collecte. À la semaine, une collecte périmée est le risque
    numéro un : statuts d'infirmerie, prix et conférences de presse bougent
    tous les jours, et le rapport ne le sait pas."""
    as_of = _parse_iso(contract.as_of)
    if as_of is None or now is None:
        return Check("fraicheur_snapshot", WARNING,
                     "date de collecte illisible — âge inconnu")
    hours = (now - as_of).total_seconds() / 3600.0
    if hours < 0:
        return Check("fraicheur_snapshot", WARNING,
                     f"collecte datée du futur ({contract.as_of}) — horloge suspecte")
    state = (BLOCKED if hours >= SNAPSHOT_AGE_BLOCK_H
             else WARNING if hours >= SNAPSHOT_AGE_WARN_H else ACCEPTED)
    detail = f"collecte vieille de {hours:.0f} h (connue au {contract.as_of})"
    if state != ACCEPTED:
        detail += " — statuts, prix et forfaits ont pu changer depuis ; recollecter"
    return Check("fraicheur_snapshot", state, detail)


def _deadline(contract, now):
    """La décision est-elle encore actionnable ?

    Une recommandation publiée après la deadline n'est plus une décision, c'est
    un commentaire. Le moteur ne le vérifiait pas."""
    dl = _parse_iso(contract.deadline)
    if dl is None or now is None:
        return Check("deadline_actionnable", WARNING,
                     f"deadline GW{contract.gw} inconnue — actionnabilité non vérifiée")
    left = (dl - now).total_seconds() / 3600.0
    if left <= 0:
        return Check("deadline_actionnable", BLOCKED,
                     f"deadline GW{contract.gw} dépassée de {-left:.0f} h "
                     f"({contract.deadline}) : plus rien n'est actionnable, "
                     "relancer sur la GW suivante")
    return Check("deadline_actionnable", ACCEPTED,
                 f"{left:.0f} h avant la deadline GW{contract.gw} ({contract.deadline})")


def _data_coverage_weekly(contract):
    """Même lecture que `_data_coverage`, avec une nuance qui compte.

    Avant la GW1, `history_past` porte TOUTE la hiérarchie entre deux joueurs
    d'un même poste : sans elle, les priors sont plats et le classement est
    arbitraire — blocage justifié. En cours de saison, les minutes et les taux
    viennent de la saison en cours ; passé quelques journées, l'absence des
    saisons passées dégrade la précision sans rendre le classement arbitraire.
    Elle devient alors un avertissement.

    Sans cette nuance, `run` — qui ne collecte pas les ~700 element-summary,
    trop lents pour un rituel de deadline — serait bloqué toutes les semaines
    pour une raison qui ne s'applique qu'à la pré-saison.
    """
    base = _data_coverage(contract)
    by_key = {r["key"]: r for r in contract.availability}
    obligatoire_absent = any(r["required"] and not r["present"]
                             for r in contract.availability)
    manque_passe = not by_key.get("history_past", {}).get("present", False)
    assez_observe = contract.n_history_gws >= LIVE_GWS_REPLACING_HISTORY
    if (base.state == BLOCKED and manque_passe and assez_observe
            and not obligatoire_absent):
        return Check("couverture_donnees", WARNING,
                     base.detail + f" ; {contract.n_history_gws} GW de la saison "
                     "en cours observées (seuil "
                     f"{LIVE_GWS_REPLACING_HISTORY}) : minutes et taux ne "
                     "dépendent plus des saisons passées — dégradant, pas bloquant")
    return base


def _squad_readable(facts):
    """Les 15 joueurs détenus sont-ils tous projetables ?"""
    size = facts.get("squad_size")
    if size is None:
        return None
    missing = facts.get("missing_names") or facts.get("missing_ids") or []
    if missing:
        return Check("effectif_lisible", BLOCKED,
                     f"{len(missing)} joueur(s) de l'effectif absent(s) du contrat "
                     f"de projections ({', '.join(str(m) for m in missing)}) : "
                     "radiés du championnat ou identifiants inconnus — le XI et "
                     "le transfert sont calculés sans eux")
    state = ACCEPTED if size == SQUAD_SIZE else WARNING
    return Check("effectif_lisible", state,
                 f"{size}/{SQUAD_SIZE} joueurs détenus lus et projetés")


def _squad_up_to_date(facts):
    """L'effectif lu est-il encore celui qui jouera ?

    Les picks publics datent de la dernière GW close. Un transfert déjà
    effectué pour la GW à venir les rend faux, et rien dans les données ne le
    signale : ni le XI, ni le brassard, ni l'arbitrage ne porteraient sur la
    bonne équipe. Il n'y a pas de rattrapage possible en lecture seule — le
    seul remède est de lancer le conseiller AVANT de transférer."""
    n = facts.get("already_transferred")
    pick_gw = facts.get("pick_gw")
    if n is None:
        return None
    origine = f"effectif lu à la GW{pick_gw}" if pick_gw else "effectif lu"
    if n:
        return Check("effectif_a_jour", BLOCKED,
                     f"{origine} ; {n} transfert(s) déjà enregistré(s) pour la GW "
                     "à venir : l'API publique ne montre pas l'effectif courant, "
                     "les décisions ci-dessous portent sur une équipe périmée. "
                     "Lancer le conseiller AVANT de transférer dans l'app")
    return Check("effectif_a_jour", ACCEPTED,
                 f"{origine}, aucun transfert enregistré depuis pour la GW à venir")


def _agreement(key, agree, total, label, block_below=SCENARIO_AGREE_BLOCK):
    if agree is None or not total:
        return None
    state = (ACCEPTED if agree == total
             else WARNING if agree >= block_below else BLOCKED)
    detail = f"{label} : {agree}/{total} scénarios d'accord avec le central"
    if state == BLOCKED:
        detail += " — la décision dépend du jeu de priors, pas des données"
    elif state == WARNING:
        detail += " — décision fragile, à relire avant d'agir"
    return Check(key, state, detail)


def _xi_agreement(facts):
    overlap = facts.get("xi_min_overlap")
    if overlap is None:
        return None
    size = facts.get("xi_size", 11)
    state = ACCEPTED if overlap >= XI_OVERLAP_WARN else WARNING
    return Check("stabilite_xi", state,
                 f"recouvrement minimal du XI entre scénarios : {overlap}/{size} "
                 f"(alerte en dessous de {XI_OVERLAP_WARN}/{size})")


def assess_weekly(contract, facts=None, now=None):
    """Verdict des décisions de la semaine sur un effectif déjà détenu.

    `facts` porte ce que l'orchestrateur a mesuré : taille de l'effectif lu,
    joueurs introuvables, plausibilité du capitaine, accords entre scénarios.
    `now` est passé explicitement pour que le verdict reste déterministe et
    testable — le module ne lit jamais l'horloge tout seul."""
    facts = facts or {}
    now = now or datetime.now(timezone.utc)
    checks = [_data_coverage_weekly(contract), _weak_fallbacks(contract),
              _freshness(contract, now), _deadline(contract, now)]
    n = facts.get("n_scenarios")
    for maybe in (_team_reference(contract), _squad_readable(facts),
                  _squad_up_to_date(facts), _captain(facts),
                  _agreement("stabilite_capitaine", facts.get("captain_agree"), n,
                             "identité du capitaine"),
                  _agreement("stabilite_transfert", facts.get("decision_agree"), n,
                             "arbitrage transférer/conserver"),
                  _agreement("stabilite_echange", facts.get("swap_agree"), n,
                             "couple sortant/entrant exact"),
                  _xi_agreement(facts)):
        if maybe is not None:
            checks.append(maybe)
    return _conclude(checks, KIND_DECISION)


# ---------------------------------------------------- contrôle de l'audit ----

def assess_audit(contract, facts=None, now=None):
    """Verdict de l'audit d'effectif comparatif.

    L'objet jugé n'est ni une semaine ni un achat : c'est un DIAGNOSTIC sur
    quatre journées — l'écart entre l'effectif détenu et celui que le moteur
    achèterait à la même valeur d'équipe. D'où deux différences assumées avec
    la porte hebdomadaire :

    - `deadline_actionnable` n'est PAS contrôlée. Un audit reste vrai après la
      deadline : il décrit une divergence de modèle sur un horizon de quatre
      GW, pas une action à passer avant 17h30. Le contrôler ici bloquerait un
      rapport encore utile pour la semaine suivante ;
    - `stabilite_top15` l'est, elle, alors qu'elle ne l'est pas à la semaine :
      l'effectif idéal est RECONSTRUIT, donc il peut dépendre du jeu de priors.
      S'il change d'un scénario à l'autre, l'écart chiffré ne mesure plus une
      divergence, il mesure le choix d'un prior.

    La fraîcheur reste contrôlée : un audit calculé sur des prix et des statuts
    périmés propose un chemin de transferts qui n'existe plus.
    """
    facts = facts or {}
    now = now or datetime.now(timezone.utc)
    checks = [_data_coverage_weekly(contract), _weak_fallbacks(contract),
              _freshness(contract, now), _stability(facts.get("min_overlap"))]
    for maybe in (_team_reference(contract), _squad_readable(facts),
                  _squad_up_to_date(facts),
                  _flat_priors(contract, facts.get("rebuilt_ids") or []),
                  _legality(facts)):
        if maybe is not None:
            checks.append(maybe)
    return _conclude(checks, KIND_SQUAD)
