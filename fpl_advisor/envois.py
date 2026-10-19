# -*- coding: utf-8 -*-
"""Quand écrire au manager — trois mails par journée, pas un de plus.

Avant ce module, chaque passage du conseiller envoyait son mail : quatre
passages par jour pendant les 60 h qui précèdent une deadline, plus un mail de
calibration. Une dizaine de mails par journée, presque tous identiques. Le
conseil se noyait dans sa propre répétition.

La règle, désormais :

  1. PRINCIPAL — un seul mail de décision, 7 h 30 avant la deadline (vendredi
     12 h, heure de Paris, pour une deadline du vendredi 19 h 30) ;
  2. RAPPEL — 2 h 30 avant (vendredi 17 h), le moteur recalcule. Le mail ne
     part QUE si la décision a changé : transfert, capitaine, vice ou onze ;
  3. BILAN — une fois la journée jouée et ses points validés par FPL, un mail
     qui analyse ce qui s'est passé.

Le planificateur GitHub déclenche avec plusieurs heures de retard (mesuré : de
4 h 30 à 7 h sur les passages des 8 et 9/10). Viser « 12 h pile » avec un cron
est donc illusoire. Le workflow passe toutes les heures, et c'est CE module
qui décide si l'heure est venue — d'après la deadline réelle et un journal des
envois déjà faits. Un passage en retard envoie en retard ; un passage manqué
est rattrapé par le suivant ; un mail déjà envoyé ne repart jamais.

Le journal contient la décision envoyée (noms de joueurs) : c'est une donnée
personnelle, et une donnée sensible AVANT la deadline (le capitaine prévu). Il
vit dans `data/`, ignoré par Git, et le workflow le transporte d'un passage à
l'autre par le cache d'Actions, jamais par un commit.
"""

import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .optimization.weekly import libelle as libelle_transfert

PARIS = ZoneInfo("Europe/Paris")
JOURNAL = "data/envois/journal.json"

PRINCIPAL_AVANT = timedelta(hours=7, minutes=30)
RAPPEL_AVANT = timedelta(hours=2, minutes=30)
# Un mail qui arrive après la deadline ne sert à rien : en dessous de cette
# marge, on n'envoie plus rien (collecte + calcul prennent quelques minutes).
MARGE_FIN = timedelta(minutes=20)
# Un mail principal qui tomberait la nuit (deadline du samedi midi) part la
# veille au soir plutôt qu'à 4 h 30.
NUIT_AVANT = 8                 # heure de Paris en dessous de laquelle on avance
SOIREE = time(20, 0)
GARDER_GW = 6                  # le journal ne retient que les dernières journées

MOMENTS = ("principal", "rappel")


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------- horaires ----

def horaires(deadline):
    """Deadline (UTC) → (heure du mail principal, heure du rappel), en UTC.

    Pour une deadline du vendredi 18 h 30 à Londres (19 h 30 à Paris) : 12 h et
    17 h, heure de Paris, toute la saison — l'écart Paris/Londres ne bouge pas
    au changement d'heure."""
    principal = deadline - PRINCIPAL_AVANT
    rappel = deadline - RAPPEL_AVANT
    local = principal.astimezone(PARIS)
    if local.hour < NUIT_AVANT:
        veille = datetime.combine(local.date() - timedelta(days=1), SOIREE,
                                  tzinfo=PARIS)
        principal = veille.astimezone(timezone.utc)
    return principal, rappel


def prochaine_deadline(events, maintenant):
    """(gw, deadline) de la première GW dont la deadline est future."""
    futures = []
    for e in events or []:
        dt = _date(e.get("deadline_time"))
        if dt is not None and dt > maintenant and e.get("id") is not None:
            futures.append((dt, e["id"]))
    if not futures:
        return None, None
    dt, gw = min(futures)
    return gw, dt


def derniere_journee_validee(events):
    """La GW la plus récente jouée ET dont FPL a validé les points.

    `finished` passe à vrai au dernier coup de sifflet ; `data_checked` quand
    les bonus sont figés. Analyser avant, c'est commenter des points qui vont
    encore bouger."""
    faites = [e["id"] for e in events or []
              if e.get("finished") and e.get("data_checked") and e.get("id")]
    return max(faites) if faites else None


# ---------------------------------------------------------------- journal ----

def charger(chemin=JOURNAL):
    p = Path(chemin)
    if not p.exists():
        return {"version": 1, "gw": {}}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # Un journal illisible ne doit pas bloquer le conseil. Le pire cas est
        # un mail en double, pas un mail manqué.
        return {"version": 1, "gw": {}}
    j.setdefault("gw", {})
    return j


def sauver(journal, chemin=JOURNAL):
    gws = sorted(journal.get("gw", {}), key=int)
    for vieux in gws[:-GARDER_GW]:
        del journal["gw"][vieux]
    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(journal, indent=1, ensure_ascii=False),
                 encoding="utf-8")
    return p


def _etat(journal, gw):
    return journal.get("gw", {}).get(str(gw), {})


# ------------------------------------------------------------ planifier ----

