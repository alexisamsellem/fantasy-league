# -*- coding: utf-8 -*-
"""Exposition des rivaux des mini-ligues — uniquement les picks publics des
GW à deadline passée. Aucune prétention de connaître leurs choix courants.

Plusieurs ligues peuvent compter à la fois. Elles ne se moyennent pas : être
2ᵉ sur 11 et 10ᵉ sur 15 n'appelle pas la même conduite, et un joueur possédé
par tout le monde ici peut n'être possédé par personne là. Chaque ligue est
donc lue séparément, et les désaccords entre elles sont nommés plutôt que
fondus dans un chiffre unique.
"""

# Écart d'EO à partir duquel posséder un joueur n'est plus le même pari d'une
# ligue à l'autre : un tiers de l'effectif d'une ligue. [H, NON CALIBRÉ]
EO_CONFLIT = 0.33

# Conduite de ligue, issue d'un Monte Carlo de fin de saison (A11,
# docs/anomalies-constatees.md) : deux mini-ligues réelles, 24 managers,
# effectifs et points réels GW1-GW10, chips restants compris. Trois conduites
# comparées par P(finir 1er) : couvrir le leader, maximiser l'espérance,
# parier sur des différentiels.
#
# Retard au-delà duquel parier bat maximiser, selon les GW restantes. [H] :
# ces seuils dépendent de ce qu'on appelle « parier » — ici +10 pts d'écart-
# type par GW pour 0,5 pt/GW d'espérance perdue. Avec des paris moins
# dispersés (6 pts) ou plus chers (1 pt/GW), parier ne paie presque jamais.
SEUIL_PARIS = ((24, 45), (12, 20), (0, 8))      # (GW restantes ≥, retard > pts)
# Avance à partir de laquelle couvrir bat maximiser, quel que soit le nombre de
# GW restantes ; à égalité, les deux se valent (simulé, 5 tirages). [H]
AVANCE_COUVRIR = 5        # pts
# Zone où l'arbitrage entre ligues a été mesuré (28 GW restantes). En deçà,
# le coût d'un pari et son gain changent de sens : non mesuré.
ARBITRAGE_MESURE_DES = 24  # GW restantes
NB_GW_SAISON = 38
# Peloton compact : le manager juste devant est à portée d'une journée. [H]
PELOTON_COMPACT = 5       # pts


def seuil_paris(gw_restantes):
    """Retard (pts) au-delà duquel des paris modérés battent l'espérance."""
    for mini, seuil in SEUIL_PARIS:
        if gw_restantes >= mini:
            return seuil
    return SEUIL_PARIS[-1][1]


def conduite(ecart, gw_restantes):
    """couvrir, maximiser, parier — ou terminee quand la saison est jouée.

    `ecart` est SIGNÉ : retard sur le premier s'il est positif, avance sur le
    deuxième (en négatif) si l'on est en tête. Ce que la simulation montre :
      - avec au moins 5 pts d'avance, couvrir gagne ;
      - à égalité, couvrir et maximiser se valent : on maximise ;
      - en retard, maximiser, sauf au-delà du seuil de pari ;
      - un capitaine différentiel coûte toujours (−16 points de P(1er)).
    """
    if gw_restantes is not None and gw_restantes <= 0:
        return "terminee"
    if ecart <= -AVANCE_COUVRIR:
        return "couvrir"
    if ecart > seuil_paris(NB_GW_SAISON if gw_restantes is None else gw_restantes):
        return "parier"
    return "maximiser"


def _exposure(rivals, elements, my_ids):
    """EO locale : part des rivaux possédant chaque joueur, capitaine compté
    double. Retourne (table, n_rivaux_avec_picks)."""
    with_picks = {rid: r for rid, r in rivals.items()
                  if r.get("picks") and r["picks"].get("picks")}
    n = len(with_picks)
    if n == 0:
        return [], 0
    counts, cap_counts = {}, {}
    for r in with_picks.values():
        for pk in r["picks"]["picks"]:
            el = pk["element"]
            counts[el] = counts.get(el, 0) + (2 if pk.get("is_captain") else 1)
            if pk.get("is_captain"):
                cap_counts[el] = cap_counts.get(el, 0) + 1
    table = []
    for el, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        e = elements.get(el, {})
        table.append({
            "element": el, "name": e.get("web_name", f"#{el}"),
            "eo_local": c / n, "captains": cap_counts.get(el, 0),
            "i_own": el in my_ids,
        })
    return table, n


