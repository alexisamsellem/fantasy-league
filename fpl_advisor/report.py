# -*- coding: utf-8 -*-
"""Rendu du rapport de recommandation en Markdown lisible.

Le rapport contient des données personnelles (effectif, ligue, noms) : il est
écrit sous data/reports/, ignoré par Git, et ne doit pas être publié tel quel.
"""

from datetime import datetime, timezone
from pathlib import Path

from . import mail, rivals
from .evaluation import quality

POS = {1: "GB", 2: "DEF", 3: "MIL", 4: "ATT"}


def _pct(x):
    return f"{100 * x:.0f} %"


STATUTS = {"a": "", "d": "incertain", "i": "blessé", "s": "suspendu",
           "n": "indisponible", "u": "parti"}


def _alerte(r):
    """Statut officiel FPL et nouvelle associée, en une cellule.

    Un joueur signalé incertain est le fait le plus décisif d'un rapport
    hebdomadaire : il était lu par le moteur mais n'apparaissait nulle part
    dans le tableau du XI."""
    mot = STATUTS.get(r.get("status", "a"), r.get("status", ""))
    news = (r.get("news") or "").strip().replace("|", "/")
    if not mot and not news:
        return "—"
    if len(news) > 70:
        news = news[:67] + "…"
    return " ".join(x for x in (f"**{mot}**" if mot else "", news) if x)


def _row(r, teams):
    return (f"| {r['web_name']} | {POS[r['element_type']]} | "
            f"{teams.get(r['team'], r['team'])} | {r['ep']:.2f} | "
            f"{_pct(r['p_play'])} | {_pct(r['p60'])} | {r['ep_if_start']:.2f} | "
            f"{_alerte(r)} |")


def _xi_lines(xi, teams, title="XI recommandé"):
    lines = [f"\n## {title}",
             "\n| Joueur | Poste | Club | EP | P(jouer) | P(60+) | EP si 90' | Alerte |",
             "|---|---|---|---|---|---|---|---|"]
    order = {1: 0, 2: 1, 3: 2, 4: 3}
    for r in sorted(xi, key=lambda x: (order[x["element_type"]], -x["ep"])):
        lines.append(_row(r, teams))
    return lines


def _minutes_lines(xi):
    """Ce que le moteur a réellement OBSERVÉ pour les titulaires proposés.

    Sans cette ligne, un joueur qui n'a pas joué la GW précédente affiche un
    P(60+) bas, aucune alerte d'infirmerie, et rien n'explique l'écart. Le fait
    était calculé et jeté."""
    absents, remplaces = [], []
    for r in xi:
        obs = r.get("minutes_observed") or {}
        if not obs.get("gws"):
            continue
        if not obs.get("apps"):
            absents.append((r["web_name"], obs))
        elif not obs.get("starts"):
            remplaces.append((r["web_name"], obs))
    if not absents and not remplaces:
        return []
    lines = ["\n**Ce qui a été observé, et pas seulement estimé.** Un `P(60+)` "
             "bas sans alerte d'infirmerie vient presque toujours d'ici : le "
             "joueur n'a pas joué, le moteur l'a vu, et il rétrécit vers sa "
             "saison précédente plutôt que de conclure sur un seul match."]
    if absents:
        lines.append(
            "\n- **Zéro minute** sur les GW observées : "
            + ", ".join(f"{n} (0/{o['gws']} GW)" for n, o in absents)
            + ". Statut officiel disponible : c'est une absence constatée, pas "
              "une blessure déclarée. Vérifier la raison avant la deadline.")
    if remplaces:
        lines.append(
            "\n- **Entré en jeu sans démarrer** : "
            + ", ".join(f"{n} ({o['apps']}/{o['gws']} GW joués, 0 titularisation)"
                        for n, o in remplaces) + ".")
    return lines


def _bench_lines(bench, titre="Banc (dans l'ordre)"):
    lines = [f"\n## {titre}",
             "\n| Rang | Joueur | Poste | EP | P(jouer) |", "|---|---|---|---|---|"]
    for i, r in enumerate(bench, 1):
        lines.append(f"| {i} | {r['web_name']} | {POS[r['element_type']]} | "
                     f"{r['ep']:.2f} | {_pct(r['p_play'])} |")
    lines.append("\nOrdre du banc : remplaçants de champ classés par "
                 "P(jouer) × EP ; le gardien remplaçant occupe le premier slot dédié.")
    return lines


def _armband_lines(band):
    c, v = band["captain"], band["vice"]
    lines = [
        "\n## Capitaine et vice — règle FPL exacte",
        f"\nBonus additionnel du brassard = EP(capitaine) + P(capitaine à 0 min) × EP(vice) "
        f"= {c['ep']:.2f} + {c['p0']:.2f} × {v['ep']:.2f} = **{band['ev']:.2f} pts** "
        "(joueurs supposés indépendants [H]). Le vice n'est doublé que si le "
        "capitaine ne joue aucune minute.",
        "\n| Option capitaine | EP | P(0 min) | Bonus brassard attendu |",
        "|---|---|---|---|",
    ]
    for alt in band["alternatives"]:
        lines.append(f"| {alt['captain']['web_name']} | {alt['captain']['ep']:.2f} | "
                     f"{alt['captain']['p0']:.2f} | {alt['ev']:.2f} |")
    return lines


def _quality_lines(verdict, titre, note_bloquante):
    """Table du contrôle qualité, commune aux deux rapports."""
    lines = [f"\n## {titre}",
             f"\nVerdict : **{verdict.state.upper()}**. {verdict.summary}",
             "\n| Contrôle | État | Détail |", "|---|---|---|"]
    for chk in verdict.checks:
        mark = {"accepté": "accepté", "avertissement": "**avertissement**",
                "bloqué": "**BLOQUÉ**"}[chk.state]
        lines.append(f"| `{chk.key}` | {mark} | {chk.detail} |")
    if verdict.state == "bloqué":
        lines.append("\n> " + note_bloquante)
    return lines


