# -*- coding: utf-8 -*-
"""Vérification du timing des chips (A12).

Ce module ne prévoit rien et ne choisit rien de lui-même : il lit les chips
encore disponibles, leurs fenêtres officielles, et les signaux que le contrat
de projections donne pour la GW de décision et les deux suivantes. Il rend,
chip par chip, une consigne courte et la raison mesurée derrière.

Ce que les données GW2-GW10 ont montré (backtest sur 24 managers réels,
effectifs de la GW précédente, projections figées ; méthode dans
docs/anomalies-constatees.md, A12) :

  banc renforcé    l'EP du banc PRÉDIT les points du banc (corrélation 0,59).
                   Jouer quand l'EP du banc de la GW est au moins celle des
                   deux suivantes : +1,8 pt contre une semaine au hasard (IC90
                   −0,1 ; +4,0). Signal faible mais réel.
  triple capitaine l'EP du capitaine NE prédit PAS ses points (corrélation
                   0,03 ; parmi les 57 candidats capitaines à EP ≥ 4,5 sur
                   données publiques, Spearman 0,00). Aucun moment n'est
                   prévisible ; seul un double match change l'espérance,
                   mécaniquement (deux matchs, deux fois les points).
  wildcard, free hit  rien de mesurable ici : seules les contraintes valent.

La contrainte, elle, est certaine : un seul chip par GW, et chaque chip expire
à la fin de sa fenêtre. Avec n chips et k GW restantes, il reste k − n
semaines de marge ; à zéro, il faut en jouer un chaque semaine.
"""

from .optimization.squad import armband, pick_xi

NOMS = {"wildcard": "wildcard", "freehit": "free hit",
        "bboost": "banc renforcé", "3xc": "triple capitaine"}
ORDRE = ("3xc", "bboost", "freehit", "wildcard")


def disponibles(chips_officiels, chips_joues, gw):
    """Chips encore jouables à la GW `gw`.

    `chips_officiels` : bootstrap-static → chips[] (name, start_event,
    stop_event). `chips_joues` : entry/{id}/history → chips[] (name, event).
    Retourne None si les fenêtres officielles sont absentes : on ne les
    invente pas."""
    if not chips_officiels:
        return None
    out = []
    for c in chips_officiels:
        debut, fin = c.get("start_event"), c.get("stop_event")
        if debut is None or fin is None or not (debut <= gw <= fin):
            continue
        deja = any(j.get("name") == c.get("name") and debut <= (j.get("event") or 0) <= fin
                   for j in (chips_joues or []))
        if not deja:
            out.append({"name": c["name"], "fin": fin, "gw_restantes": fin - gw + 1})
    return sorted(out, key=lambda c: ORDRE.index(c["name"]) if c["name"] in ORDRE else 9)


def signaux(rows, squad_ids, gws, n_matchs):
    """Par GW de l'horizon : capitaine, son EP, son nombre de matchs, EP du banc.

    `rows` : lignes du contrat (scénario central). `n_matchs` :
    {(player_id, gw): n_fixtures}. Effectif supposé inchangé sur l'horizon."""
    by_id = {r["id"]: r for r in rows}
    out = []
    for gw in gws:
        squad = [dict(by_id[p], ep=by_id[p]["eps"][gw]) for p in squad_ids if p in by_id]
        if len(squad) < 15:
            return None
        xi, banc = pick_xi(squad)
        cap = armband(xi)["captain"]
        out.append({"gw": gw, "capitaine": cap["web_name"], "ep_capitaine": cap["ep"],
                    "matchs_capitaine": n_matchs.get((cap["id"], gw), 1),
                    "ep_banc": sum(p["ep"] for p in banc)})
    return out


def verifier(dispo, sig):
    """Consignes chip par chip pour la GW de décision (sig[0])."""
    if dispo is None:
        return {"etat": "inconnu", "raison": "fenêtres officielles des chips absentes"}
    if not dispo:
        return {"etat": "aucun", "chips": [], "marge": None}
    # Marge par fenêtre : un chip par GW.
    fin = min(c["fin"] for c in dispo)
    meme_fenetre = [c for c in dispo if c["fin"] == fin]
    restantes = meme_fenetre[0]["gw_restantes"]
    marge = restantes - len(meme_fenetre)
    lignes = []
    for c in dispo:
        n = c["name"]
        if n == "bboost":
            suivantes = ", ".join(f"{s['ep_banc']:.1f}" for s in (sig or [])[1:]) or "—"
            if sig and sig[0]["ep_banc"] >= max(s["ep_banc"] for s in sig[1:] or sig[:1]):
                consigne, raison = "JOUER CETTE GW", (
                    f"EP du banc {sig[0]['ep_banc']:.1f}, au moins celle des GW "
                    f"suivantes ({suivantes})")
            elif sig:
                meilleure = max(sig, key=lambda s: s["ep_banc"])
                consigne, raison = "ATTENDRE", (
                    f"EP du banc plus haute en GW{meilleure['gw']} "
                    f"({meilleure['ep_banc']:.1f} contre {sig[0]['ep_banc']:.1f})")
            else:
                consigne, raison = "—", "effectif illisible"
        elif n == "3xc":
            if sig and sig[0]["matchs_capitaine"] >= 2:
                consigne, raison = "JOUER CETTE GW", (
                    f"{sig[0]['capitaine']} joue deux matchs : l'espérance double")
            else:
                dgw = next((s for s in (sig or [])[1:] if s["matchs_capitaine"] >= 2), None)
                if dgw:
                    consigne, raison = "ATTENDRE", (
                        f"double match de {dgw['capitaine']} en GW{dgw['gw']}")
                else:
                    consigne, raison = "LIBRE", (
                        "aucun moment prévisible : l'EP du capitaine ne prédit pas "
                        "ses points ; le placer sur une GW sans autre chip")
        else:
            consigne, raison = "LIBRE", "aucun signal mesuré : seules les contraintes valent"
        lignes.append({"name": n, "nom": NOMS.get(n, n), "fin": c["fin"],
                       "consigne": consigne, "raison": raison})
    # Contrainte : sans marge, un chip doit partir cette GW.
    urgent = marge <= 0
    if urgent and not any(l["consigne"] == "JOUER CETTE GW" for l in lignes if l["fin"] == fin):
        for l in lignes:
            if l["fin"] == fin:
                l["consigne"], l["raison"] = "JOUER CETTE GW", (
                    f"plus de marge : {len(meme_fenetre)} chip(s) pour {restantes} GW "
                    f"avant la fin de fenêtre (GW{fin})")
                break
    # Un seul chip par GW : si plusieurs consignes disent « jouer », la mieux
    # fondée l'emporte — double match (mécanique), puis signal mesuré du banc,
    # puis contrainte de fenêtre. Les autres attendent.
    jouer = [l for l in lignes if l["consigne"] == "JOUER CETTE GW"]
    if len(jouer) > 1:
        rang = {"3xc": 0, "bboost": 1}
        garde = min(jouer, key=lambda l: rang.get(l["name"], 2))
        for l in jouer:
            if l is not garde:
                l["consigne"], l["raison"] = "PAS CETTE GW", (
                    f"un seul chip par GW : {garde['nom']} passe d'abord")
    return {"etat": "ok", "chips": lignes, "fin": fin, "restantes": restantes,
            "marge": marge, "urgent": urgent}