def _my_ids(parsed):
    picks = (parsed.get("my") or {}).get("picks") or {}
    return {pk["element"] for pk in picks.get("picks", [])}


def _standings(rows, team_id, rivals):
    """Ma position, l'écart au leader et au voisin direct."""
    me = next((r for r in rows if r.get("entry") == team_id), None)
    out = {"n_managers": len(rows), "me": me, "leader": rows[0] if rows else None,
           "gap_to_leader": None, "gap_to_next": None, "chips_used": {}}
    if me and rows:
        out["gap_to_leader"] = (rows[0].get("total") or 0) - (me.get("total") or 0)
        autres = [(r.get("total") or 0) for r in rows if r is not me]
        if out["gap_to_leader"] <= 0 and autres:
            out["avance"] = (me.get("total") or 0) - max(autres)
        devant = [r for r in rows if (r.get("total") or 0) > (me.get("total") or 0)]
        if devant:
            out["gap_to_next"] = (min((r.get("total") or 0) for r in devant)
                                  - (me.get("total") or 0))
    for rid, r in rivals.items():
        chips = [c.get("name") for c in (r.get("history") or {}).get("chips", [])]
        if chips:
            out["chips_used"][r["row"].get("entry_name", str(rid))] = chips
    return out


def ecart_signe(st):
    """Retard sur le premier (> 0), ou avance sur le deuxième (≤ 0)."""
    gap = st.get("gap_to_leader")
    if gap is None:
        return None
    return gap if gap > 0 else -(st.get("avance") or 0)


def arbitrage(vues):
    """Une seule équipe pour plusieurs ligues : quelle conduite l'emporte ?

    Mesuré à 28 GW restantes seulement (A11) : parier y coûte ≈ 1 point de
    P(1er) dans la ligue où l'on maximise, pour ≈ +0,7 point dans la ligue où
    l'on parie. La conduite sans pari l'emporte. Plus tard dans la saison, le
    rapport coût/gain s'inverse : l'arbitrage n'est alors pas mesuré.

    Retourne None si toutes les ligues demandent la même conduite, sinon
    {"conduite", "ligue", "mesure"} ; `mesure` faux : au lecteur de trancher."""
    c = [(v.get("conduite"), v.get("name") or str(v.get("id")), v.get("gw_restantes"))
         for v in vues if v.get("conduite") and v.get("conduite") != "terminee"]
    if len({x for x, _, _ in c}) < 2:
        return None
    restantes = min((r for _, _, r in c if r is not None), default=None)
    conduites = {x for x, _, _ in c}
    if ("parier" in conduites and restantes is not None
            and restantes >= ARBITRAGE_MESURE_DES):
        x, nom, _ = next(t for t in c if t[0] != "parier")
        return {"conduite": x, "ligue": nom, "mesure": True}
    return {"conduite": None, "ligue": None, "mesure": False}


def phrase_arbitrage(vues):
    """La phrase que rapport et mail affichent, ou None."""
    arb = arbitrage(vues)
    if arb is None:
        return None
    if arb["mesure"]:
        return (f"Arbitrage entre ligues : {arb['conduite'].upper()}, dicté par "
                f"« {arb['ligue']} ». Une seule équipe sert toutes les ligues ; "
                "à ce stade de la saison, parier coûte plus de chances dans la "
                "ligue où l'on peut gagner sans parier qu'il n'en rapporte "
                "ailleurs (mesuré, A11).")
    return ("Les ligues demandent des conduites différentes et l'arbitrage "
            "n'est pas mesuré à ce stade de la saison : choisis la ligue "
            "prioritaire.")