def _scenario_lines(rec):
    """Les décisions de la semaine survivent-elles au changement de priors ?"""
    sc, ag = rec.get("scenarios"), rec.get("agreement")
    if not sc or not ag:
        return []
    n = ag["n_scenarios"]
    lines = [
        "\n## Trois scénarios et stabilité des décisions",
        f"\nMême effectif, mêmes données, trois jeux de priors. Ce qui bouge "
        f"n'est pas l'équipe — elle est détenue — mais ce qu'on en fait. "
        f"Accords avec le scénario {ag['reference']} : capitaine "
        f"{ag['captain_agree']}/{n}, arbitrage transférer/conserver "
        f"{ag['decision_agree']}/{n}, couple sortant/entrant exact "
        f"{ag['swap_agree']}/{n}, XI au minimum "
        f"{ag['xi_min_overlap']}/{ag['xi_size']} joueurs communs.",
        "\n| Scénario | Capitaine | EP | Transfert | Meilleur échange | XI commun |",
        "|---|---|---|---|---|---|",
    ]
    for r in sc:
        lines.append(f"| {r['label']} | {r['captain_name']} | "
                     f"{r['captain_ep']:.2f} | {r['decision']} | "
                     f"{r['swap_label']} | {r['xi_overlap']}/{ag['xi_size']} |")
    lines.append("\nUne décision qui ne survit pas au changement de scénario est "
                 "un tirage au sort entre options équivalentes, pas une "
                 "recommandation — le contrôle qualité ci-dessus la bloque.")
    return lines



def _apres_transfert_lines(ap, teams):
    """Le XI à aligner SI le transfert recommandé est effectué.

    Sans cette section, le rapport montrait le onze de l'effectif AVANT
    l'échange à côté d'un transfert recommandé : le joueur vendu apparaissait
    encore sur le banc affiché, l'entrant nulle part, et la formation pouvait
    être fausse. La feuille de match était donc celle d'une équipe qui
    n'existerait plus (anomalie A6).
    """
    if not ap:
        return []
    d, m, f = (sum(1 for p in ap["xi"] if p["element_type"] == t) for t in (2, 3, 4))
    lines = _xi_lines(
        ap["xi"], teams,
        title=f"XI à aligner SI TU TRANSFÈRES ({d}-{m}-{f}) — "
              f"{ap['out']['web_name']} → {ap['in']['web_name']}")
    mouvements = []
    for r in ap["xi_in"]:
        mouvements.append(f"**{r['web_name']}** entre dans le onze")
    for r in ap["xi_out"]:
        mouvements.append(f"**{r['web_name']}** passe sur le banc")
    if mouvements:
        lines.append("\nCe que l'échange change dans le onze : "
                     + " ; ".join(mouvements) + ".")
    lines += _bench_lines(ap["bench"], titre="Banc après transfert (dans l'ordre)")
    b = ap["armband"]
    if ap["captain_change"]:
        lines.append(
            f"\n> **LE BRASSARD CHANGE AVEC CE TRANSFERT** : capitaine "
            f"**{b['captain']['web_name']}**, vice **{b['vice']['web_name']}** "
            "après l'échange, contre le couple annoncé plus haut sans lui.")
    else:
        lines.append(
            f"\nBrassard inchangé par l'échange : capitaine "
            f"**{b['captain']['web_name']}**, vice **{b['vice']['web_name']}**.")
    return lines


def _une_ligue_lines(v):
    st, em = v["standings"], v["meta"]
    titre = v["name"] or f"ligue {v['id']}"
    lines = [f"\n### {titre}"]
    if st.get("me"):
        pos = (f"\nClassement : **{st['me'].get('rank')}ᵉ sur "
               f"{st['n_managers']}** ; écart au leader : "
               f"**{st['gap_to_leader']} pts**")
        if st.get("gap_to_next"):
            pos += f" ; au manager juste devant : {st['gap_to_next']} pts"
        lines.append(pos + ".")
    lines.append(f"\nLecture de la position : {v['posture']}.")
    lines.append(f"\nPicks publics de la GW{em.get('gw')} (dernière deadline "
                 f"passée) pour {em.get('n_with_picks', 0)}/"
                 f"{em.get('n_rivals', 0)} rivaux. Leurs choix de la GW à venir "
                 "sont inconnus de tous — aucune prétention contraire.")
    if v["exposure"]:
        lines += ["\n| Joueur | EO locale | Capitaines | Je le possède |",
                  "|---|---|---|---|"]
        for r in v["exposure"][:12]:
            lines.append(f"| {r['name']} | {100 * r['eo_local']:.0f} % | "
                         f"{r['captains']} | {'oui' if r['i_own'] else 'NON'} |")
    if st.get("chips_used"):
        used = "; ".join(f"{k} : {', '.join(x)}" for k, x in st["chips_used"].items())
        lines.append(f"\nChips déjà consommés par les rivaux : {used}.")
    return lines


def _league_lines(rec):
    """Une section par mini-ligue, plus les joueurs sur lesquels les ligues
    ne disent pas la même chose.

    Les ligues ne se moyennent pas. Être chasseur proche dans l'une et en
    retard dans l'autre n'appelle pas la même conduite ; fondre les deux en un
    seul chiffre effacerait précisément l'arbitrage à rendre."""
    vues = rec.get("leagues")
    if not vues:
        return []
    lines = ["\n## Mini-ligues — exposition connue des rivaux",
             "\nL'EO locale compte le capitaine double : elle peut dépasser "
             "100 %. Un joueur à forte EO que je ne possède pas est une "
             "position courte contre la ligue ; un joueur à faible EO que je "
             "possède est un pari contre elle."]
    for v in vues:
        lines += _une_ligue_lines(v)

    conflits = rec.get("exposure_conflicts") or []
    if len(vues) > 1:
        lines.append("\n### Là où les ligues ne disent pas la même chose")
        if not conflits:
            lines.append(
                "\nAucun joueur ne change de nature d'une ligue à l'autre "
                f"(seuil : {100 * rivals.EO_CONFLIT:.0f} points d'écart d'EO). "
                "Les deux classements peuvent quand même appeler des conduites "
                "différentes — voir les lectures de position ci-dessus.")
        else:
            lines += ["\n| Joueur | "
                      + " | ".join((v["name"] or str(v["id"])) for v in vues)
                      + " | Écart | Je le possède |",
                      "|" + "---|" * (3 + len(vues))]
            for r in conflits[:10]:
                eos = " | ".join(f"{100 * x:.0f} %" for x in r["eo"])
                lines.append(f"| {r['name']} | {eos} | "
                             f"{100 * r['ecart']:.0f} pts | "
                             f"{'oui' if r['i_own'] else 'NON'} |")
            lines.append(
                "\nCes joueurs ne sont pas le même pari selon la ligue : "
                "posséder un joueur très possédé protège une avance, posséder "
                "un joueur peu possédé creuse un retard. Le moteur ne tranche "
                "pas — il ne sait pas laquelle des deux ligues compte le plus "
                "pour toi.")
    return lines

