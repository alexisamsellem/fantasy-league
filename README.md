# fantasy-league — conseiller FPL Classic (V0)

Agent de décision Fantasy Premier League en mode **conseiller** : lecture seule,
données publiques gratuites, validation humaine de toute décision. Objectif
principal : gagner une mini-ligue privée ; le rang global sert de benchmark.
Le cadrage complet est dans `dossier-conception-agent-fpl.md`.

## Le rituel avant chaque deadline (5 minutes)

```bash
# 0. Une seule fois : configuration locale (jamais commitée)
cp config.example.json config.local.json   # y mettre team_id et league_id
pip install duckdb                          # seule dépendance optionnelle

# 1. Avant chaque deadline (idéalement après les conférences de presse) :
python3 -m unittest discover -s tests && python3 -m fpl_advisor run
```

`run` collecte les données publiques FPL (snapshot immuable horodaté sous
`data/snapshots/`), met à jour `data/fpl.duckdb`, puis écrit la recommandation
dans `data/reports/GW<n>-recommandation-<horodatage>.md` : XI, banc ordonné,
capitaine + vice (règle FPL exacte), transférer vs conserver, projections,
incertitude, hypothèses, déclencheurs de révision, exposition des rivaux
(picks publics de la dernière GW close uniquement).

Un flag de blessure tombe après la collecte ? Relancer la même commande :
chaque exécution repart des données fraîches sans écraser les snapshots
précédents.

Autres commandes : `collect` (collecte seule), `advise` (recommandation depuis
le dernier snapshot), `demo` (bout-en-bout sur données 100 % synthétiques,
aucun réseau requis).

## Où trouver team_id et league_id

Voir `docs/guide-j0.md` (section 2 et 3) : les deux se lisent dans les URLs de
`fantasy.premierleague.com` une fois connecté. Le protocole J0
(`scripts/j0_verification.py`) vérifie les règles du jeu à la source officielle
avant de faire confiance au barème codé dans `fpl_advisor/scoring.py`.

## Données personnelles et sécurité

Tout ce qui contient team ID, ID de ligue, noms de managers ou snapshots réels
vit sous `data/` et `config.local.json` — ignorés par Git (`.gitignore`).
Aucune interaction avec FPL n'est authentifiée : GET publics uniquement, aucun
cookie, aucune écriture côté FPL.

## Limites assumées de la V0

Pas de cotes de bookmakers, pas de corrélations entre joueurs, pas de
simulation de duel de mini-ligue, pas d'optimisation de chips, pas de hits ;
prix de vente approximé par le prix courant et stock de transferts gratuits
supposé égal à 1 (non exposés publiquement). En début de saison, les
historiques sont courts et les priors grossiers : le premier juge du système
est la calibration des minutes (section 12 du dossier), pas le score d'une
semaine. Les durcissements reportés sont listés dans `docs/backlog-v0.md`.

## Tests

```bash
python3 -m unittest discover -s tests
```

Hors ligne, sans dépendance : contraintes du XI vérifiées contre une recherche
exhaustive, formule du brassard, modèle de minutes, seuil de transfert,
EO locale (capitaine double), bout-en-bout complet sur le jeu synthétique,
plus les tests du protocole J0 (snapshots immuables, trace probante).