def _posture(st, gw_restantes=None):
    """Lecture de la position et conduite, en une ligne : « situation —
    conduite ». Le moteur ne décide rien à partir de ça : il donne au lecteur
    la règle issue de la simulation (A11)."""
    ecart = ecart_signe(st)
    if st.get("me") is None or ecart is None:
        return "position inconnue dans cette ligue"
    restantes = NB_GW_SAISON if gw_restantes is None else gw_restantes
    c = conduite(ecart, restantes)
    if c == "terminee":
        return "saison terminée — aucune conduite à tenir"
    gap = st.get("gap_to_leader")
    suivant = st.get("gap_to_next")
    compact = (gap > 0 and suivant is not None and suivant <= PELOTON_COMPACT
               and suivant < gap)
    if ecart <= 0:
        situation = f"en tête ({-ecart} pts d'avance, {restantes} GW restantes)"
    else:
        situation = (f"{'distancé' if c == 'parier' else 'chasseur'} ({gap} pts "
                     f"du leader, {restantes} GW restantes)")
    if compact:
        situation += (f", peloton compact ({suivant} pt(s) devant : gagner une "
                      "place est à portée d'une journée)")
    if c == "couvrir":
        regle = ("COUVRIR : posséder le capitaine et les joueurs clés du "
                 "poursuivant le plus proche ; jamais de capitaine différentiel")
    elif c == "maximiser" and restantes >= ARBITRAGE_MESURE_DES:
        regle = ("MAXIMISER : suivre le conseil, sans pari ; à ce stade, "
                 "couvrir le leader fait aussi bien, et mieux si tu as plus de "
                 "chips que lui ; jouer ses chips")
    elif c == "maximiser":
        regle = ("MAXIMISER : suivre le conseil, sans pari et sans copier le "
                 "leader (copier coûte quand il reste 18 GW ou moins) ; jouer "
                 "ses chips")
    else:
        regle = ("PARIER, modérément : un ou deux différentiels dans "
                 "l'effectif, jamais au brassard")
    return f"{situation} — {regle}"


def league_view(parsed, league):
    """Une ligue lue entièrement : classement, posture, exposition."""
    elements = {e["id"]: e for e in parsed["bootstrap"]["elements"]}
    rivals = league.get("rivals", {})
    table, n_picks = _exposure(rivals, elements, _my_ids(parsed))
    st = _standings(league.get("standings", []), parsed.get("team_id"), rivals)
    restantes = NB_GW_SAISON - (parsed.get("last_closed_gw") or 0)
    return {
        "id": league.get("id"), "name": league.get("name", ""),
        "standings": st, "exposure": table,
        "posture": _posture(st, restantes),
        "conduite": (None if ecart_signe(st) is None
                     else conduite(ecart_signe(st), restantes)),
        "gw_restantes": restantes,
        "meta": {"gw": parsed.get("last_closed_gw"), "n_rivals": len(rivals),
                 "n_with_picks": n_picks},
    }


def league_views(parsed):
    """Toutes les ligues configurées, dans l'ordre de la config."""
    leagues = parsed.get("leagues")
    if leagues is None:                       # snapshot d'avant le multi-ligue
        leagues = [{"id": parsed.get("league_id"), "name": "mini-ligue",
                    "standings": parsed.get("standings", []),
                    "rivals": parsed.get("rivals", {})}]
    return [league_view(parsed, l) for l in leagues]


def exposure_conflicts(views, seuil=EO_CONFLIT):
    """Joueurs dont posséder ou non n'est pas le même pari selon la ligue.

    Deux ligues peuvent tirer dans des sens opposés : un joueur possédé par
    presque tout le monde ici est une position défensive, le même joueur
    possédé par personne là-bas est un pari. Le fait est mesurable, donc il est
    mesuré — l'arbitrage, lui, reste humain."""
    if len(views) < 2:
        return []
    eo = {}
    for v in views:
        for row in v["exposure"]:
            eo.setdefault(row["element"], {"name": row["name"],
                                           "i_own": row["i_own"], "par_ligue": {}})
            eo[row["element"]]["par_ligue"][v["id"]] = row["eo_local"]
    out = []
    for el, d in eo.items():
        vals = [d["par_ligue"].get(v["id"], 0.0) for v in views]
        ecart = max(vals) - min(vals)
        if ecart >= seuil:
            out.append({"element": el, "name": d["name"], "i_own": d["i_own"],
                        "eo": vals, "ecart": ecart})
    out.sort(key=lambda r: -r["ecart"])
    return out


# --------------------------------------------------- compatibilité V0 ----

def local_exposure(parsed):
    """Vue historique : l'exposition de la PREMIÈRE ligue configurée."""
    views = league_views(parsed)
    if not views:
        return [], {"gw": parsed.get("last_closed_gw"), "n_rivals": 0,
                    "n_with_picks": 0}
    return views[0]["exposure"], views[0]["meta"]


def standings_summary(parsed):
    """Vue historique : le classement de la PREMIÈRE ligue configurée."""
    views = league_views(parsed)
    return views[0]["standings"] if views else {
        "n_managers": 0, "me": None, "leader": None,
        "gap_to_leader": None, "gap_to_next": None, "chips_used": {}}