def render(rec):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    teams = rec["teams"]
    verdict = rec.get("verdict")
    bloque = verdict is not None and verdict.state == "bloqué"
    titre = ("DÉCISION TECHNIQUE — publication refusée" if bloque
             else "conseiller FPL V0")
    lines = [
        f"# Recommandation GW{rec['gw']} — {titre}",
        f"\nGénéré le {now}. Deadline GW{rec['gw']} : {rec['deadline']}. "
        f"Snapshot : `{rec['run_dir']}` (données connues au "
        f"{rec.get('as_of', 'date inconnue')}). Historique de minutes "
        f"disponible : {rec['n_history_gws']} GW. Contrat de projections "
        f"v{rec.get('contract_version', '?')} "
        f"(modèle {rec.get('model_version', '?')}).",
        "\nToutes les décisions restent soumises à validation humaine. "
        "Document local — contient des données personnelles, ne pas publier.",
    ]
    if rec.get("pick_gw"):
        lines.append(
            f"\nEffectif lu dans les picks publics de la GW{rec['pick_gw']} "
            "(dernière deadline passée) : l'API ne rend pas l'effectif courant. "
            "Tout transfert effectué dans l'app depuis rendrait ce rapport "
            "caduc — le contrôle `effectif_a_jour` le vérifie.")
    if rec.get("synthetic"):
        lines.append(
            "\n> **DÉMO SYNTHÉTIQUE — AUCUNE VALEUR DE RECOMMANDATION.** Les "
            "joueurs, clubs et historiques de ce rapport sont fabriqués. Ce "
            "rendu prouve que le pipeline tourne ; il ne dit rien de la "
            "qualité des projections sur données réelles.")
    if rec.get("confidence"):
        lines.append(
            f"\n**Confiance de la couche de projection : "
            f"{rec['confidence'].upper()}** — {rec['confidence_why']}.")

    # Contrôle qualité — décide si l'on a le droit de parler de recommandation.
    if verdict is not None:
        lines += _quality_lines(
            verdict, "Contrôle qualité de la décision",
            "Ces décisions sont un **candidat technique** de la semaine, "
            "calculé pour le diagnostic. Au moins un contrôle bloquant a "
            "échoué : ne pas les jouer telles quelles. Une décision périmée "
            "ou instable se corrige par une nouvelle collecte ou de "
            "meilleures projections, pas par un autre optimiseur.")

    # Synthèse
    band, tr = rec["armband"], rec["transfer"]
    ap = rec.get("apres_transfert")
    d, m, f = (sum(1 for p in rec["xi"] if p["element_type"] == t) for t in (2, 3, 4))
    forme = f"**{d}-{m}-{f}**"
    if ap:
        da, ma, fa = (sum(1 for x in ap["xi"] if x["element_type"] == t)
                      for t in (2, 3, 4))
        if (da, ma, fa) != (d, m, f):
            forme += f" en conservant, **{da}-{ma}-{fa}** en transférant"
    lines += [
        "\n## Synthèse",
        f"- Formation : {forme}",
        f"- Capitaine : **{band['captain']['web_name']}** ; vice : "
        f"**{band['vice']['web_name']}**",
        f"- Transfert : **{tr['decision'].upper()}**"
        + (f" — {tr['candidates'][0]['out']['web_name']} → "
           f"{tr['candidates'][0]['in']['web_name']} "
           f"(+{tr['candidates'][0]['delta3']:.1f} pts sur {tr['horizon']} GW)"
           if tr["decision"] == "transférer" else
           " le transfert gratuit (aucun gain net suffisant identifié)"),
    ]

    titre_xi = "XI calculé (non publiable)" if bloque else "XI recommandé"
    if ap:
        titre_xi += " SI TU CONSERVES"
    lines += _xi_lines(rec["xi"], teams, title=titre_xi)
    lines += _minutes_lines(rec["xi"])
    lines += _bench_lines(rec["bench"])
    lines += _apres_transfert_lines(ap, teams)
    lines += _armband_lines(band)
    lines += _scenario_lines(rec)
    c, v = band["captain"], band["vice"]

    # Transfert
    lines += [
        "\n## Transférer ou conserver",
        f"\nDécision : **{tr['decision'].upper()}** — seuil de bascule : "
        f"+{tr['threshold']:.1f} pts d'espérance cumulée sur {tr['horizon']} GW "
        "[H, seuil à réestimer sur notre propre journal]. "
        f"Banque disponible : {rec['bank'] / 10:.1f} M£.",
    ]
    if tr["candidates"]:
        lines += [f"\n| Sortant | Entrant | Gain sur le XI ({tr['horizon']} GW) | "
                  "Écart individuel | Banque après |",
                  "|---|---|---|---|---|"]
        for cnd in tr["candidates"]:
            lines.append(f"| {cnd['out']['web_name']} | {cnd['in']['web_name']} | "
                         f"+{cnd['delta3']:.2f} | "
                         f"+{cnd.get('delta3_brut', cnd['delta3']):.2f} | "
                         f"{cnd['cost_after'] / 10:.1f} M£ |")
        lines.append(
            "\nLes deux colonnes ne mesurent pas la même chose. **Le gain sur "
            "le XI décide** : c'est ce que l'échange ajoute au meilleur onze de "
            "chaque GW. L'écart individuel compare les points des deux joueurs, "
            "sans regarder qui joue. Quand le sortant est sur le banc, le second "
            "est plus grand que le premier — il compte des points que ce joueur "
            "ne rapportait de toute façon pas. Un écart marqué entre les deux "
            "colonnes signale un échange de banc, pas un renfort du XI.")
        if not tr.get("xi_based", True):
            lines.append(
                "\n> Effectif incomplet : aucune formation légale n'a pu être "
                "construite, le gain affiché retombe sur l'écart individuel.")
    else:
        lines.append("\nAucun échange à gain positif identifié dans la présélection.")
    lines += [
        "\nAvertissements : prix de vente approximé par le prix courant (le vrai "
        "prix de vente dépend du prix d'achat — vérifier dans l'app avant "
        "d'exécuter) ; le stock de transferts gratuits n'est pas exposé "
        "publiquement — cette recommandation suppose 1 transfert gratuit "
        "disponible ; aucun hit (−4) n'est recommandé par la V0.",
    ]

    # Projections, incertitude, hypothèses
    lines += [
        "\n## Projections, incertitude, hypothèses critiques",
        "\nMéthode : minutes probabilistes rétrécies (statut officiel × "
        "titularisations observées, pondérées par récence, rétrécies vers un "
        "prior issu de la saison précédente quand elle est collectée) ; "
        "xG/xA rétrécis en continu vers un prior de poste enrichi du rôle sur "
        "coups de pied arrêtés — aucun seuil de bascule à 180 minutes ; la "
        "force offensive du club n'est ajoutée qu'à hauteur de la part du taux "
        "issue du prior (anti double comptage) ; adversité par faiblesse "
        "défensive de l'adversaire et terrain ; clean sheets en Poisson ; "
        "DEFCON et bonus rétrécis vers des priors de poste (bonus rapporté aux "
        "minutes réellement jouées, non à un nombre d'apparitions approximé). "
        "EP = somme des composantes.",
        "\nIncertitude essentielle : la colonne « EP si 90' » isole le risque de "
        "minutes — un grand écart avec EP signale que la décision dépend surtout "
        "de la titularisation, pas du talent.",
        "\nHypothèses critiques [H] : indépendance entre joueurs (pas de "
        "corrélations de score en V0) ; minutes supposées persistantes sur "
        f"l'horizon de {tr['horizon']} GW ; forces d'équipe FPL comme proxy "
        "d'adversité (pas de cotes en V0) ; seuil de transfert fixe ; barème "
        "codé dans `fpl_advisor/scoring.py` au statut [F◦] tant que le rapport "
        "J0 ne l'a pas confirmé.",
    ]
    thin = [r for r in rec["squad"] if "prior" in r["minutes_basis"]]
    if thin:
        lines.append("\nJoueurs projetés sans historique de minutes exploitable "
                     "(prior de poste, confiance faible) : "
                     + ", ".join(r["web_name"] for r in thin) + ".")

    # Rivaux — une section par mini-ligue, jamais de moyenne entre elles
    lines += _league_lines(rec)

    # Déclencheurs de révision
    lines += ["\n## Événements qui feraient changer ces décisions"]
    if c["p_play"] < 0.9:
        lines.append(f"- Capitaine : P(jouer) de {c['web_name']} = {_pct(c['p_play'])} — "
                     "toute annonce de forfait ou de repos en conférence de presse "
                     f"bascule le brassard vers {v['web_name']}.")
    else:
        lines.append(f"- Capitaine : forfait de {c['web_name']} annoncé avant la "
                     f"deadline → brassard vers {v['web_name']}.")
    if tr["decision"] == "transférer" and tr["candidates"]:
        cnd = tr["candidates"][0]
        lines.append(f"- Transfert : si {cnd['out']['web_name']} est confirmé apte et "
                     f"titulaire en presser, ou si {cnd['in']['web_name']} est "
                     "annoncé incertain → CONSERVER.")
    else:
        lines.append("- Transfert : un forfait dans le XI recommandé avant la "
                     "deadline rouvre la décision (re-lancer le conseiller après "
                     "les conférences de presse).")
    lines.append("- Toute donnée de statut FPL changée (flag blessure) après la "
                 "collecte : re-lancer `python3 -m fpl_advisor run` avant la deadline.")

    # Limites
    lines += [
        "\n## Limites de la V0 — à ne pas surinterpréter",
        "\nPas de cotes de bookmakers, pas de corrélations, pas de simulation de "
        "duel de mini-ligue, pas d'optimisation de chips, pas de hits. Début de "
        "saison : historiques courts, priors grossiers — la calibration des "
        "minutes (niveau 1 du plan d'évaluation) est le premier juge de ce "
        "système, pas ses résultats d'une semaine. L'EO locale décrit la "
        "dernière GW close, pas les choix courants des rivaux.",
    ]
    return "\n".join(lines) + "\n"


