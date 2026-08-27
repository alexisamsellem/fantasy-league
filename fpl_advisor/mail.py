# -*- coding: utf-8 -*-
"""Le mail de la semaine — court, HTML, décision en tête.

Le rapport Markdown reste la trace complète : douze contrôles, quatre tableaux
de projections, les hypothèses. Il est fait pour être relu et audité. Il n'est
pas fait pour être lu sur un téléphone à 19h20 un vendredi.

Ce module produit l'autre objet : ce qu'il faut faire, puis POURQUOI, dans cet
ordre. La justification n'est pas reléguée en bas de page — elle suit
immédiatement la décision, sous forme de chaîne : ce fait a produit cette
conséquence, qui a produit celle-là. Un lecteur qui s'arrête après trois lignes
sait quoi jouer ; un lecteur qui continue sait pourquoi.

Contraintes de la messagerie, toutes assumées :
  - mise en page en tableaux, styles en ligne : les clients mail ignorent les
    feuilles de style externes et une bonne partie de la grille CSS ;
  - aucune image distante, aucun script, rien à télécharger ;
  - une version texte accompagne toujours le HTML — certains clients ne
    montrent que celle-là, et elle doit rester lisible seule.
"""

from datetime import datetime, timezone

POS = {1: "GB", 2: "DEF", 3: "MIL", 4: "ATT"}

# Palette : une seule teinte d'accent par état, contrastée sur fond clair. Les
# messageries en thème sombre inversent parfois les couleurs — d'où des fonds
# explicites partout, jamais de transparent.
ENCRE = "#111827"
GRIS = "#6b7280"
TRAIT = "#e5e7eb"
FOND = "#ffffff"
CARTE = "#f9fafb"
VERT = "#15803d"
AMBRE = "#b45309"
ROUGE = "#b91c1c"
PELOUSE = "#166534"

ETATS = {"accepté": (VERT, "✓ feu vert"),
         "avertissement": (AMBRE, "▲ à relire"),
         "bloqué": (ROUGE, "✕ ne pas jouer")}


def _nb(x, dec=2):
    """Nombre à la française : virgule décimale, pas de point."""
    return f"{x:.{dec}f}".replace(".", ",")


def _pct(x):
    """Pourcentage à la française : espace insécable avant le signe."""
    return f"{100 * x:.0f}\u00a0%"


def _pts(n, mot="pt"):
    return f"{n} {mot}{'s' if abs(n) > 1 else ''}"


def _date_courte(ts):
    """Horodatage lisible : la microseconde n'apprend rien à personne."""
    t = str(ts or "?").replace("T", " ")
    return t[:16] + " UTC" if len(t) >= 16 else t


def _heures(deadline, maintenant=None):
    if not deadline:
        return None
    maintenant = maintenant or datetime.now(timezone.utc)
    try:
        dl = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dl - maintenant).total_seconds() / 3600.0


def _quand(h):
    if h is None:
        return "deadline inconnue"
    if h <= 0:
        return "deadline passée"
    if h < 1:
        return f"plus que {h * 60:.0f} min"
    if h < 48:
        return f"plus que {h:.0f} h"
    return f"encore {h / 24:.0f} jours"


def sujet(rec, maintenant=None):
    h = _heures(rec.get("deadline"), maintenant)
    tr = rec["transfer"]
    if tr["decision"] == "transférer" and tr["candidates"]:
        c = tr["candidates"][0]
        quoi = f"{c['out']['web_name']} → {c['in']['web_name']}"
    else:
        quoi = "on garde tout"
    band = rec["armband"]["captain"]["web_name"]
    return f"GW{rec['gw']} · {quoi} · {band} capitaine · {_quand(h)}"


# ------------------------------------------------------------ le fond ----

