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
aucun réseau requis), `initial-squad` (effectif initial, section suivante).

## Avant la GW1 : construire l'effectif initial

```bash
python3 -m fpl_advisor initial-squad --with-history   # recommandé (voir plus bas)
python3 -m fpl_advisor initial-squad                  # sans les saisons passées
python3 -m fpl_advisor initial-bench                  # banc d'essai vs baseline publique
python3 -m fpl_advisor initial-squad --demo           # synthétique, hors ligne
```

Aucune configuration requise — ni team ID ni ligue : ce mode ne collecte que
des données publiques (bootstrap, calendrier, historique live s'il existe).
Il construit un effectif de 15 joueurs sous les contraintes FPL exactes —
budget 100,0 M£, 2 GB / 5 DEF / 5 MIL / 3 ATT, 3 joueurs maximum par club —
en optimisant une équipe statique (aucun transfert) sur les 4 premières GW à
venir : pour chaque GW, meilleur XI possible + bonus exact du brassard.
Optimisation par montée locale (échanges un-pour-un depuis l'effectif le
moins cher) : optimum local documenté, pas d'optimum global garanti.

Le rapport (`data/reports/GW<n>-effectif-initial-<horodatage>.md`) suit le
même format que le mode hebdomadaire : effectif complet avec EP par GW, XI,
banc ordonné, capitaine + vice (règle FPL exacte), projections, incertitude,
hypothèses [H], déclencheurs de révision, limites. Il ne contient aucune
donnée personnelle. Il ajoute deux sections propres à ce mode :

- **Trois scénarios et stabilité** : les projections sont recalculées sous un
  jeu de priors prudent, central et favorable, et un effectif complet est
  ré-optimisé sous chacun. Le rapport affiche l'amplitude entre scénarios et le
  recouvrement du top 15 ; en dessous de 12 joueurs communs sur 15, l'effectif
  est explicitement déclaré **instable** — une option parmi plusieurs, pas une
  recommandation ferme.
- **Provenance des données** : chaque source du contrat est listée présente ou
  absente, avec ce qui se dégrade sans elle.

`--with-history` ajoute un GET public par joueur (`element-summary`) pour
récupérer les saisons passées. C'est long, et c'est **la** donnée qui rend un
classement de pré-saison défendable : sans elle, les priors sont plats par
poste et le rapport le signale en confiance « faible ». Détail complet dans
`docs/contrat-de-donnees.md`.

### Ce que valent ces projections

La couche de projection rétrécit chaque estimation vers un prior explicite
plutôt que de faire confiance aux petits échantillons : minutes fondées sur les
titularisations observées et la saison précédente (jamais 0 % ni 100 % pour un
joueur disponible), xG/xA rétrécis en continu sans seuil de bascule, hiérarchie
offensive tirée du poste et du rôle sur coups de pied arrêtés plutôt que du
prix, force offensive du club comptée une seule fois, bonus rapporté aux
minutes réellement jouées, DEFCON rétréci vers un prior de poste.

Aucune de ces valeurs de prior n'est calibrée : ce sont des ordres de grandeur
posés avant observation (`[H, NON CALIBRÉ]` dans `fpl_advisor/forecasting/priors.py`). Le
moteur est explicite sur ses sources ; il n'est pas démontré juste. La preuve
attendue vient du banc d'essai.

### Banc d'essai contre une baseline publique

`initial-bench` fige, depuis le même snapshot et avec le même optimiseur, deux
effectifs légaux : celui des projections internes cumulées sur GW1→GW4, et
celui d'une baseline publique naïve (champ officiel `ep_next`, ou repli
déterministe `selected_by_percent` défini à l'avance). Le fichier
`data/reports/GW<n>-banc-essai-initial.json` contient les deux effectifs, les
décisions figées par GW et le protocole de comparaison arrêté **avant** tout
résultat : score cumulé, score hors bonus de capitaine, joueurs à 0 minute et
calibration de `P(60+)` (score de Brier + tableau de fiabilité). C'est cette
dernière métrique qui juge le système, pas l'écart de score sur quatre GW.

## Comment le code est organisé

Trois métiers séparés, dans ce sens et jamais l'inverse :

```
données → forecasting → contrat de projections → evaluation → optimization → rapport
```

- **`fpl_advisor/forecasting/`** — *prévoir les points*. Le seul endroit qui
  transforme des données joueurs et équipes en points espérés (minutes, taux
  offensifs, adversité, bonus, DEFCON, scénarios).
- **`fpl_advisor/evaluation/`** — *vérifier les prévisions*. Rend un verdict
  déterministe — accepté, avertissement ou bloqué — et fournit la baseline
  publique et la mesure de stabilité. Ne choisit aucun joueur.
- **`fpl_advisor/optimization/`** — *optimiser l'équipe*. XI, banc, brassard,
  transferts, effectif initial. Ne lit jamais le snapshot, ne recalcule jamais
  une prévision, ne juge jamais leur crédibilité.

Entre les deux premiers passe un **contrat de projections** sérialisable : on
peut le figer sur disque et rejouer l'optimisation sans snapshot ni recalcul.

```bash
python3 -m fpl_advisor initial-squad --demo --freeze-projections projections.json
python3 -m fpl_advisor initial-squad --from-projections projections.json
```

Si le contrôle qualité **bloque**, l'équipe est quand même calculée pour le
diagnostic, mais le rapport l'appelle « candidat technique » et non
« recommandation ». Détail complet : `docs/architecture.md`.

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
plus les tests du protocole J0 (snapshots immuables, trace probante), ceux du
mode effectif initial (quotas, budget, limite de club, optimum local, rapport,
CLI sans config), les régressions de la couche de projection (prix compté deux
fois, certitude excessive après une apparition, petit échantillon offensif non
rétréci, DEFCON binaire, présélection dominée par la GW1, instabilité non
détectée) et le test d'acceptation du banc d'essai.

Ces tests démontrent des invariants sur des données synthétiques. Ils ne
démontrent **pas** que les projections sont bonnes : cela demande quatre GW
réellement jouées et se mesure avec `initial-bench`.
