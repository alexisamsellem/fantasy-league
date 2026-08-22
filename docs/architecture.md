# Architecture : prévoir, vérifier, optimiser

Le dépôt fait trois choses très différentes, qu'il est facile de confondre.
Les séparer, c'est pouvoir améliorer l'une sans casser les autres.

## Les trois métiers, en une phrase chacun

| Couche | La question posée | Ce qu'elle produit |
|---|---|---|
| **`forecasting`** — prévoir les points | « Combien de points ce joueur va-t-il marquer ? » | un contrat de projections |
| **`evaluation`** — vérifier les prévisions | « A-t-on le droit d'appeler ça une recommandation ? » | un verdict : accepté, avertissement ou bloqué |
| **`optimization`** — optimiser l'équipe | « Quelle est la meilleure équipe possible pour ces points ? » | un effectif, un XI, un capitaine |

Une analogie : le forecasting est le météorologue, l'evaluation est le
contrôleur qui décide si le bulletin est assez fiable pour être diffusé, et
l'optimization est celui qui organise le pique-nique en fonction du bulletin.
Le dernier ne regarde jamais le ciel lui-même, et il ne décide pas non plus si
la météo est digne de confiance.

## Le sens de circulation

```
données et snapshots
        ↓
   forecasting          seul endroit qui transforme des données en prévisions
        ↓
contrat de projections  frontière figée, sérialisable en JSON
        ↓
   evaluation           juge les prévisions, ne choisit aucun joueur
        ↓
   optimization         choisit les joueurs, ne juge rien
        ↓
     rapport
```

Une flèche ne remonte jamais. Concrètement :

- `forecasting` n'importe ni `evaluation` ni `optimization` ;
- `evaluation` n'importe pas `optimization` ;
- `optimization` ne connaît ni le snapshot, ni l'API, ni le moteur de prévision.

Ces trois règles sont vérifiées par des tests qui lisent le code source
(`tests/test_architecture.py`, classe `DirectionDesDependancesTests`).

### Le cas gênant, et comment il est résolu

Mesurer la stabilité du top 15 demande de ré-optimiser une équipe sous chaque
scénario. L'évaluation aurait donc « besoin » de l'optimiseur, ce qui
inverserait la flèche. On inverse plutôt la dépendance : l'évaluation déclare
l'interface dont elle a besoin (`evaluation/backend.py`, cinq fonctions), et
l'appelant lui fournit l'implémentation réelle (`fpl_advisor/wiring.py`).
Un test peut donc injecter un sélecteur factice et vérifier les verdicts sans
faire tourner le vrai optimiseur.

## Le contrat de projections

C'est le seul objet qui traverse la frontière. Pour chaque joueur et chaque
Gameweek, il porte : identifiant, GW, points espérés, probabilité de zéro
minute, probabilité de jouer 60 minutes ou plus, détail des composantes
(présence, buts, passes, clean sheet, arrêts, DEFCON, bonus, malus), les trois
scénarios, un niveau de confiance, la provenance de chaque estimation. Au
niveau du fichier : version du contrat, version du modèle, date de
connaissance des données, horizon, snapshot d'origine et couverture des
sources.

Il ne contient **aucune donnée brute** : ni `bootstrap`, ni `fixtures`, ni
`live`, ni historique. Un test le vérifie.

```bash
# Figer les projections dans un fichier
python3 -m fpl_advisor initial-squad --demo --freeze-projections projections.json

# Reconstruire exactement le même effectif, sans snapshot ni recalcul
python3 -m fpl_advisor initial-squad --from-projections projections.json
```

Le rapport produit par le second appel est identique au premier, à
l'horodatage près. C'est la preuve opérationnelle que la frontière tient.

## Les deux modes passent par le même chemin

Le dépôt prend deux sortes de décisions, avec la même mécanique :

| | Mode effectif initial (`initial.py`) | Mode hebdomadaire (`weekly.py`) |
|---|---|---|
| Question | quels 15 joueurs acheter avant la GW1 ? | que faire cette semaine de l'effectif que j'ai ? |
| Horizon | 4 GW | 3 GW |
| Ce qui est optimisé | l'effectif entier | le brassard, le XI, transférer ou conserver |
| Ce qui est mesuré | recouvrement du top 15 entre scénarios | accord des décisions entre scénarios |
| Porte qualité | `quality.assess` | `quality.assess_weekly` |

