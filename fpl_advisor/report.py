# -*- coding: utf-8 -*-
"""Rendu du rapport de recommandation en Markdown lisible.

Le rapport contient des données personnelles (effectif, ligue, noms) : il est
écrit sous data/reports/, ignoré par Git, et ne doit pas être publié tel quel.
"""

from datetime import datetime, timezone
from pathlib import Path

POS = {1: "GB", 2: "DEF", 3: "MIL", 4: "ATT"}


def _pct(x):
    return f"{100 * x:.0f} %"


def _row(r, teams):
    return (f"| {r['web_name']} | {POS[r['element_type']]} | "
            f"{teams.get(r['team'], r['team'])} | {r['ep']:.2f} | "
            f"{_pct(r['p_play'])} | {_pct(r['p60'])} | {r['ep_if_start']:.2f} |")


def _xi_lines(xi, teams, title="XI recommandé"):
    lines = [f"\n## {title}",
             "\n| Joueur | Poste | Club | EP | P(jouer) | P(60+) | EP si 90' |",
             "|---|---|---|---|---|---|---|"]
    order = {1: 0, 2: 1, 3: 2, 4: 3}
    for r in sorted(xi, key=lambda x: (order[x["element_type"]], -x["ep"])):
        lines.append(_row(r, teams))
    return lines


