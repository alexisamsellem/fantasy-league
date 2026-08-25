#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit data/reference/team_priors.csv depuis un CSV football-data.co.uk.

Pourquoi un script plutôt qu'un copier-coller : le fichier de référence n'est
utile que si ses noms d'équipe correspondent EXACTEMENT à ceux du bootstrap
FPL. Le moteur apparie sur `name` ou `short_name`, sans tolérance ; un club mal
nommé n'échoue pas, il est silencieusement traité comme promu et reçoit un
prior générique. Un fichier à moitié faux est donc pire qu'un fichier absent —
absent, au moins, c'est signalé.

Ce script fait l'appariement à la source, le montre, et REFUSE d'écrire quand
il n'est pas sûr.

    python3 scripts/build_team_priors.py --e0 ~/Downloads/E0.csv

Source : https://www.football-data.co.uk/englandm.php — CSV « Season <année> »
de la Premier League (E0), gratuit, colonnes HomeTeam/AwayTeam/FTHG/FTAG.
Prendre la saison PRÉCÉDENTE : c'est un prior, pas une observation courante.

Les clubs FPL absents du fichier (les promus) sont laissés dehors : le moteur
leur applique ses priors de promus, c'est le comportement voulu.
"""

import argparse
import csv
import difflib
import json
import sys
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SORTIE = "data/reference/team_priors.csv"
SEUIL_FLOU = 0.82        # en dessous, on ne devine pas : on demande

# Écarts de nommage connus entre football-data.co.uk et FPL. La liste sert de
# raccourci ; tout ce qui n'y est pas passe par l'appariement flou, qui demande
# confirmation. Aucune correspondance n'est inventée en silence.
ALIAS = {
    "man united": "Man Utd", "manchester united": "Man Utd",
    "man city": "Man City", "manchester city": "Man City",
    "tottenham": "Spurs", "tottenham hotspur": "Spurs",
    "newcastle": "Newcastle", "newcastle united": "Newcastle",
    "nott'm forest": "Nott'm Forest", "nottingham forest": "Nott'm Forest",
    "wolves": "Wolves", "wolverhampton": "Wolves",
    "sheffield united": "Sheffield Utd", "leeds united": "Leeds",
    "west brom": "West Brom", "west bromwich albion": "West Brom",
    "brighton": "Brighton", "leicester": "Leicester",
    "west ham": "West Ham", "crystal palace": "Crystal Palace",
    "luton": "Luton", "ipswich": "Ipswich", "southampton": "Southampton",
    "bournemouth": "Bournemouth", "sunderland": "Sunderland",
}


def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    for mot in (" fc", " afc", "."):
        s = s.replace(mot, "")
    return " ".join(s.split())


def clubs_fpl(data_dir):
    """Noms des clubs du dernier snapshot. Sans snapshot, pas d'appariement
    possible — on s'arrête plutôt que d'écrire un fichier invérifiable."""
    racine = Path(data_dir) / "snapshots"
    runs = sorted((d for d in racine.iterdir() if d.is_dir()), reverse=True) \
        if racine.exists() else []
    for run in runs:
        f = run / "bootstrap-static.json"
        if f.exists():
            boot = json.loads(f.read_text(encoding="utf-8"))
            equipes = boot.get("teams") or []
            if equipes:
                return equipes, run
    raise SystemExit(
        f"Aucun bootstrap-static.json sous {racine}. Lancer d'abord une "
        "collecte :\n  python3 -m fpl_advisor run")


def agrege(chemin_e0):
    """Buts marqués, encaissés et matchs joués par club."""
    stats = {}
    with open(chemin_e0, newline="", encoding="utf-8-sig") as fh:
        lignes = list(csv.DictReader(fh))
    manquantes = {"HomeTeam", "AwayTeam", "FTHG", "FTAG"} - set(lignes[0] or {})
    if not lignes or manquantes:
        raise SystemExit(
            f"{chemin_e0} n'a pas le format football-data.co.uk "
            f"(colonnes absentes : {', '.join(sorted(manquantes)) or 'fichier vide'}).")
    for r in lignes:
        dom, ext = (r.get("HomeTeam") or "").strip(), (r.get("AwayTeam") or "").strip()
        try:
            bd, be = int(r["FTHG"]), int(r["FTAG"])
        except (TypeError, ValueError, KeyError):
            continue                      # match non joué : ligne ignorée
        if not dom or not ext:
            continue
        for nom, pour, contre in ((dom, bd, be), (ext, be, bd)):
            s = stats.setdefault(nom, {"gf": 0, "ga": 0, "m": 0})
            s["gf"] += pour
            s["ga"] += contre
            s["m"] += 1
    return stats


def apparie(noms_source, equipes_fpl):
    """{nom football-data: nom FPL} + la liste des incertitudes."""
    par_norme = {}
    for t in equipes_fpl:
        for cand in (t.get("name"), t.get("short_name")):
            if cand:
                par_norme[_norm(cand)] = t.get("name")
    trouves, doutes = {}, []
    for nom in noms_source:
        n = _norm(nom)
        if n in par_norme:
            trouves[nom] = par_norme[n]
            continue
        if n in ALIAS and _norm(ALIAS[n]) in par_norme:
            trouves[nom] = par_norme[_norm(ALIAS[n])]
            continue
        proches = difflib.get_close_matches(n, list(par_norme), 1, SEUIL_FLOU)
        if proches:
            doutes.append((nom, par_norme[proches[0]]))
        # Sinon : club relégué, absent de la PL cette saison. Rien à dire.
    return trouves, doutes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--e0", required=True,
                    help="CSV Premier League de la saison PRÉCÉDENTE "
                         "(football-data.co.uk, mmz4281/<saison>/E0.csv)")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default=SORTIE)
    ap.add_argument("--accepter-approximations", action="store_true",
                    help="valide les rapprochements flous listés par un premier "
                         "passage — à ne cocher qu'après les avoir lus")
    args = ap.parse_args(argv)

    equipes, run = clubs_fpl(args.data_dir)
    print(f"Clubs FPL lus dans {run} : {len(equipes)}")
    stats = agrege(args.e0)
    print(f"Clubs trouvés dans {args.e0} : {len(stats)}")

    trouves, doutes = apparie(stats, equipes)
    if doutes and not args.accepter_approximations:
        print("\nRapprochements INCERTAINS — rien n'a été écrit :")
        for source, fpl in doutes:
            print(f"  « {source} »  ->  « {fpl} » ?")
        print("\nSi ces rapprochements sont justes, relancer avec "
              "--accepter-approximations.\nSinon, corriger les noms dans le CSV "
              "source, ou compléter ALIAS dans ce script.")
        return 1
    for source, fpl in doutes:
        trouves[source] = fpl
        print(f"Rapprochement accepté : « {source} » -> « {fpl} »")

    noms_fpl_couverts = set(trouves.values())
    absents = [t["name"] for t in equipes if t.get("name") not in noms_fpl_couverts]

    chemin = RACINE / args.out if not Path(args.out).is_absolute() else Path(args.out)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["team_name", "goals_for", "goals_against", "matches", "division"])
        for source, fpl in sorted(trouves.items(), key=lambda kv: kv[1]):
            s = stats[source]
            w.writerow([fpl, s["gf"], s["ga"], s["m"], 1])

    print(f"\nÉcrit : {chemin}")
    print(f"{len(trouves)}/{len(equipes)} clubs FPL appariés.")
    if absents:
        print(f"{len(absents)} club(s) sans référence, traités comme promus par "
              f"le moteur : {', '.join(absents)}")
        if len(absents) > 4:
            print("\nATTENTION : plus de 4 clubs sans référence. Une saison de "
                  "Premier League n'en promeut que 3 — au-delà, ce sont "
                  "probablement des noms qui ne correspondent pas. Vérifier "
                  "avant de faire confiance à ce fichier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
