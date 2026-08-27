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

# Une couleur par poste. Toutes les pastilles sont CLAIRES avec un texte
# foncé — jamais l'inverse. Raison : les messageries en thème sombre
# retournent les couleurs qu'elles jugent claires, et retournent AUSSI le
# texte posé dessus. Un fond clair + texte foncé reste donc contrasté après
# inversion (il devient foncé + texte clair). Un bloc foncé avec du texte
# blanc, lui, se fait inverser à moitié et devient illisible — c'est ce qui
# est arrivé au terrain vert de la première version.
POSTES = {
    1: {"nom": "GB",  "fond": "#fef3c7", "encre": "#78350f", "trait": "#fcd34d"},
    2: {"nom": "DEF", "fond": "#dbeafe", "encre": "#1e3a8a", "trait": "#93c5fd"},
    3: {"nom": "MIL", "fond": "#dcfce7", "encre": "#14532d", "trait": "#86efac"},
    4: {"nom": "ATT", "fond": "#ffe4e6", "encre": "#881337", "trait": "#fda4af"},
}
CAPITAINE = {"fond": "#fef08a", "encre": "#422006", "trait": "#eab308"}
VICE = {"fond": "#e9d5ff", "encre": "#4c1d95", "trait": "#c4b5fd"}
BANC = {"fond": "#f1f5f9", "encre": "#475569", "trait": "#cbd5e1"}

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


def _pastille(p, brassard=None):
    """Un joueur = une pastille colorée par son poste. Le brassard change la
    couleur ET ajoute une lettre : la couleur seule ne suffit pas à qui la
    distingue mal."""
    c = POSTES[p["element_type"]]
    if brassard == "C":
        c = CAPITAINE
    elif brassard == "V":
        c = VICE
    lettre = ""
    if brassard:
        lettre = (f'<span style="font-weight:800;">&nbsp;{brassard}</span>')
    return (f'<span style="display:inline-block;background:{c["fond"]};'
            f'color:{c["encre"]};border:1px solid {c["trait"]};'
            f'border-radius:999px;padding:6px 12px;margin:0 5px 7px 0;'
            f'font:600 14px/1.2 -apple-system,BlinkMacSystemFont,\'Segoe UI\','
            f'Roboto,Arial,sans-serif;white-space:nowrap;">'
            f'{_echap(p["web_name"])}{lettre}</span>')


def _etiquette(et):
    c = POSTES[et]
    return (f'<span style="display:inline-block;background:{c["trait"]};'
            f'color:{c["encre"]};border-radius:6px;padding:4px 8px;'
            f'font:800 11px/1 -apple-system,BlinkMacSystemFont,\'Segoe UI\','
            f'Roboto,Arial,sans-serif;letter-spacing:.06em;">'
            f'{c["nom"]}</span>')


def _pelouse(rec):
    """Le onze, une ligne par poste, en pastilles colorées. Le banc dessous.

    Pas de grand aplat sombre : voir le commentaire de POSTES. Chaque ligne
    porte son étiquette de poste à gauche, ce qui permet de lire la formation
    même quand les noms passent à la ligne sur un téléphone."""
    ap = rec.get("apres_transfert")
    xi, bench = (ap or rec)["xi"], (ap or rec)["bench"]
    band = (ap or rec)["armband"]
    cap, vice = band["captain"]["id"], band["vice"]["id"]

    rangs = []
    for et in (1, 2, 3, 4):
        joueurs = sorted((p for p in xi if p["element_type"] == et),
                         key=lambda p: -p["ep"])
        if not joueurs:
            continue
        chips = "".join(
            _pastille(p, "C" if p["id"] == cap else
                      "V" if p["id"] == vice else None) for p in joueurs)
        rangs.append(
            f'<tr><td width="46" valign="top" style="padding:9px 8px 2px 0;">'
            f'{_etiquette(et)}</td>'
            f'<td valign="top" style="padding:6px 0 0;">{chips}</td></tr>')

    banc = "".join(
        f'<span style="display:inline-block;background:{BANC["fond"]};'
        f'color:{BANC["encre"]};border:1px solid {BANC["trait"]};'
        f'border-radius:999px;padding:5px 11px;margin:0 5px 6px 0;'
        f'font:600 13px/1.2 -apple-system,BlinkMacSystemFont,\'Segoe UI\','
        f'Roboto,Arial,sans-serif;white-space:nowrap;">'
        f'{i}. {_echap(p["web_name"])}</span>'
        for i, p in enumerate(bench, 1))

    return (
        f'<table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0" class="cadre" style="background:{CARTE};'
        f'border:1px solid {TRAIT};border-radius:12px;">'
        f'<tr><td style="padding:12px 16px 6px;">'
        f'<table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0">{"".join(rangs)}</table></td></tr>'
        f'<tr><td style="padding:10px 16px 12px;border-top:1px solid {TRAIT};">'
        f'<div class="sourdine" style="margin-bottom:7px;font:800 11px/1 '
        f'-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,'
        f'sans-serif;letter-spacing:.08em;color:{GRIS};">BANC</div>'
        f'{banc}</td></tr></table>')


