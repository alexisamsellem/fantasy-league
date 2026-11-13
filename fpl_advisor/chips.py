# -*- coding: utf-8 -*-
"""Vérification du timing des chips (A12).

Ce module ne prévoit rien et ne choisit rien de lui-même : il lit les chips
encore disponibles, leurs fenêtres officielles, et les signaux que le contrat
de projections donne pour la GW de décision et les deux suivantes. Il rend,
chip par chip, une consigne courte et la raison derrière.

Ce que les données GW2-GW10 ont montré (backtest sur 24 managers réels,
effectifs de la GW précédente, projections figées ; méthode et revue dans
docs/anomalies-constatees.md, A12) :

  banc renforcé et triple capitaine   même règle — jouer quand l'EP du banc
                   (resp. du capitaine) de la GW est au moins celle des GW
                   suivantes de la fenêtre. Gain contre une semaine au hasard,
                   GW2 exclue (journée où tous les capitaines ont marqué gros) :
                   ≈ +2 pts pour chacun. Signal FAIBLE, non prouvé : les
                   déclenchements tombent sur 3 GW communes à tous.
  double match     change l'espérance mécaniquement (deux matchs) : il prime.
  wildcard, free hit  rien de mesurable ici : seules les contraintes valent.

La contrainte, elle, est certaine : un seul chip par GW, et chaque chip expire
à la fin de sa fenêtre. Avec n chips et k GW restantes, il reste k − n
semaines de marge ; à zéro, il faut en jouer un chaque semaine ; en dessous,
des chips seront perdus quoi qu'il arrive.

Limite connue : un chip déjà activé pour la GW à venir n'apparaît dans
l'historique public qu'après la deadline.
"""

from .optimization.squad import armband, pick_xi

NOMS = {"wildcard": "wildcard", "freehit": "free hit",
        "bboost": "banc renforcé", "3xc": "triple capitaine"}
ORDRE = ("3xc", "bboost", "freehit", "wildcard")
SIGNAL = {"3xc": "ep_capitaine", "bboost": "ep_banc"}


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
    {(player_id, gw): n_fixtures}. Effectif supposé inchangé sur l'horizon.
    Un joueur absent du contrat est ignoré ; sans formation légale, None."""
    by_id = {r["id"]: r for r in rows}
    out = []
    for gw in gws:
        squad = [dict(by_id[p], ep=by_id[p]["eps"][gw]) for p in squad_ids
                 if p in by_id and gw in by_id[p]["eps"]]
        try:
            xi, banc = pick_xi(squad)
        except ValueError:
            return None
        cap = armband(xi)["captain"]
        out.append({"gw": gw, "capitaine": cap["web_name"], "ep_capitaine": cap["ep"],
                    "matchs_capitaine": n_matchs.get((cap["id"], gw), 1),
                    "ep_banc": sum(p["ep"] for p in banc)})
    return out


def _consigne_signal(n, sig):
    """Banc renforcé ou triple capitaine sur l'horizon déjà coupé à la fenêtre."""
    if not sig:
        return "LIBRE", "signaux indisponibles (effectif illisible)"
    if n == "3xc":
        if sig[0]["matchs_capitaine"] >= 2:
            return "JOUER CETTE GW", f"{sig[0]['capitaine']} joue deux matchs"
        dgw = next((s for s in sig[1:] if s["matchs_capitaine"] >= 2), None)
        if dgw:
            return "ATTENDRE", f"double match de {dgw['capitaine']} en GW{dgw['gw']}"
    cle = SIGNAL[n]
    quoi = "du banc" if n == "bboost" else f"du capitaine ({sig[0]['capitaine']})"
    if all(sig[0][cle] >= s[cle] for s in sig[1:]):
        suite = ", ".join(f"{s[cle]:.1f}" for s in sig[1:])
        return "JOUER CETTE GW", (f"EP {quoi} {sig[0][cle]:.1f}, au moins celle des GW "
                                  f"suivantes de la fenêtre ({suite or 'aucune'}) — "
                                  "signal faible")
    best = max(sig, key=lambda s: s[cle])
    return "ATTENDRE", (f"EP {quoi} plus haute en GW{best['gw']} "
                        f"({best[cle]:.1f} contre {sig[0][cle]:.1f}) — signal faible")


def verifier(dispo, sig):
    """Consignes chip par chip pour la GW de décision (sig[0])."""
    if dispo is None:
        return {"etat": "inconnu", "raison": "fenêtres officielles des chips absentes"}
    if not dispo:
        return {"etat": "aucun", "chips": [], "marge": None}
    fin = min(c["fin"] for c in dispo)
    meme_fenetre = [c for c in dispo if c["fin"] == fin]
    restantes = meme_fenetre[0]["gw_restantes"]
    marge = restantes - len(meme_fenetre)
    lignes = []
    for c in dispo:
        n = c["name"]
        horizon = [s for s in (sig or []) if s["gw"] <= c["fin"]]   # rien après l'expiration
        if n in SIGNAL:
            consigne, raison = _consigne_signal(n, horizon)
        else:
            consigne, raison = "LIBRE", "aucun signal mesuré : seules les contraintes valent"
        lignes.append({"name": n, "nom": NOMS.get(n, n), "fin": c["fin"],
                       "consigne": consigne, "raison": raison})

    # Un seul chip par GW : double match d'abord (mécanique), puis banc, puis
    # capitaine (signaux faibles, même ordre de grandeur), puis le reste.
    def rang(l):
        if l["name"] == "3xc" and "deux matchs" in l["raison"]:
            return 0
        return {"bboost": 1, "3xc": 2}.get(l["name"], 3)
    jouer = [l for l in lignes if l["consigne"] == "JOUER CETTE GW"]
    if len(jouer) > 1:
        garde = min(jouer, key=rang)
        for l in jouer:
            if l is not garde:
                l["consigne"], l["raison"] = "PAS CETTE GW", (
                    f"un seul chip par GW : {garde['nom']} passe d'abord")
        jouer = [garde]

    # Contrainte de fenêtre.
    urgent = marge <= 0
    fenetre = [l for l in lignes if l["fin"] == fin]
    if urgent and not any(l["consigne"] == "JOUER CETTE GW" for l in fenetre) and not jouer:
        garde = min(fenetre, key=rang)
        garde["consigne"], garde["raison"] = "JOUER CETTE GW", (
            f"plus de marge : {len(fenetre)} chip(s) pour {restantes} GW avant la fin "
            f"de fenêtre (GW{fin})")
    if marge < 0:
        perdus = sorted((l for l in fenetre if l["consigne"] != "JOUER CETTE GW"),
                        key=rang, reverse=True)[:-marge]
        for l in perdus:
            l["consigne"], l["raison"] = "PERDU", (
                f"{len(fenetre)} chips pour {restantes} GW : au moins {-marge} "
                "expirera sans être joué ; jouer le plus utile chaque GW")
    return {"etat": "ok", "chips": lignes, "fin": fin, "restantes": restantes,
            "marge": marge, "urgent": urgent}
