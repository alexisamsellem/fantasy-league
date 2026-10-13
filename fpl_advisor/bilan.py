# -*- coding: utf-8 -*-
"""Le bilan d'une journée jouée — le mail d'APRÈS.

Le mail d'avant dit quoi faire et pourquoi. Celui-ci dit ce que ça a donné,
dans le même ordre causal : le score, puis ce qui l'a fait — le brassard, le
transfert, le banc — puis ce que le moteur avait prévu face à ce qui s'est
passé, et enfin la conséquence sur les classements.

Tout vient de l'API publique après validation des points par FPL
(`data_checked`), et du contrat de projections figé AVANT la deadline. Rien
n'est recalculé après coup : comparer le réel à une prévision refaite avec le
résultat sous les yeux ne mesurerait rien.
"""

from pathlib import Path

from .forecasting import ProjectionSet
from .mail import (ENCRE, FOND, GRIS, POS, STYLE_SOMBRE, TRAIT, VERT, AMBRE,
                   _date_courte, _echap, _gras, _nb, _pts)

FIGEAGES = "projections-figees"
CHIPS = {"wildcard": "Wildcard", "freehit": "Free Hit",
         "bboost": "Bench Boost", "3xc": "Triple capitaine"}


def contrat_fige(gw, dossier=FIGEAGES):
    """Le contrat figé avant la deadline de `gw`, ou None s'il n'existe pas."""
    for nom in (f"projections-GW{gw}.json.gz", f"projections-GW{gw}.json"):
        p = Path(dossier) / nom
        if p.exists():
            try:
                return ProjectionSet.load(p)
            except (ValueError, OSError, KeyError):
                return None
    return None


def _ligne_historique(history, gw):
    courant = (history or {}).get("current") or []
    cur = next((h for h in courant if h.get("event") == gw), None)
    prev = max((h for h in courant if (h.get("event") or 0) < gw),
               key=lambda h: h["event"], default=None)
    return cur, prev


def _onze_final(picks):
    """Les joueurs qui ont réellement compté : le onze de départ, corrigé des
    remplacements automatiques. Banc entier si Bench Boost."""
    ids = [pk["element"] for pk in picks["picks"]]
    if picks.get("active_chip") == "bboost":
        return ids
    onze = [pk["element"] for pk in picks["picks"] if pk["position"] <= 11]
    for s in picks.get("automatic_subs") or []:
        if s.get("element_out") in onze:
            onze[onze.index(s["element_out"])] = s.get("element_in")
    return onze


