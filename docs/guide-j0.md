# Guide J0 — exécution du protocole, identifiants, données lues

Compagnon de `scripts/j0_verification.py` et du dossier de conception (v2).

## 1. Exécuter le protocole J0

Prérequis : Python 3.9+, aucune dépendance externe, aucune connexion à ton compte FPL. Le script est strictement en lecture seule : uniquement des GET sur les endpoints publics, sans identifiant, sans cookie, sans session.

```bash
# Étape 1 — checks automatisés + génération du gabarit manuel
python3 scripts/j0_verification.py

# Étape 2 — ouvrir j0_output/j0_manual.json, et pour chaque règle :
#   ouvrir l'URL "authority" (Help/Rules ou page officielle Premier League),
#   lire la règle, remplir "confirmed": true / false / "h" (+ "note" si utile)

# Étape 3 — finaliser le rapport
python3 scripts/j0_verification.py --manual j0_output/j0_manual.json

# Optionnel, quand les IDs sont connus — vérifie la lisibilité publique :
python3 scripts/j0_verification.py --entry-id 1234567 --league-id 98765
```

Sorties dans `j0_output/` : `j0_report.md` (chaque règle avec source, valeur observée et statut final [F]/[H]/[R]), `snapshots/` (réponses brutes horodatées — premier snapshot point-in-time du projet), `game_settings_dump.json` (tous les paramètres exposés par l'API, pour inspection).

Partage des rôles, conforme au dossier : **les pages officielles Help/Rules et Premier League sont l'autorité pour les règles** (barème, vice-capitaine, revente, BPS, DEFCON…) — elles passent par la section manuelle ; **l'API vérifie les données et paramètres opérationnels** qu'elle expose explicitement (tailles d'effectif, quotas par poste, chips et fenêtres, deadlines mesurées contre les coups d'envoi, unité des prix, schéma des statistiques). Le dossier ne promeut une ligne [F◦] → [F] que sur la foi de ce rapport.

## 2. Retrouver ton team ID

1. Connecte-toi sur `fantasy.premierleague.com` (navigateur).
2. Ouvre l'onglet **Points** (ton équipe d'une GW jouée) — ou **Gameweek History**.
3. Regarde l'URL : `https://fantasy.premierleague.com/entry/1234567/event/1` (ou `/entry/1234567/history`). Le nombre après `/entry/` est ton **team ID** (aussi appelé entry ID).

Remarque : l'onglet « Pick Team » (`/my-team`) n'affiche pas l'ID dans l'URL — passe bien par Points ou History.

## 3. Retrouver l'ID de la mini-ligue

1. Onglet **Leagues & Cups**, clique sur le nom de la ligue privée cible.
2. L'URL devient : `https://fantasy.premierleague.com/leagues/98765/standings/c`. Le nombre après `/leagues/` est l'**ID de la ligue** (`c` = classic).

Transmets aussi, si tu l'as en tête, la liste des managers attendus dans la ligue : elle sert de contrôle de cohérence à la première lecture du classement.

## 4. Données publiques lues pour chaque rival — ni plus, ni moins

Tout ce qui suit est public (accessible sans authentification à quiconque connaît l'ID) et lu en GET uniquement :

| Endpoint | Contenu lu | Usage |
|---|---|---|
| `/api/leagues-classic/{league_id}/standings/` | Classement de la ligue : noms d'équipe et de manager, points, rangs, **entry IDs** des rivaux | Découverte des rivaux, suivi du duel |
| `/api/entry/{entry_id}/` | Profil public : nom d'équipe, nom du manager, points et rang globaux, valeur d'équipe | Fiche rival |
| `/api/entry/{entry_id}/history/` | Points, rang, transferts et coût par GW ; chips joués ; saisons passées | Modèle de politique du rival (chips restants, fréquence de hits, style) |
| `/api/entry/{entry_id}/event/{gw}/picks/` | Les 15 joueurs de la GW, capitaine/vice, ordre du banc, chip actif — **visible uniquement après la deadline de la GW** | EO locale exacte, duel simulé |
| `/api/entry/{entry_id}/transfers/` | Journal public des transferts effectués | Tendances du rival |

Ce qui n'est **jamais** lu ni accessible : les picks de la GW en cours avant sa deadline (personne n'y a accès — nous décidons donc toujours sans voir les choix courants des rivaux, eux non plus), les brouillons d'équipe, les adresses e-mail ou toute donnée de compte, et rien qui nécessite une connexion. Le système ne se connecte jamais à un compte — ni le tien, ni un autre.

Vérification incluse : `--entry-id` / `--league-id` dans le script J0 testent la lisibilité réelle de ces endpoints sur ta ligue (le dossier marque ce point [R] tant que ce test n'a pas tourné — certaines configurations de ligue pourraient restreindre la lecture).
