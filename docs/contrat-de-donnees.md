# Contrat de données de la couche de projection

Ce document dit **exactement** quelles données le moteur consomme, **où** les
prendre, et **ce qui se dégrade** quand elles manquent. Il existe parce que la
qualité d'un top 15 de pré-saison ne dépend pas de l'optimiseur mais des
données qui l'alimentent.

État au 22/08/2026 : depuis l'environnement de développement,
`fantasy.premierleague.com`, `football-data.co.uk` et `fbref.com` répondent
tous `403` au tunnel du proxy sortant. **Aucune donnée réelle n'a pu être
collectée.** Rien n'a été fabriqué pour compenser : les sources absentes sont
signalées comme absentes, dans le code (`priors.availability_report`) et dans
chaque rapport produit.

## 1. Ce que le moteur consomme

| Clé | Source | Sert à | Sans elle |
|---|---|---|---|
| `bootstrap_core` | `GET /api/bootstrap-static/` → `elements[]` : `status`, `chance_of_playing_next_round`, `minutes`, `element_type`, `team`, `now_cost` | disponibilité, minutes observées, quotas, budget | **arrêt** — aucune projection |
| `starts` | même appel → `elements[].starts` | séparer P(titulaire) de P(jouer) | titularisations déduites des minutes (`minutes >= 60`), confiance réduite |
| `set_pieces` | même appel → `penalties_order`, `direct_freekicks_order`, `corners_and_indirect_freekicks_order` | hiérarchie offensive de pré-saison **sans passer par le prix** | priors offensifs plats par poste |
| `xg_xa` | même appel → `expected_goals_per_90`, `expected_assists_per_90` | taux offensifs de la saison en cours (rétrécis) | priors de poste et de rôle seulement |
| `history_past` | `GET /api/element-summary/{element_id}/` → `history_past[]` (un appel public **par joueur**) | **prior de pré-saison** : minutes, titularisations, xG/xA de la saison précédente | **top 15 non exploitable** : plus rien ne distingue deux joueurs d'un même poste |
| `team_reference` | fichier local `data/reference/team_priors.csv` (voir §3) | priors attaque/défense d'équipe, gestion des promus | ratings `strength_*` FPL seuls, statut **[R] non validé** |
| `ep_next` | `GET /api/bootstrap-static/` → `elements[].ep_next` | baseline publique du banc d'essai | repli déterministe défini à l'avance : `selected_by_percent` |

`history_past` est la source critique. C'est elle qui transforme un classement
arbitraire en hiérarchie défendable avant la première journée.

## 2. Ce qu'il faut exécuter depuis une machine qui atteint l'API

### 2.1 Mode hebdomadaire — l'effectif existe déjà

C'est le cas courant en cours de saison. Une seule commande, à lancer **avant
la deadline** et idéalement après les conférences de presse :

```bash
cp config.example.json config.local.json   # une fois : team_id et league_id
python3 -m unittest discover -s tests      # 109 tests, hors ligne, ~15 s
python3 -m fpl_advisor run                 # collecte + décision de la semaine
```

`run` collecte le bootstrap, le calendrier, l'historique live des GW closes,
l'effectif détenu (`entry/<team_id>/event/<gw>/picks/`), le classement de la
mini-ligue et les picks publics des rivaux, puis écrit
`data/reports/GW<n>-recommandation-<horodatage>.md`.

Deux contrôles peuvent bloquer la publication pour une raison qui n'a rien à
voir avec le modèle, et il faut les lire en premier :

- `deadline_actionnable` — la deadline de la GW visée est passée. Le rapport
  n'est plus une décision ; relancer après le changement de GW.
- `fraicheur_snapshot` — la collecte a plus de 24 h (avertissement) ou 72 h
  (blocage). La date vient du manifeste du snapshot, pas de l'heure du
  rapport : relancer `run` plutôt que `advise`.

`advise` seul rejoue la décision sur le dernier snapshot sans recollecter :
utile pour comparer deux lectures, jamais pour décider sur des données vieilles.

**L'effectif détenu n'est lisible qu'après la première deadline passée** — les
picks ne sont publics qu'à partir de ce moment. Avant, la commande s'arrête sur
un `BLOCAGE FACTUEL` explicite plutôt que de deviner.