def build(d, contrat=None):
    """Données collectées (`collect.load_bilan`) → bilan structuré."""
    gw = d["gw"]
    boot = d["bootstrap"]
    picks = d.get("picks")
    if not picks or not picks.get("picks"):
        raise SystemExit(f"BLOCAGE : picks de la GW{gw} illisibles — rien à analyser.")
    elements = {e["id"]: e for e in boot.get("elements", [])}
    ev = next((e for e in boot.get("events", []) if e.get("id") == gw), {})
    live = {e["id"]: e.get("stats") or {} for e in (d.get("live") or {}).get("elements", [])}

    def nom(pid):
        return elements.get(pid, {}).get("web_name", f"#{pid}")

    def pts(pid):
        return int(live.get(pid, {}).get("total_points") or 0)

    def minutes(pid):
        return int(live.get(pid, {}).get("minutes") or 0)

    cur, prev = _ligne_historique(d.get("history"), gw)
    cur = cur or picks.get("entry_history") or {}
    points = int(cur.get("points") or 0)
    cout = int(cur.get("event_transfers_cost") or 0)

    onze = _onze_final(picks)
    cap_pk = next((pk for pk in picks["picks"] if pk.get("is_captain")), None)
    vice_pk = next((pk for pk in picks["picks"] if pk.get("is_vice_captain")), None)
    facteur = 3 if picks.get("active_chip") == "3xc" else 2
    porteur = None
    if cap_pk and minutes(cap_pk["element"]) > 0:
        porteur = cap_pk["element"]
    elif vice_pk and minutes(vice_pk["element"]) > 0:
        porteur = vice_pk["element"]
    ideal = max(onze, key=pts) if onze else None
    capitaine = {
        "nom": nom(cap_pk["element"]) if cap_pk else None,
        "porteur": nom(porteur) if porteur else None,
        "a_joue": bool(cap_pk and porteur == cap_pk["element"]),
        "pts": pts(porteur) if porteur else 0,
        "facteur": facteur,
        "ideal": nom(ideal) if ideal else None,
        "ideal_pts": pts(ideal) if ideal else 0,
    }
    capitaine["perte"] = max(0, capitaine["ideal_pts"] - capitaine["pts"]) * (facteur - 1)

    transferts = [{"sortant": nom(t["element_out"]), "entrant": nom(t["element_in"]),
                   "pts_sortant": pts(t["element_out"]),
                   "pts_entrant": pts(t["element_in"])}
                  for t in d.get("transfers") or [] if t.get("event") == gw]

    banc = [pk["element"] for pk in picks["picks"] if pk["element"] not in onze]
    meilleur_banc = max(banc, key=pts) if banc else None

    joueurs = []
    ep = {}
    if contrat is not None and gw in contrat.horizon:
        ep = {r.player_id: r.ep for r in contrat.rows if r.gw == gw}
    for pid in onze:
        mult = facteur if pid == porteur else 1
        joueurs.append({"nom": nom(pid), "poste": elements.get(pid, {}).get("element_type"),
                        "pts": pts(pid), "minutes": minutes(pid), "mult": mult,
                        "ep": ep.get(pid)})
    prevu = None
    if ep and all(j["ep"] is not None for j in joueurs):
        prevu = sum(j["ep"] * j["mult"] for j in joueurs)
    ecarts = sorted((j for j in joueurs if j["ep"] is not None),
                    key=lambda j: j["pts"] - j["ep"])

    ligues = []
    for lg in d.get("leagues") or []:
        rows = lg.get("rows") or []
        moi = next((r for r in rows if r.get("entry") == d.get("team_id")), None)
        if not moi:
            continue
        totaux = [r.get("event_total") or 0 for r in rows]
        top = max(rows, key=lambda r: r.get("event_total") or 0)
        ligues.append({
            "nom": lg["name"], "rang": moi.get("rank"),
            "ancien": moi.get("last_rank") or None, "n": len(rows),
            "journee": moi.get("event_total"),
            "moyenne": sum(totaux) / len(totaux) if totaux else None,
            "top_nom": top.get("entry_name"), "top_pts": top.get("event_total"),
        })

    calib = None
    if contrat is not None and gw in contrat.horizon:
        mins = {pid: int(s.get("minutes") or 0) for pid, s in live.items()}
        if any(mins.values()):
            from .evaluation import calibration
            try:
                calib = calibration.assess(contrat, mins, gw)["conclusion"]
            except SystemExit:
                calib = None

    return {
        "gw": gw, "points": points, "cout": cout, "net": points - cout,
        "moyenne": ev.get("average_entry_score"),
        "meilleur": ev.get("highest_score"),
        "rang_gw": cur.get("rank"),
        "rang_general": cur.get("overall_rank"),
        "rang_general_avant": (prev or {}).get("overall_rank"),
        "banc_pts": int(cur.get("points_on_bench") or 0),
        "meilleur_banc": ({"nom": nom(meilleur_banc), "pts": pts(meilleur_banc)}
                          if meilleur_banc else None),
        "chip": picks.get("active_chip"),
        "remplacements": [(nom(s.get("element_out")), nom(s.get("element_in")))
                          for s in picks.get("automatic_subs") or []],
        "capitaine": capitaine, "transferts": transferts,
        "joueurs": joueurs, "prevu": prevu,
        "surprise": ecarts[-1] if ecarts else None,
        "deception": ecarts[0] if ecarts else None,
        "ligues": ligues, "calibration": calib,
        "contrat_as_of": contrat.as_of if contrat is not None else None,
    }