L'effectif détenu est une **donnée personnelle** : il n'entre jamais dans le
contrat de projections, qui reste public et publiable. Il est passé à part, en
simples identifiants, par `advise.py`.

## Le contrôle qualité

`evaluation/quality.py` rend un verdict déterministe en trois états, à partir
du contrat et de faits simples sur ce qui est proposé. Le module ne lit jamais
l'horloge tout seul : l'heure de décision lui est passée, pour que le verdict
reste reproductible.

Contrôles du mode effectif initial :

| Contrôle | Bloque quand |
|---|---|
| `couverture_donnees` | confiance des données « faible » ou source obligatoire absente |
| `fallbacks_faibles` | 70 % ou plus des joueurs reposent sur un repli faible |
| `stabilite_top15` | moins de 12 joueurs communs sur 15 entre scénarios |
| `priors_plats` | 60 % ou plus du top 15 classé sur un prior de poste plat |
| `legalite_fpl` | budget, quotas ou limite de club violés |
| `budget_utilise` | moins de 85,0 M£ engagés |
| `capitaine_plausible` | capitaine sous 30 % de chances de jouer 60 minutes |
| `baseline_publique` | (avertissement seulement) recouvrement ≤ 2/15 |

Contrôles du mode hebdomadaire (`fallbacks_faibles` est commun ;
`couverture_donnees` est relu : voir la note sous la table) :

| Contrôle | Bloque quand |
|---|---|
| `deadline_actionnable` | la deadline de la GW visée est déjà passée |
| `fraicheur_snapshot` | la collecte a plus de 72 heures (avertissement dès 24) |
| `effectif_lisible` | un joueur détenu est absent du contrat (radié, identifiant inconnu) |
| `capitaine_plausible` | capitaine sous 30 % de chances de jouer 60 minutes |
| `stabilite_capitaine` | moins de 2 scénarios sur 3 désignent le même capitaine |
| `stabilite_transfert` | moins de 2 scénarios sur 3 concluent au même arbitrage |
| `stabilite_echange` | moins de 2 scénarios sur 3 visent le même couple sortant/entrant |
| `stabilite_xi` | (avertissement seulement) moins de 10 titulaires communs sur 11 |

Les deux premiers n'existent qu'à la semaine, et c'est volontaire : avant la
GW1 une collecte de la veille est sans conséquence, alors qu'en cours de saison
elle ignore les blessures, les conférences de presse et les changements de
prix. Une recommandation publiée après la deadline n'est plus une décision.

`couverture_donnees` est le même contrôle dans les deux modes, à une nuance
près. Avant la GW1, l'absence des saisons passées rend le classement entre
joueurs d'un même poste arbitraire : elle bloque. En cours de saison, passé
trois journées jouées, minutes et taux viennent de la saison en cours ; elle
devient un avertissement. Sans cette nuance, `run` — qui ne collecte pas les
~700 `element-summary` — serait bloqué toutes les semaines pour un critère qui
ne s'applique qu'à la pré-saison.

Ces seuils sont des **règles de publication**, pas des paramètres de modèle :
les changer ne modifie aucune projection.

Quand le verdict est **bloqué**, l'équipe ou la décision est toujours calculée
— on en a besoin pour diagnostiquer — mais le rapport l'appelle **candidat
technique** (effectif) ou **décision technique** (semaine), et non
recommandation, dès son titre.

## Ce qui reste volontairement hors périmètre

`--from-projections` n'existe pas pour le mode hebdomadaire. Rejouer une
semaine depuis un contrat figé demanderait aussi l'effectif détenu, qui est
une donnée personnelle et reste par construction hors du contrat. Le figeage
(`--freeze-projections`) fonctionne dans les deux modes : il produit la trace
auditable de ce que le moteur croyait au moment de la décision, sans jamais
transporter de donnée personnelle.