**Et il ne l'est que pour la dernière GW close.** L'API publique ne rend jamais
l'effectif courant. Conséquence pratique : lancer le conseiller **avant** de
transférer dans l'app. Si un transfert est déjà enregistré pour la GW visée, le
contrôle `effectif_a_jour` bloque — le XI et l'arbitrage porteraient sur une
équipe qui n'existe plus, et aucune lecture publique ne permet de rattraper.

### 2.2 Mode effectif initial — avant la GW1

```bash
# Collecte complète, saisons passées comprises (un GET public par joueur ;
# aucun cookie, aucune authentification, lecture seule)
python3 -m fpl_advisor initial-squad --with-history

# Banc d'essai : effectif interne vs baseline publique, figés côte à côte
python3 -m fpl_advisor initial-bench
```

La première commande écrit un snapshot immuable sous `data/snapshots/<horodatage>/`
et le rapport sous `data/reports/`. La section « Provenance des données et
sources manquantes » du rapport indique, ligne par ligne, ce qui a été
réellement obtenu.

Si `--with-history` échoue partiellement (quelques joueurs en erreur), le
moteur utilise ce qui existe et rétrécit vers le prior de poste pour le reste :
la confiance affichée baisse en conséquence, aucune valeur n'est inventée.

### 2.3 Les saisons passées en cours de saison

`run` ne collecte pas les saisons passées par défaut : c'est un appel public
par joueur (~36 s pour 600 joueurs le 22/08/2026 depuis une connexion
domestique, mais entièrement dépendant du réseau). Les snapshots étant immuables et
indépendants, un run n'hérite jamais des `element-summary` du précédent.

Ce que ça coûte dépend du nombre de journées déjà jouées, et le contrôle
`couverture_donnees` en tient compte :

| Journées jouées | `history_past` absent |
|---|---|
| moins de 3 | **bloque** — la saison en cours ne suffit pas à distinguer deux joueurs d'un même poste, les priors sont plats |
| 3 ou plus | **avertit** — minutes et taux viennent de la saison en cours ; l'absence dégrade la précision sans rendre le classement arbitraire |

En début de saison, il faut donc les collecter au moins une fois **dans un
snapshot hebdomadaire** :

```bash
python3 -m fpl_advisor run --with-history   # un GET public par joueur en plus
```

À partir de la 3ᵉ journée jouée, `run` seul suffit ; le rapport continue de
signaler l'absence en avertissement, jamais en silence.

## 3. Référence d'équipe (facultative, gratuite)

Pour remplacer les ratings `strength_*` FPL — jamais validés par le protocole
J0 — par des priors fondés sur la saison précédente, déposer un CSV ici :

```
data/reference/team_priors.csv
```

Colonnes exactes :

```csv
team_name,goals_for,goals_against,matches,division
Arsenal,69,29,38,1
Sunderland,52,48,46,2
```

- `team_name` : doit correspondre au `name` ou au `short_name` du club dans le
  bootstrap FPL (comparaison insensible à la casse).
- `division` : `1` pour un club de Premier League la saison précédente,
  n'importe quoi d'autre pour un promu.
- Un club présent dans le bootstrap mais **absent du fichier** est traité comme
  promu (priors `PROMOTED_ATTACK` / `PROMOTED_DEFENCE`).

Source gratuite adaptée : les CSV saison de `football-data.co.uk`
(`mmz4281/<saison>/E0.csv` pour la Premier League, `E1.csv` pour le
Championship), agrégés par équipe. Aucune source payante n'est requise et
aucune n'est utilisée.

`docs/exemple-team_priors.csv` donne le format sur deux lignes fictives.

## 4. Ce que le contrat NE couvre pas

Aucune cote de bookmaker, aucune donnée sous abonnement, aucun scraping de
site tiers. Le fichier de référence d'équipe est le seul apport externe, il est
optionnel, local, et fourni par l'utilisateur.

## 5. Statut de calibration

Aucune constante de `fpl_advisor/priors.py` n'a été ajustée sur des résultats
2026/27 : ce sont des ordres de grandeur posés avant observation, marqués
`[H, NON CALIBRÉS]`. Le moteur est **explicite**, il n'est pas **démontré
juste**. La preuve de calibration attendue est celle du banc d'essai —
calibration de `P(60+)` (score de Brier + tableau de fiabilité) et nombre de
joueurs à 0 minute — mesurée après quatre GW réellement jouées.