# --------------------------------------------------------------- le fond ----

def _signe(n, dec=0):
    s = f"{abs(n):.{dec}f}".replace(".", ",")
    return ("+" if n > 0 else "−" if n < 0 else "") + s


def _rang(n):
    return f"{n:,}".replace(",", " ") if isinstance(n, int) else "?"


def sujet(b):
    c = b["capitaine"]
    morceaux = [f"Bilan GW{b['gw']}", f"{_pts(b['net'])}"]
    if b["moyenne"] is not None:
        morceaux[-1] += f" (moy. {b['moyenne']})"
    if c["porteur"]:
        morceaux.append(f"{c['porteur']} (C) {_pts(c['pts'] * c['facteur'])}")
    a, n = b["rang_general_avant"], b["rang_general"]
    if isinstance(a, int) and isinstance(n, int) and a != n:
        morceaux.append("classement " + ("↑" if n < a else "↓"))
    return " · ".join(morceaux)


def chaine(b):
    """Le score, puis ce qui l'a fait, dans l'ordre où ça a pesé."""
    out = []
    moy = b["moyenne"]
    tete = f"{_pts(b['net'])}"
    if b["cout"]:
        tete += f" ({b['points']} − {b['cout']} de pénalité de transfert)"
    if moy is not None:
        ecart = b["net"] - moy
        out.append((tete, f"{_signe(ecart)} par rapport à la moyenne générale "
                          f"({moy} pts). Meilleur score de la journée : "
                          f"{b['meilleur'] or '?'} pts."))
    else:
        out.append((tete, "moyenne générale non publiée."))

    c = b["capitaine"]
    if not c["porteur"]:
        out.append(("Brassard perdu", f"ni {c['nom']} ni le vice n'ont joué : "
                                       "aucun point doublé."))
    else:
        qui = c["porteur"] if c["a_joue"] else (
            f"{c['porteur']} (vice, {c['nom']} n'a pas joué)")
        if c["perte"] > 0:
            suite = (f"le meilleur choix dans ton onze était {c['ideal']} "
                     f"({c['ideal_pts']} pts) : {_pts(c['perte'])} laissés sur "
                     "la table.")
        else:
            suite = "c'était le meilleur choix possible dans ton onze."
        out.append((f"Brassard : {qui}, {c['pts']} × {c['facteur']} = "
                    f"{c['pts'] * c['facteur']} pts", suite))

    trs = b["transferts"]
    if len(trs) > 3:
        # Wildcard ou Free Hit : quinze lignes noieraient le reste. Le bilan
        # d'ensemble dit ce que le remaniement a rapporté ; les détails sont
        # dans le onze plus bas.
        ent = sum(t["pts_entrant"] for t in trs)
        sor = sum(t["pts_sortant"] for t in trs)
        chip = CHIPS.get(b["chip"], "remaniement")
        out.append((f"{chip} : {len(trs)} transferts, {_signe(ent - sor)} pts",
                    f"les entrants ont marqué {ent} pts, les sortants en "
                    f"auraient marqué {sor}."))
        trs = []
    for t in trs:
        delta = t["pts_entrant"] - t["pts_sortant"]
        out.append((f"Transfert {t['sortant']} → {t['entrant']} : {_signe(delta)} pt"
                    + ("s" if abs(delta) > 1 else ""),
                    f"{t['entrant']} a marqué {t['pts_entrant']}, {t['sortant']} "
                    f"en aurait marqué {t['pts_sortant']}."))
    if not b["transferts"]:
        out.append(("Aucun transfert", "l'effectif de la journée précédente a "
                                        "joué tel quel."))

    mb = b["meilleur_banc"]
    if b["chip"] == "bboost":
        out.append(("Bench Boost", f"le banc a compté : {_pts(b['banc_pts'])}."))
    elif b["banc_pts"]:
        out.append((f"{_pts(b['banc_pts'])} restés sur le banc",
                    f"surtout {mb['nom']} ({mb['pts']})." if mb else ""))
    for sortant, entrant in b["remplacements"]:
        out.append((f"Remplacement auto : {entrant} pour {sortant}",
                    f"{sortant} n'a pas joué."))

    if b["prevu"] is not None:
        ecart = b["net"] + b["cout"] - b["prevu"]
        detail = []
        s, dc = b["surprise"], b["deception"]
        if s and s["pts"] - s["ep"] > 0:
            detail.append(f"plus belle surprise {s['nom']} ({s['pts']} pts pour "
                          f"{_nb(s['ep'], 1)} prévus)")
        if dc and dc["pts"] - dc["ep"] < 0:
            detail.append(f"plus grosse déception {dc['nom']} ({dc['pts']} pts "
                          f"pour {_nb(dc['ep'], 1)} prévus)")
        out.append((f"Le moteur attendait {_nb(b['prevu'], 1)} pts pour ce onze : "
                    f"{_signe(ecart, 1)}",
                    (" ; ".join(detail) + ".") if detail else
                    "aucun écart marquant joueur par joueur."))

    a, n = b["rang_general_avant"], b["rang_general"]
    if isinstance(n, int):
        if isinstance(a, int) and a != n:
            sens = "gagné" if n < a else "perdu"
            out.append((f"Classement général : {_rang(a)} → {_rang(n)}",
                        f"{_rang(abs(a - n))} places {sens}es."))
        else:
            out.append((f"Classement général : {_rang(n)}", "inchangé."))
    return out