def decisions(rec):
    """Les trois lignes qui décident, dans l'ordre où on les exécute."""
    tr = rec["transfer"]
    ap = rec.get("apres_transfert")
    band = (ap or rec)["armband"]
    xi = (ap or rec)["xi"]
    d, m, f = (sum(1 for p in xi if p["element_type"] == t) for t in (2, 3, 4))
    lignes = []
    if tr["decision"] == "transférer" and tr["candidates"]:
        c = tr["candidates"][0]
        lignes.append(("Transfert",
                       f"{c['out']['web_name']} → {c['in']['web_name']}",
                       f"+{_nb(c['delta3'], 1)} pts sur {tr['horizon']} journées"))
    else:
        lignes.append(("Transfert", "aucun",
                       f"rien ne dépasse le seuil de +{tr['threshold']:.0f} pts"))
    lignes.append(("Capitaine", band["captain"]["web_name"],
                   f"vice : {band['vice']['web_name']}"))
    lignes.append(("Formation", f"{d}-{m}-{f}", "onze ci-dessous"))
    return lignes


def chaine(rec):
    """La chaîne de causalité : chaque décision et le fait qui la produit.

    C'est le cœur de ce mail. Une recommandation sans sa cause n'est pas
    vérifiable par le lecteur : il ne peut que faire confiance, ou pas."""
    tr, ap = rec["transfer"], rec.get("apres_transfert")
    band = rec["armband"]
    out = []

    if tr["decision"] == "transférer" and tr["candidates"]:
        c = tr["candidates"][0]
        sortant, entrant = c["out"], c["in"]
        sur_le_banc = sortant["id"] in {p["id"] for p in rec["bench"]}
        out.append((
            f"{sortant['web_name']} sort",
            f"il pèse {_nb(sortant['ep'])} pt attendu cette journée"
            + (" et il est sur ton banc, donc il ne te rapporte rien"
               if sur_le_banc else "")
            + f". {entrant['web_name']} en pèse {_nb(entrant['ep'])}."))
        if ap and ap["xi_in"]:
            noms = ", ".join(p["web_name"] for p in ap["xi_in"])
            out.append((f"{noms} prend une place dans le onze",
                        "l'entrant est meilleur que le onzième titulaire, "
                        "donc il joue — ce n'est pas un renfort de banc"))
        if ap and ap["xi_out"]:
            noms = ", ".join(p["web_name"] for p in ap["xi_out"])
            out.append((f"{noms} passe sur le banc",
                        "c'est lui que l'entrant déplace, et c'est pour ça que "
                        "la formation change"))
        out.append((
            f"Gain compté : +{_nb(c['delta3'])} pts",
            f"mesuré sur le MEILLEUR ONZE, pas sur l'écart entre les deux "
            f"joueurs (qui vaut +{_nb(c.get('delta3_brut', c['delta3']))} et "
            "surestime tout échange de banc)"))
    else:
        top = tr["candidates"][0] if tr["candidates"] else None
        out.append((
            "On ne transfère pas",
            (f"le meilleur échange trouvé ({top['out']['web_name']} → "
             f"{top['in']['web_name']}) ne rapporte que +{_nb(top['delta3'])} pts, "
             f"sous le seuil de +{tr['threshold']:.0f}" if top
             else "aucun échange réalisable n'améliore le onze")))

    c, v = band["captain"], band["vice"]
    out.append((
        f"{c['web_name']} porte le brassard",
        f"{_nb(c['ep'])} pts attendus et {_pct(c['p_play'])} de chances de "
        f"jouer. {v['web_name']} suit à {_nb(v['ep'])} — il devient capitaine "
        "seulement "
        f"si {c['web_name']} ne joue aucune minute"))

    ag = rec.get("agreement") or {}
    n = ag.get("n_scenarios")
    if n:
        out.append((
            "Ces choix tiennent debout",
            f"le moteur rejoue la semaine avec trois jeux d'hypothèses "
            f"différents. Capitaine : {ag.get('captain_agree')}/{n} d'accord. "
            f"Transfert : {ag.get('decision_agree')}/{n}. Couple exact : "
            f"{ag.get('swap_agree')}/{n}"))
    return out