ACCENTS = [("#7c3aed", "#ede9fe"),   # transfert : violet
           ("#a16207", "#fef9c3"),   # capitaine : or
           ("#0f766e", "#ccfbf1")]   # formation : turquoise


def _decisions_html(rec):
    lignes = []
    for i, (titre, quoi, note) in enumerate(decisions(rec)):
        trait, fond = ACCENTS[i % len(ACCENTS)]
        lignes.append(
            f'<tr><td style="padding:0 0 9px;">'
            f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" style="background:{fond};'
            f'border-left:5px solid {trait};border-radius:10px;"><tr>'
            f'<td style="padding:11px 15px;">'
            f'<div style="font:800 11px/1.3 -apple-system,BlinkMacSystemFont,'
            f'\'Segoe UI\',Roboto,Arial,sans-serif;letter-spacing:.09em;'
            f'text-transform:uppercase;color:{trait};">{_echap(titre)}</div>'
            f'<div style="margin-top:3px;font:800 20px/1.25 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{ENCRE};">{_echap(quoi)}</div>'
            f'<div style="margin-top:2px;font:400 13px/1.45 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{trait};">{_echap(note)}</div>'
            f'</td></tr></table></td></tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0">{"".join(lignes)}</table>')


def _chaine_html(rec):
    """Chaque maillon numéroté : la chaîne se lit dans l'ordre, et le lecteur
    voit du premier coup d'œil combien d'étapes il reste."""
    out = []
    for i, (titre, pourquoi) in enumerate(chaine(rec), 1):
        out.append(
            f'<tr><td width="30" valign="top" style="padding:5px 0 0;">'
            f'<span style="display:inline-block;width:22px;height:22px;'
            f'background:#dcfce7;color:#14532d;border:1px solid #86efac;'
            f'border-radius:999px;text-align:center;'
            f'font:800 12px/21px -apple-system,BlinkMacSystemFont,'
            f'\'Segoe UI\',Roboto,Arial,sans-serif;">{i}</span></td>'
            f'<td class="encre" style="padding:4px 0 12px 8px;'
            f'font:400 14px/1.55 -apple-system,BlinkMacSystemFont,'
            f'\'Segoe UI\',Roboto,Arial,sans-serif;color:{ENCRE};">'
            f'<strong>{_echap(titre)}</strong><br>'
            f'<span class="sourdine" style="color:{GRIS};font-size:13px;">'
            f'{_echap(pourquoi)}</span></td></tr>')
    return (f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0">{"".join(out)}</table>')


def _ligues_html(rec):
    cartes = []
    for l in ligues(rec):
        chaud = "retard" in l["lecture"] or "paris" in l["lecture"]
        trait, fond = (("#c2410c", "#ffedd5") if chaud
                       else ("#0369a1", "#e0f2fe"))
        cartes.append(
            f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0" style="background:{fond};'
            f'border-left:5px solid {trait};border-radius:10px;'
            f'margin-bottom:9px;"><tr><td style="padding:12px 15px;">'
            f'<div style="font:800 15px/1.3 -apple-system,BlinkMacSystemFont,'
            f'\'Segoe UI\',Roboto,Arial,sans-serif;color:{ENCRE};">'
            f'{_echap(l["nom"])}</div>'
            f'<div style="margin-top:3px;font:700 13px/1.5 -apple-system,'
            f'BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;'
            f'color:{trait};">{_echap(l["rang"])} &nbsp;·&nbsp; '
            f'{_echap(l["ecart"])} &nbsp;·&nbsp; {_echap(l["voisin"])}</div>'
            f'<div style="margin-top:5px;font:400 13px/1.5 '
            f'-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,'
            f'sans-serif;color:{ENCRE};">{_echap(l["lecture"])}</div>'
            f'</td></tr></table>')
    return "".join(cartes)


def _phrase_pieces(pieces):
    """Ne promets une pièce jointe que s'il y en a une.

    Le mail annonçait « le détail complet est en pièce jointe » quoi qu'il
    arrive. Quand l'audit échouait — il est en `continue-on-error` — ou quand
    l'envoi partait sans fichier, le mail mentait au lecteur."""
    if not pieces:
        return ("Le rapport complet — douze contrôles, projections joueur par "
                "joueur, trois scénarios, hypothèses — reste sous "
                "<code>data/reports/</code>. Aucune pièce jointe dans cet "
                "envoi.")
    noms = ", ".join(_echap(n) for n in pieces)
    pluriel = "s" if len(pieces) > 1 else ""
    return (f"En pièce{pluriel} jointe{pluriel} : {noms} — les douze contrôles, "
            "les projections joueur par joueur, les trois scénarios et les "
            "hypothèses. Le mail décide, la pièce jointe prouve.")


# Thème sombre. Sans ce bloc, les messageries inversent l'e-mail à leur façon
# et détruisent le contraste. Déclarer `color-scheme` leur dit que la page
# gère elle-même les deux thèmes : elles cessent d'inverser de force et
# appliquent ces règles à la place.
STYLE_SOMBRE = """
:root { color-scheme: light dark; supported-color-schemes: light dark; }
@media (prefers-color-scheme: dark) {
  .page    { background:#0b1120 !important; }
  .feuille { background:#111827 !important; }
  .cadre   { background:#1f2937 !important; border-color:#374151 !important; }
  .encre   { color:#f3f4f6 !important; }
  .sourdine{ color:#9ca3af !important; }
  .separe  { border-color:#374151 !important; }
}
"""

# Deux familles de blocs, et la distinction n'est pas cosmétique.
#
#   .cadre  conteneurs NEUTRES (le onze, la pastille de contrôle). Ils passent
#           au sombre, et le texte qu'ils portent est marqué `.encre` pour
#           s'éclaircir avec eux.
#   (rien)  cartes COLORÉES (décisions, ligues). Fond clair et texte foncé
#           FIXES tous les deux : elles restent lisibles dans les deux thèmes
#           sans qu'aucune règle ne s'applique. C'est le piège de la première
#           version — un texte marqué `.encre` s'éclaircissait sur un fond qui,
#           lui, restait clair, et disparaissait.


def render_html(rec, maintenant=None, pieces=None):
    """Le mail. Décision, puis pourquoi, puis le onze, puis le contexte."""
    v = rec.get("verdict")
    etat = v.state if v is not None else "avertissement"
    couleur, pastille = ETATS.get(etat, ETATS["avertissement"])
    h = _heures(rec.get("deadline"), maintenant)
    verts = sum(1 for c in (v.checks if v is not None else []) if c.state == "accepté")
    total = len(v.checks) if v is not None else 0
    police = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,"
              "sans-serif")

    alertes_html = "".join(
        f'<li style="margin:0 0 8px;">{_gras(a)}</li>' for a in alertes(rec))

    def titre(t):
        return (f'<p class="sourdine" style="margin:26px 0 10px;font:800 11px/1.4 '
                f'{police};letter-spacing:.1em;text-transform:uppercase;'
                f'color:{GRIS};">{_echap(t)}</p>')

    corps = f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       class="page" style="background:#eef2f7;padding:18px 10px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       class="feuille" style="max-width:600px;width:100%;background:{FOND};
              border-radius:16px;overflow:hidden;">

  <tr><td style="padding:20px 22px 16px;background:{couleur};">
    <table role="presentation" width="100%"><tr>
      <td style="font:800 27px/1.1 {police};color:#ffffff;">GW{rec['gw']}</td>
      <td align="right" style="font:800 12px/1.4 {police};">
        <span style="background:rgba(255,255,255,.22);color:#ffffff;
                     padding:5px 11px;border-radius:999px;">{pastille}</span></td>
    </tr></table>
    <div style="margin-top:5px;font:700 16px/1.4 {police};color:#ffffff;">
      {_echap(_quand(h).capitalize())} pour jouer.</div>
  </td></tr>

  <tr><td style="padding:6px 22px 0;">
    {titre("Ce que tu fais")}
    {_decisions_html(rec)}
  </td></tr>

  <tr><td style="padding:0 22px;">
    {titre("Pourquoi — dans l'ordre")}
    {_chaine_html(rec)}
  </td></tr>

  <tr><td style="padding:0 22px;">
    {titre("Ton onze")}
    {_pelouse(rec)}
  </td></tr>

  <tr><td style="padding:0 22px;">
    {titre("Ce qui te ferait changer d'avis")}
    <ul class="encre" style="margin:0;padding-left:20px;font:400 14px/1.6
               {police};color:{ENCRE};">{alertes_html}</ul>
  </td></tr>

  <tr><td style="padding:0 22px;">
    {titre("Tes ligues")}
    {_ligues_html(rec)}
  </td></tr>

  <tr><td style="padding:20px 22px 24px;">
    <div class="separe" style="border-top:1px solid {TRAIT};padding-top:14px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td class="cadre encre" style="background:{CARTE};
                   border:1px solid {TRAIT};border-radius:10px;
                   padding:11px 14px;font:700 13px/1.4 {police};
                   color:{ENCRE};">{verts}/{total} contrôles au vert</td></tr>
      </table>
      <div class="sourdine" style="margin-top:12px;font:400 12px/1.65 {police};
                  color:{GRIS};">
        Ça veut dire que rien d'anormal n'a été détecté — pas que les
        prévisions sont justes. Aucune constante de ce moteur n'a encore été
        confrontée à un résultat réel. Le premier vrai score arrive après les
        matchs.<br><br>
        {_phrase_pieces(pieces)}<br><br>
        Données connues au {_echap(_date_courte(rec.get('as_of')))}. Prix de
        vente approximé par le prix affiché — vérifie dans l'app avant
        d'exécuter.
      </div>
    </div>
  </td></tr>

</table>
</td></tr></table>"""

    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark">'
            f'<meta name="supported-color-schemes" content="light dark">'
            f'<title>GW{rec["gw"]}</title><style>{STYLE_SOMBRE}</style></head>'
            f'<body class="page" style="margin:0;padding:0;background:#eef2f7;">'
            f'{corps}</body></html>')


def render_texte(rec, maintenant=None, pieces=None):
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
    pj = (("En pièce(s) jointe(s) : " + ", ".join(pieces)
           + " — le rapport complet.") if pieces else
          "Aucune pièce jointe dans cet envoi ; le rapport complet reste sous "
          "data/reports/.")
    out += ["", f"{verts}/{total} contrôles au vert. Rien d'anormal détecté — ce "
                f"n'est pas une preuve que les prévisions sont justes. {pj}",
            f"Données connues au {_date_courte(rec.get('as_of'))}. Prix de vente "
            "approximé par le prix affiché : vérifie dans l'app."]
    return "\n".join(out)