def planifier(events, journal, maintenant=None, forcer=False):
    """Que doit faire CE passage ? Un dict, sans effet de bord :

        conseil  : "principal" | "rappel" | "rien"
        gw, deadline, heures          (prochaine deadline)
        bilan_gw : GW à analyser, ou None
        raison   : une phrase pour les journaux de CI
    """
    maintenant = maintenant or datetime.now(timezone.utc)
    plan = {"conseil": "rien", "gw": None, "deadline": None, "heures": None,
            "bilan_gw": None, "raison": "", "principal_a": None,
            "rappel_a": None, "force": False}

    fini = derniere_journee_validee(events)
    if fini is not None and "bilan" not in _etat(journal, fini):
        # Seulement la journée qui vient de se jouer — ou une qu'on a
        # conseillée et pas encore analysée (semaine à deux journées, quand la
        # deadline suivante passe avant la validation des points). Jamais une
        # journée ancienne : au premier déploiement, le journal est vide, et
        # personne ne veut le bilan d'un match d'il y a un mois.
        closes = [e["id"] for e in events or []
                  if e.get("id") and _date(e.get("deadline_time"))
                  and _date(e.get("deadline_time")) <= maintenant]
        if fini == max(closes, default=None) or "principal" in _etat(journal, fini):
            plan["bilan_gw"] = fini

    gw, dl = prochaine_deadline(events, maintenant)
    if gw is None:
        plan["raison"] = "aucune deadline à venir"
        return plan
    principal, rappel = horaires(dl)
    plan.update(gw=gw, deadline=_iso(dl),
                heures=(dl - maintenant).total_seconds() / 3600.0,
                principal_a=_iso(principal), rappel_a=_iso(rappel))
    etat = _etat(journal, gw)

    if forcer:
        plan.update(conseil="principal", force=True,
                    raison="envoi forcé à la main")
    elif maintenant >= dl - MARGE_FIN:
        plan["raison"] = "trop près de la deadline pour qu'un mail serve"
    elif maintenant >= rappel:
        if "rappel" in etat:
            plan["raison"] = "rappel déjà traité"
        else:
            plan["conseil"] = "rappel"
            plan["raison"] = ("heure du rappel" if "principal" in etat else
                              "heure du rappel, mail principal jamais parti : "
                              "il part maintenant")
    elif maintenant >= principal:
        if "principal" in etat:
            plan["raison"] = "mail principal déjà envoyé"
        else:
            plan["conseil"] = "principal"
            plan["raison"] = "heure du mail principal"
    else:
        plan["raison"] = "trop tôt"
    return plan


# ------------------------------------------------------------- décision ----

def decision(rec):
    """Ce que le manager doit FAIRE, réduit à ce qui peut changer d'un passage
    à l'autre. Le mail montre l'effectif d'après transfert (anomalie A6) :
    la décision aussi."""
    tr = rec["transfer"]
    ap = rec.get("apres_transfert")
    band = (ap or rec)["armband"]
    if tr["decision"] == "transférer" and tr["candidates"]:
        transfert = libelle_transfert(tr)
    else:
        transfert = "aucun"
    return {
        "transfert": transfert,
        "capitaine": band["captain"]["web_name"],
        "vice": band["vice"]["web_name"],
        "onze": sorted(p["web_name"] for p in (ap or rec)["xi"]),
    }


def changements(avant, apres):
    """Ce qui diffère entre deux décisions, en phrases lisibles. Liste vide si
    rien n'a bougé."""
    out = []
    for cle, nom in (("transfert", "Transfert"), ("capitaine", "Capitaine"),
                     ("vice", "Vice-capitaine")):
        if avant.get(cle) != apres.get(cle):
            out.append(f"{nom} : {avant.get(cle) or '?'} → **{apres.get(cle)}**.")
    entrent = sorted(set(apres.get("onze", [])) - set(avant.get("onze", [])))
    sortent = sorted(set(avant.get("onze", [])) - set(apres.get("onze", [])))
    if entrent or sortent:
        morceaux = []
        if entrent:
            morceaux.append(f"**{', '.join(entrent)}** entre")
        if sortent:
            morceaux.append(f"{', '.join(sortent)} sort")
        out.append("Onze : " + " ; ".join(morceaux) + ".")
    return out


def arbitrer(journal, gw, moment, dec):
    """(envoyer, changements) pour ce passage.

    Au rappel, on compare à la décision du mail principal. Si celui-ci n'est
    jamais parti (passage manqué), le rappel en tient lieu et part quoi qu'il
    arrive : le manager doit recevoir au moins un conseil par journée."""
    if moment not in MOMENTS:
        raise ValueError(f"moment inconnu : {moment}")
    if moment == "principal":
        return True, []
    avant = (_etat(journal, gw).get("principal") or {}).get("decision")
    if avant is None:
        return True, []
    diff = changements(avant, dec)
    return bool(diff), diff


def noter(journal, gw, moment, envoye, dec=None, maintenant=None):
    """Inscrit un passage au journal. Appelé APRÈS l'envoi réussi : un envoi
    raté n'est pas noté, et le passage suivant réessaie."""
    ts = _iso(maintenant or datetime.now(timezone.utc))
    etat = journal.setdefault("gw", {}).setdefault(str(gw), {})
    if moment == "bilan":
        etat["bilan"] = {"envoye_le": ts}
        return journal
    if moment not in MOMENTS:
        raise ValueError(f"moment inconnu : {moment}")
    if envoye and "principal" not in etat:
        # Le rappel qui part en premier devient la référence.
        etat["principal"] = {"envoye_le": ts, "decision": dec, "par": moment}
    if moment == "rappel":
        etat["rappel"] = {"traite_le": ts, "envoye": bool(envoye)}
    return journal


def sortie(**kv):
    """Écrit `cle=valeur` sur la sortie standard et dans $GITHUB_OUTPUT."""
    for k, v in kv.items():
        print(f"{k}={'' if v is None else v}")
    chemin = os.environ.get("GITHUB_OUTPUT")
    if chemin:
        with open(chemin, "a", encoding="utf-8") as fh:
            for k, v in kv.items():
                fh.write(f"{k}={'' if v is None else v}\n")