def alertes(rec):
    """Ce qui ferait changer d'avis avant la deadline."""
    ap = rec.get("apres_transfert")
    band = (ap or rec)["armband"]
    c = band["captain"]
    out = []
    if c["p_play"] < 0.93:
        out.append(f"{c['web_name']} déclaré forfait ou ménagé en conférence de "
                   f"presse → le brassard passe à {band['vice']['web_name']}.")
    tr = rec["transfer"]
    if tr["decision"] == "transférer" and tr["candidates"]:
        cd = tr["candidates"][0]
        out.append(f"{cd['in']['web_name']} annoncé incertain, ou "
                   f"{cd['out']['web_name']} confirmé titulaire → on garde.")
    blesses = [p for p in (ap or rec)["xi"]
               if p.get("status", "a") != "a" or (p.get("news") or "").strip()]
    for p in blesses[:3]:
        news = (p.get("news") or "").strip()
        out.append(f"**{p['web_name']}** : {news or 'statut non disponible'}.")
    if not out:
        out.append("Rien de spécial. Relance quand même après les conférences "
                   "de presse.")
    return out


def ligues(rec):
    """Une ligne par mini-ligue : où tu en es, et ce que ça implique."""
    out = []
    for v in rec.get("leagues") or []:
        st = v["standings"]
        if not st.get("me"):
            continue
        posture = v["posture"].split(" — ")[-1].replace(" [H]", "")
        out.append({
            "nom": v["name"],
            "rang": f"{st['me'].get('rank')}ᵉ / {st['n_managers']}",
            "ecart": f"{_pts(st['gap_to_leader'])} du leader",
            "voisin": (f"{_pts(st['gap_to_next'])} du suivant"
                       if st.get("gap_to_next") else "en tête"),
            "lecture": posture,
        })
    return out


# ------------------------------------------------------------- rendu ----

def _echap(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _gras(t):
    """`**mot**` → gras. Les alertes sont écrites une fois, rendues deux."""
    bouts, ouvert = _echap(t).split("**"), False
    out = []
    for b in bouts:
        out.append(f"<strong>{b}</strong>" if ouvert else b)
        ouvert = not ouvert
    return "".join(out)


def _bloc(contenu, fond=FOND, bord=None, pad="16px 20px"):
    style = f"background:{fond};padding:{pad};"
    if bord:
        style += f"border:1px solid {bord};border-radius:10px;"
    return (f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" style="border-collapse:separate;"><tr>'
            f'<td style="{style}">{contenu}</td></tr></table>')


def _titre(t):
    return (f'<p style="margin:28px 0 10px;font:600 12px/1.4 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'letter-spacing:.09em;text-transform:uppercase;color:{GRIS};">'
            f'{_echap(t)}</p>')


def _ligne_joueur(p, brassard=None):
    badge = ""
    if brassard == "C":
        badge = ('<span style="background:#facc15;color:#422006;font-weight:700;'
                 'font-size:10px;padding:1px 5px;border-radius:4px;'
                 'margin-left:5px;">C</span>')
    elif brassard == "V":
        badge = ('<span style="background:#d1fae5;color:#065f46;font-weight:700;'
                 'font-size:10px;padding:1px 5px;border-radius:4px;'
                 'margin-left:5px;">V</span>')
    return f"{_echap(p['web_name'])}{badge}"


def _pelouse(rec):
    """Le onze, par ligne de poste, sur fond vert. Le banc juste dessous."""
    ap = rec.get("apres_transfert")
    xi = (ap or rec)["xi"]
    bench = (ap or rec)["bench"]
    band = (ap or rec)["armband"]
    cap, vice = band["captain"]["id"], band["vice"]["id"]

    rangs = []
    for et in (1, 2, 3, 4):
        joueurs = sorted((p for p in xi if p["element_type"] == et),
                         key=lambda p: -p["ep"])
        if not joueurs:
            continue
        cells = " &nbsp;·&nbsp; ".join(
            _ligne_joueur(p, "C" if p["id"] == cap else
                          "V" if p["id"] == vice else None) for p in joueurs)
        rangs.append(
            f'<tr><td style="padding:9px 12px;text-align:center;color:#ffffff;'
            f'font:600 15px/1.5 -apple-system,BlinkMacSystemFont,\'Segoe UI\','
            f'Roboto,Arial,sans-serif;">{cells}</td></tr>')

    banc = " &nbsp;·&nbsp; ".join(
        f"{i}. {_echap(p['web_name'])}" for i, p in enumerate(bench, 1))
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{PELOUSE};border-radius:10px;">'
        + "".join(rangs) +
        f'<tr><td style="padding:10px 12px 14px;text-align:center;'
        f'border-top:1px solid rgba(255,255,255,.22);color:#bbf7d0;'
        f'font:400 12px/1.5 -apple-system,BlinkMacSystemFont,\'Segoe UI\','
        f'Roboto,Arial,sans-serif;">Banc &nbsp; {banc}</td></tr></table>')