def lignes_ligues(b):
    out = []
    for l in b["ligues"]:
        mouv = ""
        if l["ancien"] and l["rang"] and l["ancien"] != l["rang"]:
            mouv = (f" (↑{l['ancien'] - l['rang']})" if l["rang"] < l["ancien"]
                    else f" (↓{l['rang'] - l['ancien']})")
        moy = f", moyenne de la ligue {_nb(l['moyenne'], 1)}" if l["moyenne"] is not None else ""
        out.append(f"**{l['nom']}** : {l['rang']}ᵉ / {l['n']}{mouv} — "
                   f"{l['journee']} pts cette journée{moy} ; meilleur : "
                   f"{l['top_nom']} ({l['top_pts']}).")
    return out


# ------------------------------------------------------------------ rendu ----

def render_texte(b):
    out = [f"Bilan GW{b['gw']}", "", "CE QUI S'EST PASSÉ, DANS L'ORDRE"]
    for titre, texte in chaine(b):
        out.append(f"  > {titre}")
        if texte:
            out.append(f"    {texte}")
    if b["joueurs"]:
        out += ["", "TON ONZE (points réels / prévus)"]
        for et in (1, 2, 3, 4):
            js = [j for j in b["joueurs"] if j["poste"] == et]
            if js:
                out.append(f"  {POS[et]:>3}  " + " · ".join(
                    f"{j['nom']}{' (C)' if j['mult'] > 1 else ''} {j['pts']}"
                    + (f"/{_nb(j['ep'], 1)}" if j["ep"] is not None else "")
                    for j in js))
    if b["ligues"]:
        out += ["", "TES LIGUES"]
        out += ["  " + l.replace("**", "") for l in lignes_ligues(b)]
    if b["calibration"]:
        out += ["", "LE MOTEUR, NOTÉ", "  " + b["calibration"]]
    return "\n".join(out)


