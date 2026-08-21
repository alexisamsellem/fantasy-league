# Contrat de données de la couche de projection

Ce document dit **exactement** quelles données le moteur consomme, **où** les
prendre, et **ce qui se dégrade** quand elles manquent. Il existe parce que la
qualité d'un top 15 de pré-saison ne dépend pas de l'optimiseur mais des
données qui l'alimentent.

État au 21/08/2026 : depuis l'environnement de développement,
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

```bash
# Collecte complète, saisons passées comprises (~700 GET publics, comptez
# plusieurs minutes ; aucun cookie, aucune authentification, lecture seule)
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
