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

# Conduite de ligue : MESURÉE par simulation (A11, docs/anomalies-constatees.md).
# Monte Carlo de la fin de saison sur deux mini-ligues réelles, 24 managers,
# effectifs et points réels GW1-GW10, chips restants compris. Trois conduites
# comparées par P(finir 1er) : couvrir le leader, maximiser l'espérance,
# parier sur des différentiels. Retard au-delà duquel parier rapporte plus que
# maximiser, selon le nombre de GW restantes :
SEUIL_PARIS = ((24, 45), (12, 20), (0, 8))      # (GW restantes ≥, retard > pts)
NB_GW_SAISON = 38
# Peloton compact : le manager juste devant est à portée d'une journée. [H]
PELOTON_COMPACT = 5       # pts


def seuil_paris(gw_restantes):
    """Retard (pts) au-delà duquel des paris modérés battent l'espérance."""
    for mini, seuil in SEUIL_PARIS:
        if gw_restantes >= mini:
            return seuil
    return SEUIL_PARIS[-1][1]


def conduite(ecart_leader, gw_restantes):
    """COUVRIR, MAXIMISER ou PARIER — la règle mesurée (A11).

    `ecart_leader` : points de retard sur le premier (0 si en tête ou à égalité).
    Ce que la simulation a montré, et que la règle applique :
      - en tête ou à égalité, couvrir rapporte (+9 points de P(1er) à égalité
        avec 28 GW restantes) ;
      - en retard modéré, maximiser l'espérance ; copier le leader coûte cher
        dès qu'il reste 18 GW ou moins (−9 points de P(1er) à 17 pts de retard) ;
      - parier ne paie qu'au-delà du seuil, et peu (+1 à +3 points de P(1er)) ;
      - un capitaine différentiel coûte toujours (−16 points de P(1er)).
    """
    if ecart_leader <= 0:
        return "couvrir"
    if ecart_leader > seuil_paris(gw_restantes):
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
        devant = [r for r in rows if (r.get("total") or 0) > (me.get("total") or 0)]
        if devant:
            out["gap_to_next"] = (min((r.get("total") or 0) for r in devant)
                                  - (me.get("total") or 0))
    for rid, r in rivals.items():
        chips = [c.get("name") for c in (r.get("history") or {}).get("chips", [])]
        if chips:
            out["chips_used"][r["row"].get("entry_name", str(rid))] = chips
    return out


def arbitrage(vues):
    """Une seule équipe pour plusieurs ligues : quelle conduite l'emporte ?

    Mesuré (A11) : parier coûte de l'espérance, donc des chances dans la ligue
    où l'on maximise (≈ −1 point de P(1er) à 17 pts de retard), pour un gain
    plus petit dans la ligue où l'on parie (≈ +0,7 point à 91 pts). La conduite
    sans pari l'emporte donc dès qu'une ligue la demande. Retourne
    (conduite, ligue qui la dicte) ou None si une seule conduite est en jeu."""
    c = [(v.get("conduite"), v.get("name") or str(v.get("id"))) for v in vues
         if v.get("conduite")]
    if len({x for x, _ in c}) < 2:
        return None
    for prio in ("couvrir", "maximiser"):
        for x, nom in c:
            if x == prio:
                return x, nom
    return None


def _posture(st, gw_restantes=None):
    """Lecture de la position et conduite mesurée, en une ligne :
    « situation — conduite ». Le moteur ne décide rien à partir de ça : il
    donne au lecteur la règle que la simulation a validée (A11)."""
    gap = st.get("gap_to_leader")
    if st.get("me") is None or gap is None:
        return "position inconnue dans cette ligue"
    restantes = NB_GW_SAISON if gw_restantes is None else gw_restantes
    suivant = st.get("gap_to_next")
    compact = (gap > 0 and suivant is not None and suivant <= PELOTON_COMPACT
               and suivant < gap)
    situation = ("en tête" if gap <= 0 else
                 f"{'chasseur' if conduite(gap, restantes) == 'maximiser' else 'distancé'}"
                 f" ({gap} pts du leader, {restantes} GW restantes)")
    if compact:
        situation += (f", peloton compact ({suivant} pt(s) devant : gagner une "
                      "place est à portée d'une journée)")
    c = conduite(gap, restantes)
    if c == "couvrir":
        regle = ("COUVRIR : posséder le capitaine et les joueurs clés du "
                 "poursuivant le plus proche ; jamais de capitaine différentiel")
    elif c == "maximiser":
        regle = ("MAXIMISER : suivre le conseil, sans pari et sans copier le "
                 "leader ; jouer ses chips")
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
    return {
        "id": league.get("id"), "name": league.get("name", ""),
        "standings": st, "exposure": table,
        "posture": _posture(st, None if parsed.get("last_closed_gw") is None
                            else NB_GW_SAISON - parsed["last_closed_gw"]),
        "conduite": (None if st.get("gap_to_leader") is None else conduite(
            st["gap_to_leader"], NB_GW_SAISON - (parsed.get("last_closed_gw") or 0))),
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