def _decisions_html(rec):
    lignes = []
    for i, (titre, quoi, note) in enumerate(decisions(rec)):
        haut = "" if i == 0 else f"border-top:1px solid {TRAIT};"
        lignes.append(
            f'<tr><td style="padding:13px 0 12px;{haut}">'
            f'<div style="font:600 11px/1.3 -apple-system,BlinkMacSystemFont,'
            f'\'Segoe UI\',Roboto,Arial,sans-serif;letter-spacing:.08em;'
            f'text-transform:uppercase;color:{GRIS};">{_echap(titre)}</div>'
            f'<div style="margin-top:4px;font:700 21px/1.3 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{ENCRE};">{_echap(quoi)}</div>'
            f'<div style="margin-top:2px;font:400 13px/1.45 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{GRIS};">{_echap(note)}</div></td></tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0">{"".join(lignes)}</table>')


def _chaine_html(rec):
    out = []
    for titre, pourquoi in chaine(rec):
        out.append(
            f'<tr><td width="20" valign="top" style="padding:9px 0 0;'
            f'color:{VERT};font:700 14px/1 Arial,sans-serif;">↳</td>'
            f'<td style="padding:7px 0 7px 6px;font:400 14px/1.6 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{ENCRE};"><strong>{_echap(titre)}</strong><br>'
            f'<span style="color:{GRIS};font-size:13px;">'
            f'{_echap(pourquoi)}</span></td></tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0">{"".join(out)}</table>')


def _ligues_html(rec):
    cartes = []
    for l in ligues(rec):
        cartes.append(_bloc(
            f'<div style="font:700 15px/1.3 -apple-system,BlinkMacSystemFont,'
            f'\'Segoe UI\',Roboto,Arial,sans-serif;color:{ENCRE};">'
            f'{_echap(l["nom"])}</div>'
            f'<div style="margin-top:3px;font:600 13px/1.5 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{ENCRE};">{_echap(l["rang"])} &nbsp;·&nbsp; '
            f'{_echap(l["ecart"])} &nbsp;·&nbsp; {_echap(l["voisin"])}</div>'
            f'<div style="margin-top:5px;font:400 13px/1.5 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{GRIS};">{_echap(l["lecture"])}</div>',
            fond=CARTE, bord=TRAIT, pad="13px 16px"))
    return '<div style="height:8px;line-height:8px;">&nbsp;</div>'.join(cartes)


