# -*- coding: utf-8 -*-
"""Exposition des rivaux de la mini-ligue — uniquement les picks publics des
GW à deadline passée. Aucune prétention de connaître leurs choix courants."""


def local_exposure(parsed):
    """EO locale sur la dernière GW close : part des rivaux possédant chaque
    joueur, capitaine compté double. Retourne (table, méta)."""
    rivals = parsed.get("rivals", {})
    with_picks = {rid: r for rid, r in rivals.items()
                  if r.get("picks") and r["picks"].get("picks")}
    n = len(with_picks)
    meta = {
        "gw": parsed.get("last_closed_gw"),
        "n_rivals": len(rivals),
        "n_with_picks": n,
    }
    if n == 0:
        return [], meta

    counts, cap_counts = {}, {}
    for r in with_picks.values():
        for pk in r["picks"]["picks"]:
            el = pk["element"]
            mult = 2 if pk.get("is_captain") else 1
            counts[el] = counts.get(el, 0) + mult
            if pk.get("is_captain"):
                cap_counts[el] = cap_counts.get(el, 0) + 1

    elements = {e["id"]: e for e in parsed["bootstrap"]["elements"]}
    my_ids = set()
    if parsed.get("my", {}).get("picks"):
        my_ids = {pk["element"] for pk in parsed["my"]["picks"].get("picks", [])}

    table = []
    for el, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        e = elements.get(el, {})
        table.append({
            "element": el,
            "name": e.get("web_name", f"#{el}"),
            "eo_local": c / n,
            "captains": cap_counts.get(el, 0),
            "i_own": el in my_ids,
        })
    return table, meta


def standings_summary(parsed):
    """Ma position, l'écart au leader et aux voisins directs."""
    rows = parsed.get("standings", [])
    me = next((r for r in rows if r.get("entry") == parsed.get("team_id")), None)
    out = {"n_managers": len(rows), "me": me, "leader": rows[0] if rows else None,
           "gap_to_leader": None, "chips_used": {}}
    if me and rows:
        out["gap_to_leader"] = (rows[0].get("total") or 0) - (me.get("total") or 0)
    for rid, r in parsed.get("rivals", {}).items():
        hist = r.get("history") or {}
        chips = [c.get("name") for c in hist.get("chips", [])]
        if chips:
            out["chips_used"][r["row"].get("entry_name", str(rid))] = chips
    return out