def render_html(b):
    police = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"
    bon = b["moyenne"] is None or b["net"] >= b["moyenne"]
    couleur = VERT if bon else AMBRE

    def titre(t):
        return (f'<p class="sourdine" style="margin:26px 0 10px;font:800 11px/1.4 '
                f'{police};letter-spacing:.1em;text-transform:uppercase;'
                f'color:{GRIS};">{_echap(t)}</p>')

    etapes = "".join(
        f'<tr><td class="encre" style="padding:0 0 12px;font:400 14px/1.55 {police};'
        f'color:{ENCRE};"><strong>{_echap(t)}</strong>'
        + (f'<br><span class="sourdine" style="color:{GRIS};">{_echap(x)}</span>'
           if x else "") + "</td></tr>"
        for t, x in chaine(b))

    onze = ""
    if b["joueurs"]:
        lignes = []
        for et in (1, 2, 3, 4):
            js = [j for j in b["joueurs"] if j["poste"] == et]
            if not js:
                continue
            cell = " · ".join(
                f"{_echap(j['nom'])}{' <strong>(C)</strong>' if j['mult'] > 1 else ''} "
                f"<strong>{j['pts']}</strong>"
                + (f'<span style="color:{GRIS};">/{_nb(j["ep"], 1)}</span>'
                   if j["ep"] is not None else "")
                for j in js)
            lignes.append(f'<tr><td style="padding:4px 10px 4px 0;font:800 11px/1.6 '
                          f'{police};color:{GRIS};">{POS[et]}</td>'
                          f'<td class="encre" style="font:400 14px/1.6 {police};'
                          f'color:{ENCRE};">{cell}</td></tr>')
        onze = (f'<tr><td style="padding:0 22px;">{titre("Ton onze — réel / prévu")}'
                f'<table role="presentation" class="cadre" width="100%" '
                f'style="background:#f9fafb;border:1px solid {TRAIT};'
                f'border-radius:10px;padding:8px 12px;">{"".join(lignes)}'
                f'</table></td></tr>')

    ligues = ""
    if b["ligues"]:
        items = "".join(f'<li style="margin:0 0 8px;">{_gras(l)}</li>'
                        for l in lignes_ligues(b))
        ligues = (f'<tr><td style="padding:0 22px;">{titre("Tes ligues")}'
                  f'<ul class="encre" style="margin:0;padding-left:20px;'
                  f'font:400 14px/1.6 {police};color:{ENCRE};">{items}</ul>'
                  f'</td></tr>')

    calib = ""
    if b["calibration"]:
        calib = (f'<tr><td style="padding:0 22px;">{titre("Le moteur, noté")}'
                 f'<p class="sourdine" style="margin:0;font:400 13px/1.6 {police};'
                 f'color:{GRIS};">{_echap(b["calibration"])}</p></td></tr>')

    moy = f" · moyenne {b['moyenne']}" if b["moyenne"] is not None else ""
    corps = f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       class="page" style="background:#eef2f7;padding:18px 10px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       class="feuille" style="max-width:600px;width:100%;background:{FOND};
              border-radius:16px;overflow:hidden;">
  <tr><td style="padding:20px 22px 16px;background:{couleur};">
    <div style="font:800 13px/1.4 {police};color:#ffffff;letter-spacing:.06em;
                text-transform:uppercase;">Bilan GW{b['gw']}</div>
    <div style="margin-top:4px;font:800 30px/1.1 {police};color:#ffffff;">
      {_echap(_pts(b['net']))}</div>
    <div style="margin-top:4px;font:600 14px/1.4 {police};color:#ffffff;">
      {_echap(moy.lstrip(' ·'))}</div>
  </td></tr>
  <tr><td style="padding:0 22px;">
    {titre("Ce qui s'est passé, dans l'ordre")}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {etapes}</table>
  </td></tr>
  {onze}
  {ligues}
  {calib}
  <tr><td style="padding:18px 22px 24px;">
    <div class="sourdine separe" style="border-top:1px solid {TRAIT};
         padding-top:12px;font:400 12px/1.6 {police};color:{GRIS};">
      Points validés par FPL. Prévisions : contrat figé avant la deadline
      ({_echap(_date_courte(b['contrat_as_of']) if b['contrat_as_of'] else 'absent')}), jamais recalculé après coup.
    </div>
  </td></tr>
</table>
</td></tr></table>"""
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark">'
            f'<meta name="supported-color-schemes" content="light dark">'
            f'<title>Bilan GW{b["gw"]}</title><style>{STYLE_SOMBRE}</style></head>'
            f'<body class="page" style="margin:0;padding:0;background:#eef2f7;">'
            f'{corps}</body></html>')