def render_html(rec, maintenant=None):
    """Le mail. Décision, puis pourquoi, puis le onze, puis le contexte."""
    v = rec.get("verdict")
    etat = v.state if v is not None else "avertissement"
    couleur, pastille = ETATS.get(etat, ETATS["avertissement"])
    h = _heures(rec.get("deadline"), maintenant)
    verts = sum(1 for c in (v.checks if v is not None else []) if c.state == "accepté")
    total = len(v.checks) if v is not None else 0

    alertes_html = "".join(
        f'<li style="margin:0 0 7px;">{_gras(a)}</li>' for a in alertes(rec))

    corps = f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:#f3f4f6;padding:20px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;width:100%;background:{FOND};border-radius:14px;
              overflow:hidden;">

  <tr><td style="padding:22px 24px 18px;border-bottom:1px solid {TRAIT};">
    <table role="presentation" width="100%"><tr>
      <td style="font:800 26px/1.15 -apple-system,BlinkMacSystemFont,'Segoe UI',
                 Roboto,Arial,sans-serif;color:{ENCRE};">GW{rec['gw']}</td>
      <td align="right" style="font:600 12px/1.4 -apple-system,
                 BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
        <span style="background:{couleur};color:#ffffff;padding:4px 10px;
                     border-radius:20px;">{pastille}</span></td>
    </tr></table>
    <div style="margin-top:6px;font:600 15px/1.4 -apple-system,
                BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
                color:{couleur};">{_echap(_quand(h).capitalize())} pour jouer.</div>
  </td></tr>

  <tr><td style="padding:4px 24px 0;">
    {_titre("Ce que tu fais")}
    {_decisions_html(rec)}
  </td></tr>

  <tr><td style="padding:0 24px;">
    {_titre("Pourquoi — dans l'ordre")}
    {_chaine_html(rec)}
  </td></tr>

  <tr><td style="padding:0 24px;">
    {_titre("Ton onze")}
    {_pelouse(rec)}
  </td></tr>

  <tr><td style="padding:0 24px;">
    {_titre("Ce qui te ferait changer d'avis")}
    <ul style="margin:0;padding-left:20px;font:400 14px/1.6 -apple-system,
               BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
               color:{ENCRE};">{alertes_html}</ul>
  </td></tr>

  <tr><td style="padding:0 24px;">
    {_titre("Tes ligues")}
    {_ligues_html(rec)}
  </td></tr>

  <tr><td style="padding:24px;">
    <div style="border-top:1px solid {TRAIT};padding-top:14px;
                font:400 12px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',
                Roboto,Arial,sans-serif;color:{GRIS};">
      <strong style="color:{ENCRE};">{verts}/{total} contrôles au vert.</strong>
      Ça veut dire que rien d'anormal n'a été détecté — pas que les prévisions
      sont justes. Aucune constante de ce moteur n'a encore été confrontée à un
      résultat réel. Le premier vrai score arrive après les matchs.<br><br>
      Le détail complet est en pièce jointe : les douze contrôles, les
      projections joueur par joueur, les trois scénarios, les hypothèses.<br><br>
      Données connues au {_echap(_date_courte(rec.get('as_of')))}. Prix de vente
      approximé par le prix affiché — vérifie dans l'app avant d'exécuter.
    </div>
  </td></tr>

</table>
</td></tr></table>"""

    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light">'
            f'<title>GW{rec["gw"]}</title></head>'
            f'<body style="margin:0;padding:0;background:#f3f4f6;">'
            f'{corps}</body></html>')


def render_texte(rec, maintenant=None):
    """Version texte. Certains clients ne montrent que celle-là."""
    v = rec.get("verdict")
    h = _heures(rec.get("deadline"), maintenant)
    out = [f"GW{rec['gw']} — {_quand(h)} pour jouer.", ""]
    out.append("CE QUE TU FAIS")
    for titre, quoi, note in decisions(rec):
        out.append(f"  {titre} : {quoi} ({note})")
    out += ["", "POURQUOI — DANS L'ORDRE"]
    for titre, pourquoi in chaine(rec):
        out.append(f"  > {titre}")
        out.append(f"    {pourquoi}")

    ap = rec.get("apres_transfert")
    xi, bench = (ap or rec)["xi"], (ap or rec)["bench"]
    band = (ap or rec)["armband"]
    out += ["", "TON ONZE"]
    for et in (1, 2, 3, 4):
        joueurs = sorted((p for p in xi if p["element_type"] == et),
                         key=lambda p: -p["ep"])
        if not joueurs:
            continue
        noms = " · ".join(
            p["web_name"] + (" (C)" if p["id"] == band["captain"]["id"]
                             else " (V)" if p["id"] == band["vice"]["id"] else "")
            for p in joueurs)
        out.append(f"  {POS[et]:>3}  {noms}")
    out.append("  Banc  " + " · ".join(
        f"{i}. {p['web_name']}" for i, p in enumerate(bench, 1)))

    out += ["", "CE QUI TE FERAIT CHANGER D'AVIS"]
    for a in alertes(rec):
        out.append("  - " + a.replace("**", ""))

    out += ["", "TES LIGUES"]
    for l in ligues(rec):
        out.append(f"  {l['nom']} : {l['rang']}, {l['ecart']}, {l['voisin']}")
        out.append(f"    {l['lecture']}")

    verts = sum(1 for c in (v.checks if v is not None else []) if c.state == "accepté")
    total = len(v.checks) if v is not None else 0
    out += ["", f"{verts}/{total} contrôles au vert. Rien d'anormal détecté — ce "
                "n'est pas une preuve que les prévisions sont justes. Le détail "
                "complet est en pièce jointe.",
            f"Données connues au {_date_courte(rec.get('as_of'))}. Prix de vente "
            "approximé par le prix affiché : vérifie dans l'app."]
    return "\n".join(out)
