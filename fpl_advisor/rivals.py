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

# Retard à partir duquel « suivre le peloton » ne peut plus suffire. [H]
RETARD_CHASSEUR = 15      # pts
# En dessous, le manager juste devant est à portée d'une seule journée. [H]
PELOTON_COMPACT = 5       # pts


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


def _posture(st):
    """Lecture de la position, en une ligne. Descriptive et [H] : le moteur
    ne décide rien à partir de ça, il donne au lecteur de quoi arbitrer.

    L'écart au leader ne suffit pas à décrire une position. Être 10ᵉ à 20 pts
    du premier mais à 1 pt du 9ᵉ n'est pas la même chose qu'être 10ᵉ à 20 pts
    du premier et 15 du 9ᵉ : dans le premier cas, gagner des places est facile
    et gagner la ligue est un autre problème. Les deux écarts sont donc lus."""
    gap = st.get("gap_to_leader")
    if st.get("me") is None or gap is None:
        return "position inconnue dans cette ligue"
    if gap == 0:
        return ("en tête — le risque est de PERDRE la place : coller aux choix "
                "majoritaires protège l'avance [H]")
    if gap <= RETARD_CHASSEUR:
        return (f"chasseur proche ({gap} pts du leader) — suivre le peloton "
                "coûte peu, différencier tard suffit à doubler [H]")
    suivant = st.get("gap_to_next")
    if suivant is not None and suivant <= PELOTON_COMPACT:
        return (f"en retard du leader ({gap} pts) mais le peloton est compact "
                f"({suivant} pt(s) devant) — gagner des places est à portée "
                "d'une journée, gagner la ligue demande des paris que les "
                "autres ne prennent pas [H]")
    return (f"en retard ({gap} pts du leader) — suivre le peloton conserve "
            "l'écart : il faut des paris que les autres ne prennent pas [H]")


def league_view(parsed, league):
    """Une ligue lue entièrement : classement, posture, exposition."""
    elements = {e["id"]: e for e in parsed["bootstrap"]["elements"]}
    rivals = league.get("rivals", {})
    table, n_picks = _exposure(rivals, elements, _my_ids(parsed))
    st = _standings(league.get("standings", []), parsed.get("team_id"), rivals)
    return {
        "id": league.get("id"), "name": league.get("name", ""),
        "standings": st, "posture": _posture(st), "exposure": table,
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