def write_report(rec, data_dir="data"):
    out = Path(data_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"GW{rec['gw']}-recommandation-{ts}.md"
    path.write_text(render(rec), encoding="utf-8")
    return path


def pieces_jointes(gw, data_dir="data"):
    """Les rapports de CETTE journée présents sur disque, du plus récent.

    Le mail ne doit annoncer que des pièces jointes qui existent : c'est ce
    que cette fonction établit, plutôt qu'une promesse écrite en dur."""
    out = Path(data_dir) / "reports"
    if not out.exists():
        return []
    noms = []
    for motif in (f"GW{gw}-recommandation-*.md", f"GW{gw}-audit-effectif-*.md"):
        trouves = sorted(out.glob(motif))
        if trouves:
            noms.append(trouves[-1].name)
    return noms


def write_email(rec, data_dir="data", pieces=None):
    """Écrit le mail de la semaine, HTML et texte, à côté du rapport complet.

    Les deux formes sont produites ensemble et jamais séparément : un client
    qui n'affiche que le texte doit recevoir la même décision, pas un résumé
    appauvri.

    `pieces` : les fichiers réellement joints à l'envoi. Par défaut, ceux qui
    existent sur disque pour cette journée — un mail ne doit jamais promettre
    une pièce jointe qui n'arrivera pas."""
    out = Path(data_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    if pieces is None:
        pieces = pieces_jointes(rec["gw"], data_dir)
    base = out / f"GW{rec['gw']}-mail"
    html = base.with_suffix(".html")
    texte = base.with_suffix(".txt")
    html.write_text(mail.render_html(rec, pieces=pieces), encoding="utf-8")
    texte.write_text(mail.render_texte(rec, pieces=pieces), encoding="utf-8")
    (out / f"GW{rec['gw']}-sujet.txt").write_text(mail.sujet(rec), encoding="utf-8")
    return html, texte


def render_initial(rec):
    """Rapport du mode effectif initial — même famille de format que le mode
    hebdomadaire, sans sections équipe/ligue (aucune donnée personnelle)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    teams = rec["teams"]
    gws = rec["horizon"]
    band = rec["armband"]
    c, v = band["captain"], band["vice"]
    verdict = rec.get("verdict")
    bloque = verdict is not None and verdict.state == "bloqué"
    titre = ("CANDIDAT TECHNIQUE — publication refusée" if bloque
             else "conseiller FPL V0")
    lines = [
        f"# Effectif initial GW{rec['gw']} — {titre}",
        f"\nGénéré le {now}. Deadline GW{rec['gw']} : {rec['deadline']}. "
        f"Snapshot : `{rec['run_dir']}`. Historique de minutes disponible : "
        f"{rec['n_history_gws']} GW. Contrat de projections "
        f"v{rec.get('contract_version', '?')} "
        f"(modèle {rec.get('model_version', '?')}).",
        "\nToutes les décisions restent soumises à validation humaine. Ce mode "
        "n'utilise ni team ID ni ligue : données publiques uniquement.",
    ]
    if rec.get("synthetic"):
        lines.append(
            "\n> **DÉMO SYNTHÉTIQUE — AUCUNE VALEUR DE RECOMMANDATION.** Les "
            "joueurs, clubs et historiques de ce rapport sont fabriqués. Ce "
            "rendu prouve que le pipeline tourne ; il ne dit rien de la "
            "qualité des projections sur données réelles.")
    lines.append(
        f"\n**Confiance de la couche de projection : {rec['confidence'].upper()}** "
        f"— {rec['confidence_why']}.")

    # Contrôle qualité — décide si l'on a le droit de parler de recommandation.
    if verdict is not None:
        lines += _quality_lines(
            verdict, "Contrôle qualité des projections",
            "Cet effectif est un **candidat technique**, calculé pour le "
            "diagnostic. Ce n'est pas une recommandation : au moins un "
            "contrôle bloquant a échoué. Le corriger demande de meilleures "
            "données ou de meilleures projections, pas un autre optimiseur.")

    # Synthèse
    d, m, f = (sum(1 for p in rec["xi"] if p["element_type"] == t) for t in (2, 3, 4))
    lines += [
        "\n## Synthèse",
        f"- Budget utilisé : **{rec['cost'] / 10:.1f} M£** sur "
        f"{rec['budget'] / 10:.1f} (banque restante : {rec['bank'] / 10:.1f} M£)",
        f"- Formation GW{rec['gw']} : **{d}-{m}-{f}**",
        f"- Capitaine : **{c['web_name']}** ; vice : **{v['web_name']}**",
        f"- EP totale de l'effectif statique sur les GW{gws[0]}–{gws[-1]} : "
        f"**{rec['value4']:.1f} pts** (meilleur XI par GW + brassard exact, "
        "aucun transfert supposé [H])",
    ]

    # Effectif complet
    header = "| Joueur | Poste | Club | Prix | " \
        + " | ".join(f"EP GW{g}" for g in gws) + " | Total |"
    titre_effectif = ("Candidat technique (15 joueurs)" if bloque
                      else "Effectif recommandé (15 joueurs)")
    lines += [f"\n## {titre_effectif}", "\n" + header,
              "|" + "---|" * (5 + len(gws))]
    order = {1: 0, 2: 1, 3: 2, 4: 3}
    for r in sorted(rec["squad"], key=lambda x: (order[x["element_type"]], -x["ep4"])):
        eps = " | ".join(f"{r['eps'][g]:.2f}" for g in gws)
        lines.append(f"| {r['web_name']} | {POS[r['element_type']]} | "
                     f"{teams.get(r['team'], r['team'])} | {r['now_cost'] / 10:.1f} | "
                     f"{eps} | {r['ep4']:.2f} |")

    lines += _xi_lines(rec["xi"], teams, title=f"XI recommandé (GW{rec['gw']})")
    lines += _minutes_lines(rec["xi"])
    lines += _bench_lines(rec["bench"])
    lines += _armband_lines(band)

    # Scénarios et stabilité du top 15
    sc = rec["scenarios"]
    lines += [
        "\n## Trois scénarios et stabilité de l'effectif",
        "\nL'incertitude n'est pas un habillage d'un chiffre unique : chaque "
        "scénario re-projette tous les joueurs avec un rétrécissement différent "
        "vers les priors, puis RE-OPTIMISE un effectif complet. L'écart entre "
        "scénarios s'ouvre avec l'horizon (l'incertitude croît GW après GW).",
        "\n| Scénario | Effectif optimal du scénario | Effectif recommandé évalué ici | Communs avec le recommandé | Lecture |",
        "|---|---|---|---|---|",
    ]
    for r in sc:
        cv = f"{r['central_value']:.1f}" if r["central_value"] is not None else "n/a"
        lines.append(f"| {r['label']} | {r['own_value']:.1f} pts | {cv} pts | "
                     f"{r['overlap']}/15 | {r['note']} |")
    span = max(r["own_value"] for r in sc) - min(r["own_value"] for r in sc)
    lines.append(
        f"\nAmplitude entre scénario prudent et favorable : **{span:.1f} pts** "
        f"sur {len(gws)} GW. Recouvrement minimal du top 15 : "
        f"**{rec['min_overlap']}/15** (seuil de stabilité : "
        f"{rec['stability_threshold']}/15).")
    if rec["stable"]:
        lines.append(
            "\nEffectif jugé **relativement stable** : le noyau survit aux trois "
            "jeux de priors. Cela ne dit rien de sa justesse — un effectif peut "
            "être stable et faux si les priors sont faux dans le même sens.")
    else:
        lines.append(
            "\n> **EFFECTIF INSTABLE.** Le top 15 change de "
            f"{15 - rec['min_overlap']} joueurs selon le jeu de priors retenu. "
            "Il faut le lire comme UNE option parmi plusieurs équivalentes, pas "
            "comme une recommandation ferme : l'écart entre ces joueurs est "
            "inférieur à l'incertitude du modèle.")

    # Provenance des données
    lines += [
        "\n## Provenance des données et sources manquantes",
        "\n| Source du contrat | Présente | Détail | Ce qui se dégrade sans elle |",
        "|---|---|---|---|",
    ]
    for r in rec["availability"]:
        mark = "oui" if r["present"] else "**NON**"
        lines.append(f"| `{r['key']}` | {mark} | {r['detail']} | {r['without']} |")
    lines.append(f"\nAdversité d'équipe : {rec['team_factor_source']}.")
    absent = [r for r in rec["availability"] if not r["present"]]
    if absent:
        lines.append(
            "\nSources absentes de ce snapshot — à fournir pour rendre le top 15 "
            "défendable :\n" + "\n".join(f"- `{r['key']}` → {r['source']}"
                                          for r in absent))

    # Projections, incertitude, hypothèses
    lines += [
        "\n## Projections, incertitude, hypothèses critiques",
        "\nMéthode : même moteur de projection que le mode hebdomadaire — "
        "minutes probabilistes rétrécies (statut officiel × titularisations "
        "observées × prior de la saison précédente, jamais 0 % ni 100 % pour "
        "un joueur disponible) ; xG/xA rétrécis en continu vers un prior de "
        "poste enrichi du rôle sur coups de pied arrêtés, sans seuil de "
        "bascule ; force offensive du club ajoutée seulement à hauteur de la "
        "part du taux issue du prior (anti double comptage) ; adversité par "
        "faiblesse défensive de l'adversaire et terrain ; clean sheets en "
        "Poisson ; bonus et DEFCON rétrécis vers des priors de poste. "
        "EP = somme des composantes.",
        "\nIncertitude essentielle : la colonne « EP si 90' » isole le risque "
        "de minutes — un grand écart avec EP signale que le choix dépend "
        "surtout de la titularisation, pas du talent.",
        "\nCe qui n'est PAS prouvé : aucune de ces valeurs de prior n'a été "
        "calibrée sur des résultats 2026/27. Le moteur est explicite sur ses "
        "sources, il n'est pas démontré juste. Le juge de niveau 1 reste la "
        "calibration de P(60+) mesurée après coup (voir le banc d'essai : "
        "`python3 -m fpl_advisor initial-bench`).",
        "\nHypothèses critiques [H] : équipe statique (aucun transfert) sur "
        f"l'horizon de {len(gws)} GW ; optimisation par montée locale (échanges "
        "un-pour-un depuis l'effectif le moins cher) — optimum local, pas "
        "d'optimum global garanti ; minutes supposées persistantes ; "
        "indépendance entre joueurs ; forces d'équipe FPL comme proxy "
        "d'adversité ; barème codé dans `fpl_advisor/scoring.py` au statut "
        "[F◦] tant que le rapport J0 ne l'a pas confirmé.",
    ]
    thin = [r for r in rec["squad"] if "prior" in r["minutes_basis"]]
    if thin:
        lines.append("\nJoueurs projetés SANS historique de minutes (prior prix, "
                     "fiabilité faible) : " + ", ".join(r["web_name"] for r in thin) + ".")

    # Déclencheurs de révision
    lines += ["\n## Événements qui feraient changer ces décisions"]
    if c["p_play"] < 0.9:
        lines.append(f"- Capitaine : P(jouer) de {c['web_name']} = {_pct(c['p_play'])} — "
                     "toute annonce de forfait ou de repos en conférence de presse "
                     f"bascule le brassard vers {v['web_name']}.")
    else:
        lines.append(f"- Capitaine : forfait de {c['web_name']} annoncé avant la "
                     f"deadline → brassard vers {v['web_name']}.")
    lines += [
        "- Un flag de blessure ou une annonce de transfert touchant un des 15 "
        "→ re-lancer `python3 -m fpl_advisor initial-squad` avant la deadline.",
        "- Les prix FPL bougent (presque) chaque nuit avant la GW1 : si un "
        "joueur retenu augmente au-delà de la banque restante, l'effectif "
        "n'est plus finançable tel quel — re-lancer la commande.",
    ]

    # Limites
    lines += [
        "\n## Limites de la V0 — à ne pas surinterpréter",
        "\nAvant la première deadline, aucune minute n'a été jouée : les "
        "projections reposent sur les priors par prix et poste, grossiers par "
        "construction. Pas de cotes de bookmakers, pas de corrélations, pas de "
        "planification des transferts futurs ni des chips : l'effectif est "
        "optimisé comme s'il restait figé sur l'horizon, alors qu'un transfert "
        "gratuit par GW existera. La sortie est un point de départ à "
        "confronter aux conférences de presse, pas une vérité.",
    ]
    return "\n".join(lines) + "\n"


def write_initial_report(rec, data_dir="data"):
    out = Path(data_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"GW{rec['gw']}-effectif-initial-{ts}.md"
    path.write_text(render_initial(rec), encoding="utf-8")
    return path


# --------------------------------------------------------- calibration ----

def render_calibration(res):
    """Rapport de calibration. Aucune donnée personnelle : ce document peut
    être partagé tel quel, contrairement au rapport hebdomadaire."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Calibration GW{res['gw']} — probabilités annoncées contre réalité",
        f"\nGénéré le {now}. Projections figées le {res['as_of_projections']} "
        f"(modèle {res['model_version']}, contrat v{res['contract_version']}), "
        f"issues de `{res['snapshot_projections']}`. "
        f"{res['n_ayant_joue']}/{res['n_observes']} joueurs ont joué au moins "
        "une minute.",
        "\n**Le point-in-time est la seule chose qui rend ce document valide** : "
        "les projections ont été figées AVANT la deadline, les résultats lus "
        "APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données "
        "d'aujourd'hui ne mesurerait rien.",
    ]
    if res.get("synthetic"):
        lines.append(
            "\n> **DONNÉES SYNTHÉTIQUES — AUCUNE VALEUR.** Ce rendu prouve que "
            "la mesure tourne ; il ne dit rien du moteur.")

    lines += [f"\n## Verdict\n\n{res['conclusion']}"]

    for m in res["metriques"].values():
        lines += [f"\n## {m['label']}", f"\n{m['note'].capitalize()}."]
        if not m["assez"]:
            lines.append(f"\nÉchantillon de {m['n']} joueurs — insuffisant pour "
                         "conclure. Rien n'est interprété ici.")
        exclus = m["sans_match"] + m["non_observes"]
        lines += [
            "\n| Mesure | Valeur | Lecture |", "|---|---|---|",
            f"| Joueurs évalués | {m['n']} | "
            f"{exclus} exclus ({m['sans_match']} sans match cette GW, "
            f"{m['non_observes']} absents des données observées) |",
            f"| Taux de base observé | {_pct(m['taux_base'] or 0)} | "
            "la fréquence réelle dans cette population |",
            f"| Probabilité moyenne annoncée | {_pct(m['annonce_moyenne'] or 0)} | "
            "un écart avec le taux de base est un biais global |",
            f"| Score de Brier | {m['brier']:.4f} | plus bas est meilleur |"
            if m["brier"] is not None else "| Score de Brier | — | |",
            f"| Brier de référence | {m['brier_reference']:.4f} | "
            "annoncer le taux de base à tout le monde |"
            if m["brier_reference"] is not None else "| Brier de référence | — | |",
            f"| **Score de compétence** | **{m['competence']:+.3f}** | "
            "**négatif = pire que ne rien savoir** |"
            if m["competence"] is not None else "| Score de compétence | — | |",
        ]
        lines += [
            "\n| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |",
            "|---|---|---|---|---|",
        ]
        for b in m["fiabilite"]:
            if not b["n"]:
                lines.append(f"| {_pct(b['lo'])} – {_pct(b['hi'])} | 0 | — | — "
                             "| tranche inutilisée |")
                continue
            lines.append(
                f"| {_pct(b['lo'])} – {_pct(b['hi'])} | {b['n']} | "
                f"{_pct(b['annonce'])} | {_pct(b['observe'])} | "
                f"{b['ecart']:+.0%} |")
        lines.append(
            "\nÉcart positif : le moteur a été trop prudent sur cette tranche. "
            "Écart négatif : trop confiant. Une tranche à faible effectif ne "
            "dit rien — regarder la colonne « Joueurs » avant de conclure.")

    lines += [
        "\n## Ce que ce document ne dit pas",
        "\nUne seule journée ne démontre aucune calibration : elle peut "
        "seulement révéler un défaut grossier. La preuve demande la répétition "
        "sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur "
        "ce seul résultat — corriger un défaut exige de le démontrer sur les "
        "données ET de le figer par un test de régression.",
    ]
    return "\n".join(lines) + "\n"


def write_calibration(res, data_dir="data"):
    out = Path(data_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"GW{res['gw']}-calibration-{ts}.md"
    path.write_text(render_calibration(res), encoding="utf-8")
    return path


# ------------------------------------------------------------- audit ----

def _audit_table(rows, teams, gws, titre, vide):
    """Table joueur → prix → EP par GW → total. Rend la ligne « vide » quand
    la liste l'est : une section absente et une section vide ne se lisent pas
    pareil."""
    lines = [f"\n### {titre}"]
    if not rows:
        return lines + [f"\n{vide}"]
    lines += ["\n| Joueur | Poste | Club | Prix | "
              + " | ".join(f"EP GW{g}" for g in gws) + " | Total | Alerte |",
              "|" + "---|" * (6 + len(gws))]
    order = {1: 0, 2: 1, 3: 2, 4: 3}
    for r in sorted(rows, key=lambda x: (order[x["element_type"]], -x["ep4"])):
        eps = " | ".join(f"{r['eps'][g]:.2f}" for g in gws)
        lines.append(f"| {r['web_name']} | {POS[r['element_type']]} | "
                     f"{teams.get(r['team'], r['team'])} | {r['now_cost'] / 10:.1f} | "
                     f"{eps} | {r['ep4']:.2f} | {_alerte(r)} |")
    return lines


def render_audit(rec):
    """Rapport de l'audit d'effectif comparatif.

    Contient l'effectif détenu : données personnelles, écrit sous data/reports/
    et jamais publiable tel quel."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    teams, gws = rec["teams"], rec["horizon"]
    verdict = rec.get("verdict")
    bloque = verdict is not None and verdict.state == "bloqué"
    retard, chemin = rec["retard"], rec["chemin"]

    titre = ("AUDIT TECHNIQUE — publication refusée" if bloque
             else "audit d'effectif comparatif")
    lines = [
        f"# Effectif GW{rec['gw']}–GW{gws[-1]} — {titre}",
    ]

    # Le verdict d'abord : le chiffre qui décide, avant tout tableau.
    if retard is None:
        lines.append(
            "\n> **ÉCART NON CALCULABLE.** L'effectif détenu n'a pas pu être "
            "projeté en entier — voir le contrôle qualité ci-dessous.")
    else:
        lines.append(
            f"\n> **Retard de l'effectif détenu : {retard:.1f} pts sur "
            f"{len(gws)} GW** ({rec['valeur_detenue']:.1f} contre "
            f"{rec['valeur_ideale']:.1f} pour l'effectif que le moteur "
            f"achèterait à la même valeur d'équipe). Recouvrement : "
            f"**{rec['recouvrement']}/15 joueurs** en commun.")
        if chemin:
            part = rec["part_rattrapee"]
            part_txt = f" soit **{part:.0%}** de l'écart" if part is not None else ""
            lines.append(
                f"\n> Un transfert gratuit par semaine pendant "
                f"{rec['semaines']} semaines en récupère "
                f"**{chemin['gain_total']:.1f} pts**{part_txt} — "
                f"{len(chemin['etapes'])} échange(s) trouvé(s).")

    lines += [
        f"\nGénéré le {now}. Deadline GW{rec['gw']} : {rec['deadline']}. "
        f"Snapshot : `{rec['run_dir']}` (connu au {rec['as_of']}). Historique "
        f"de minutes disponible : {rec['n_history_gws']} GW. Contrat de "
        f"projections v{rec.get('contract_version', '?')} "
        f"(modèle {rec.get('model_version', '?')}).",
        "\nToutes les décisions restent soumises à validation humaine.",
        "\n> **CE QUE CET AUDIT N'EST PAS.** Reconstruire un effectif de zéro "
        "ignore le coût des transferts : l'écart ci-dessus n'est atteignable "
        "qu'en quinze transferts simultanés, c'est-à-dire avec un wildcard. Il "
        "mesure OÙ le modèle diverge de l'équipe détenue, pas ce qu'il faut "
        "faire cette semaine. Le chemin de transferts en fin de rapport est la "
        "seule partie actionnable — et sa première étape est la seule à "
        "reposer sur des projections encore fraîches.",
        "\n> **Prix de vente approximés par le prix affiché.** L'API publique "
        "ne donne pas le prix d'achat : la valeur d'équipe reconstituée ici "
        "peut être légèrement optimiste, et un échange annoncé faisable peut ne "
        "pas l'être dans l'application. Vérifier avant d'agir.",
        "\n> **L'écart est un minorant, pas un optimum.** L'effectif "
        "reconstruit sort d'une montée locale, lancée depuis deux points de "
        "départ (l'effectif le moins cher et l'effectif détenu) et gardant le "
        "meilleur des deux. Elle s'arrête au premier sommet atteint : il existe "
        "peut-être mieux. Un écart nul dit donc « le moteur n'a pas trouvé "
        "mieux », pas « il n'y a rien de mieux » (anomalie A5).",
    ]
    if rec.get("synthetic"):
        lines.append(
            "\n> **DÉMO SYNTHÉTIQUE — AUCUNE VALEUR DE RECOMMANDATION.** Les "
            "joueurs, clubs et historiques de ce rapport sont fabriqués.")
    lines.append(
        f"\n**Confiance de la couche de projection : {rec['confidence'].upper()}** "
        f"— {rec['confidence_why']}.")

    if verdict is not None:
        lines += _quality_lines(
            verdict, "Contrôle qualité des projections",
            "Cet audit est un **diagnostic technique**. Ce n'est pas une "
            "recommandation : au moins un contrôle bloquant a échoué. Les "
            "chiffres ci-dessous restent calculés pour comprendre l'écart, pas "
            "pour agir dessus.")

    # Synthèse chiffrée
    lines += [
        "\n## Synthèse",
        f"- Valeur d'équipe reconstituée : **{rec['budget'] / 10:.1f} M£** "
        f"({rec['cout_detenu'] / 10:.1f} M£ d'effectif + "
        f"{rec['bank'] / 10:.1f} M£ en banque) — pour mémoire, budget de "
        f"départ FPL : {rec['budget_initial'] / 10:.1f} M£",
        f"- Effectif reconstruit : **{rec['cout_ideal'] / 10:.1f} M£** engagés "
        f"sur les {rec['budget'] / 10:.1f} disponibles",
    ]
    if retard is not None:
        lines += [
            f"- EP de l'effectif **détenu** sur GW{gws[0]}–GW{gws[-1]} : "
            f"**{rec['valeur_detenue']:.1f} pts**",
            f"- EP de l'effectif **reconstruit** : **{rec['valeur_ideale']:.1f} pts**",
            f"- **Écart : {retard:.1f} pts** sur {len(gws)} GW, soit "
            f"{retard / len(gws):.1f} pts par journée",
        ]
    lines.append(
        "\nLes deux valeurs sont calculées de la même façon : meilleur XI de "
        "chaque GW + bonus exact du brassard, aucun transfert supposé en cours "
        "de route. C'est la mesure qui décide, jamais la somme des points "
        "individuels — un remplaçant qui ne joue pas ne rapporte rien à "
        "l'équipe (anomalie A2).")

    # Divergence par poste
    lines += [
        "\n## Où le modèle diverge",
        "\n| Poste | En commun | Détenus écartés | Retenus non détenus |",
        "|---|---|---|---|",
    ]
    for et in (1, 2, 3, 4):
        v = rec["par_poste"][et]
        sortants = ", ".join(r["web_name"] for r in v["detenus_ecartes"]) or "—"
        entrants = ", ".join(r["web_name"] for r in v["retenus_non_detenus"]) or "—"
        lines.append(f"| {POS[et]} | {v['communs']} | {sortants} | {entrants} |")

    lines += _audit_table(
        rec["detenus_ecartes"], teams, gws,
        "Joueurs détenus que le moteur n'achèterait pas",
        "Aucun : le moteur rachèterait l'effectif à l'identique.")
    lines += _audit_table(
        rec["retenus_non_detenus"], teams, gws,
        "Joueurs retenus par le moteur et non détenus",
        "Aucun.")

    # Chemin de transferts
    lines += ["\n## Chemin de transferts proposé"]
    if not chemin or not chemin["etapes"]:
        lines.append(
            "\nAucun échange un-pour-un n'améliore la valeur de l'effectif sous "
            "ces projections. Ce n'est pas un satisfecit : l'écart mesuré plus "
            "haut peut rester grand et n'être atteignable qu'en plusieurs "
            "transferts simultanés.")
    else:
        lines += [
            f"\nUn transfert gratuit par semaine, {rec['semaines']} semaines, "
            "sans hit (hors périmètre V0). Chaque étape prend l'échange qui "
            "ajoute le plus à la valeur de l'effectif, puis repart de l'équipe "
            "obtenue.",
            "\n| Semaine | Sortant | Entrant | Gain | Cumul | Banque après | "
            f"> seuil hebdo ({chemin['seuil_hebdomadaire']:.1f}) |",
            "|---|---|---|---|---|---|---|",
        ]
        for e in chemin["etapes"]:
            o, i = e["out"], e["in_"]
            lines.append(
                f"| {e['semaine']} | {o['web_name']} ({POS[o['element_type']]}, "
                f"{o['now_cost'] / 10:.1f}) | {i['web_name']} "
                f"({POS[i['element_type']]}, {i['now_cost'] / 10:.1f}) | "
                f"+{e['gain']:.2f} | +{e['cumul']:.2f} | "
                f"{e['banque_apres'] / 10:.1f} M£ | "
                f"{'oui' if e['au_dessus_du_seuil'] else 'NON'} |")
        if len(chemin["etapes"]) < rec["semaines"]:
            lines.append(
                f"\nLa montée s'arrête après {len(chemin['etapes'])} échange(s) : "
                "plus aucun un-pour-un n'améliore la valeur.")
        lines += [
            "\n> **Lire ce tableau dans l'ordre, et s'arrêter tôt.** Les "
            "projections sont les mêmes à chaque étape : les prix ne bougent "
            "pas, les blessures n'arrivent pas, et la GW la plus lointaine "
            "n'est pas re-projetée. La semaine 1 est une recommandation ; les "
            "suivantes sont une direction. Relancer l'audit chaque semaine "
            "plutôt que de dérouler ce plan.",
            "\n> C'est aussi une montée locale : la meilleure séquence de "
            f"{rec['semaines']} transferts n'est pas forcément la suite des "
            f"{rec['semaines']} meilleurs transferts pris un par un. La colonne "
            "« > seuil hebdo » indique si l'étape passerait le seuil de "
            "l'arbitrage hebdomadaire — une étape en dessous ne justifie pas "
            "de brûler un transfert.",
        ]

    # Stabilité de l'effectif reconstruit
    sc = rec["scenarios"]
    lines += [
        "\n## Stabilité de l'effectif reconstruit",
        "\nL'écart chiffré plus haut ne vaut que si l'effectif « idéal » ne "
        "change pas avec le jeu de priors retenu. Chaque scénario re-projette "
        "tous les joueurs puis RE-OPTIMISE un effectif complet à la même valeur "
        "d'équipe.",
        "\n| Scénario | Effectif optimal du scénario | Effectif reconstruit évalué ici | Communs | Lecture |",
        "|---|---|---|---|---|",
    ]
    for r in sc:
        cv = f"{r['central_value']:.1f}" if r["central_value"] is not None else "n/a"
        lines.append(f"| {r['label']} | {r['own_value']:.1f} pts | {cv} pts | "
                     f"{r['overlap']}/15 | {r['note']} |")
    lines.append(
        f"\nRecouvrement minimal : **{rec['min_overlap']}/15** (seuil de "
        f"stabilité : {quality.STABILITY_MIN_OVERLAP}/15). En dessous du seuil, "
        "l'effectif reconstruit est UNE option parmi plusieurs équivalentes, et "
        "l'écart chiffré mesure surtout le choix d'un prior.")

    # Effectifs complets
    lines += _audit_table(rec["owned"], teams, gws,
                          "Effectif détenu (15 joueurs)", "Effectif illisible.")
    lines += _audit_table(rec["rebuilt"], teams, gws,
                          "Effectif reconstruit (15 joueurs)", "Non calculé.")

    lines += [
        "\n## Limites",
        "- **Aucune constante de ce moteur n'est calibrée.** Les seuils et les "
        "priors sont posés à la main [H] ; l'écart chiffré est celui d'un "
        "modèle non prouvé, pas une vérité.",
        "- L'audit suppose l'effectif détenu figé pendant les "
        f"{len(gws)} GW pour le comparer à un effectif lui aussi figé. Les deux "
        "côtés sont donc pénalisés de la même façon par l'absence de "
        "transferts : c'est ce qui rend la comparaison lisible, et ce qui la "
        "rend théorique.",
        "- Ni chips, ni hits, ni prix de vente réels, ni évolution des prix.",
        "- Un effectif stable et un écart faible ne démontrent pas que le "
        "moteur a raison. Seule la calibration, mesurée après coup sur des "
        "projections figées avant la deadline, tranchera.",
    ]
    if rec["missing_ids"]:
        lines.append(
            f"- **{len(rec['missing_ids'])} joueur(s) détenu(s) absent(s) du "
            f"contrat de projections** ({', '.join(rec['missing_names'])}) : "
            "tout chiffre ci-dessus est faux d'autant de joueurs.")
    return "\n".join(lines) + "\n"


def write_audit(rec, data_dir="data"):
    out = Path(data_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"GW{rec['gw']}-audit-effectif-{ts}.md"
    path.write_text(render_audit(rec), encoding="utf-8")
    return path