def _bench_lines(bench):
    lines = ["\n## Banc (dans l'ordre)",
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


def render(rec):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    teams = rec["teams"]
    lines = [
        f"# Recommandation GW{rec['gw']} — conseiller FPL V0",
        f"\nGénéré le {now}. Deadline GW{rec['gw']} : {rec['deadline']}. "
        f"Snapshot : `{rec['run_dir']}`. Historique de minutes disponible : "
        f"{rec['n_history_gws']} GW.",
        "\nToutes les décisions restent soumises à validation humaine. "
        "Document local — contient des données personnelles, ne pas publier.",
    ]

    # Synthèse
    band, tr = rec["armband"], rec["transfer"]
    d, m, f = (sum(1 for p in rec["xi"] if p["element_type"] == t) for t in (2, 3, 4))
    lines += [
        "\n## Synthèse",
        f"- Formation : **{d}-{m}-{f}**",
        f"- Capitaine : **{band['captain']['web_name']}** ; vice : "
        f"**{band['vice']['web_name']}**",
        f"- Transfert : **{tr['decision'].upper()}**"
        + (f" — {tr['candidates'][0]['out']['web_name']} → "
           f"{tr['candidates'][0]['in']['web_name']} "
           f"(+{tr['candidates'][0]['delta3']:.1f} pts sur {tr['horizon']} GW)"
           if tr["decision"] == "transférer" else
           " le transfert gratuit (aucun gain net suffisant identifié)"),
    ]

    lines += _xi_lines(rec["xi"], teams)
    lines += _bench_lines(rec["bench"])
    lines += _armband_lines(band)
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
        lines += ["\n| Sortant | Entrant | Δ EP (3 GW) | Banque après |",
                  "|---|---|---|---|"]
        for cnd in tr["candidates"]:
            lines.append(f"| {cnd['out']['web_name']} | {cnd['in']['web_name']} | "
                         f"+{cnd['delta3']:.2f} | {cnd['cost_after'] / 10:.1f} M£ |")
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
        "\nMéthode : minutes probabilistes (statut officiel × historique récent "
        "pondéré, ou prior par prix sans historique) ; buts/assists par xG/xA "
        "par 90 officiels (ou prior par poste et prix si < 180 minutes) ajustés "
        "par un modèle d'équipe multiplicatif sur les forces FPL ; clean sheets "
        "en Poisson ; DEFCON empirique sur les comptages CBIT officiels ; bonus "
        "au taux saisonnier. EP = somme des composantes.",
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
        lines.append("\nJoueurs projetés SANS historique de minutes (prior prix, "
                     "fiabilité faible) : " + ", ".join(r["web_name"] for r in thin) + ".")

    # Rivaux
    em, st = rec["exposure_meta"], rec["standings"]
    lines += ["\n## Mini-ligue — exposition connue des rivaux"]
    if st.get("me"):
        lines.append(f"\nClassement : {st['me'].get('rank')}ᵉ sur {st['n_managers']} ; "
                     f"écart au leader : {st['gap_to_leader']} pts.")
    lines.append(f"\nPicks publics de la GW{em.get('gw')} (dernière deadline passée) "
                 f"pour {em.get('n_with_picks', 0)}/{em.get('n_rivals', 0)} rivaux. "
                 "Leurs choix de la GW à venir sont inconnus de tous — aucune "
                 "prétention contraire.")
    if rec["exposure"]:
        lines += ["\n| Joueur | EO locale | Capitaines | Je le possède |",
                  "|---|---|---|---|"]
        lines.insert(-2, "\nL'EO locale compte le capitaine double : elle peut "
                         "dépasser 100 %. Un joueur à forte EO que je ne possède "
                         "pas est une position courte contre la ligue.")
        for r in rec["exposure"][:12]:
            eo = f"{100 * r['eo_local']:.0f} %"
            lines.append(f"| {r['name']} | {eo} | {r['captains']} | "
                         f"{'oui' if r['i_own'] else 'NON'} |")
    if st.get("chips_used"):
        used = "; ".join(f"{k} : {', '.join(v)}" for k, v in st["chips_used"].items())
        lines.append(f"\nChips déjà consommés par les rivaux : {used}.")

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


def render_initial(rec):
    """Rapport du mode effectif initial — même famille de format que le mode
    hebdomadaire, sans sections équipe/ligue (aucune donnée personnelle)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    teams = rec["teams"]
    gws = rec["horizon"]
    band = rec["armband"]
    c, v = band["captain"], band["vice"]
    lines = [
        f"# Effectif initial GW{rec['gw']} — conseiller FPL V0",
        f"\nGénéré le {now}. Deadline GW{rec['gw']} : {rec['deadline']}. "
        f"Snapshot : `{rec['run_dir']}`. Historique de minutes disponible : "
        f"{rec['n_history_gws']} GW.",
        "\nToutes les décisions restent soumises à validation humaine. Ce mode "
        "n'utilise ni team ID ni ligue : données publiques uniquement.",
    ]

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
    lines += ["\n## Effectif recommandé (15 joueurs)", "\n" + header,
              "|" + "---|" * (5 + len(gws))]
    order = {1: 0, 2: 1, 3: 2, 4: 3}
    for r in sorted(rec["squad"], key=lambda x: (order[x["element_type"]], -x["ep4"])):
        eps = " | ".join(f"{r['eps'][g]:.2f}" for g in gws)
        lines.append(f"| {r['web_name']} | {POS[r['element_type']]} | "
                     f"{teams.get(r['team'], r['team'])} | {r['now_cost'] / 10:.1f} | "
                     f"{eps} | {r['ep4']:.2f} |")

    lines += _xi_lines(rec["xi"], teams, title=f"XI recommandé (GW{rec['gw']})")
    lines += _bench_lines(rec["bench"])
    lines += _armband_lines(band)

    # Projections, incertitude, hypothèses
    lines += [
        "\n## Projections, incertitude, hypothèses critiques",
        "\nMéthode : même moteur de projection que le mode hebdomadaire — "
        "minutes probabilistes (statut officiel × historique récent pondéré, "
        "ou prior par prix sans historique) ; buts/assists par xG/xA par 90 "
        "officiels (ou prior par poste et prix si < 180 minutes) ajustés par "
        "un modèle d'équipe multiplicatif sur les forces FPL ; clean sheets "
        "en Poisson ; bonus au taux saisonnier. EP = somme des composantes.",
        "\nIncertitude essentielle : la colonne « EP si 90' » isole le risque "
        "de minutes — un grand écart avec EP signale que le choix dépend "
        "surtout de la titularisation, pas du talent.",
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
