# EXEMPLE ILLUSTRATIF — Rapport J0 attendu (valeurs fictives)

> Ce fichier montre la forme du rapport que produit `scripts/j0_verification.py`
> après une exécution complète réussie. **Toutes les valeurs sont fictives** et
> servent uniquement à illustrer le format ; le vrai rapport est généré
> localement dans `j0_output/j0_report.md` et ne contient ni ID complet ni nom
> de manager.

# Rapport J0 — vérification des faits réglementaires

Généré le 2026-08-22 09:15 UTC. Lecture seule, endpoints publics uniquement, aucun identifiant.
Autorité des règles : pages officielles Help/Rules et Premier League. L'API vérifie les paramètres opérationnels qu'elle expose explicitement ; une ligne « Observation » constate une régularité mesurée et ne prouve pas la règle générale, confirmée à part en section manuelle.
Partage : ce rapport ne contient ni ID complet, ni nom de manager — il est transmissible tel quel. Les snapshots (`snapshots/`) contiennent les données réelles : ils restent locaux et ne sont jamais commités ni transmis.

## Checks automatisés (API officielle)

| Règle | Source | Valeur observée | Statut |
|---|---|---|---|
| API FPL publique accessible sans authentification | https://fantasy.premierleague.com/api/bootstrap-static/ | accessible (snapshot enregistré) | [F] |
| Effectif de 15 joueurs, XI de 11, max 3 par club | …/bootstrap-static/ (game_settings) | squadsize=15, squadplay=11, team_limit=3 | [F] |
| Quotas 2 GB / 5 DEF / 5 MIL / 3 ATT ; XI : 1 GB, ≥3 DEF, ≥1 ATT | …/bootstrap-static/ (element_types) | select={GKP:2, DEF:5, MID:5, FWD:3}, min_play={GKP:1, DEF:3, MID:2, FWD:1}, … | [F] |
| Budget initial 100,0 M£ | …/bootstrap-static/ (game_settings) | champ non exposé — confirmer sur Help/Rules (section manuelle) | [R] |
| 1 transfert gratuit/GW, cumul maximal 5 | …/bootstrap-static/ (game_settings) + Help/Rules | champ non exposé — règle → autorité Help/Rules (section manuelle) | [R] |
| 2 WC, 2 FH, 2 BB, 2 TC ; jeu 1 jusqu'à GW19, jeu 2 dès GW20 | …/bootstrap-static/ (chips) + page officielle | [('3xc', 1, 19), ('3xc', 20, 38), ('bboost', 1, 19), …] | [F] |
| Observation : écart deadline → premier coup d'envoi, mesuré sur toutes les GW programmées | …/bootstrap-static/ (events) + …/fixtures/ | écarts observés (min) sur 38 GW : [90] — observation cohérente — la règle générale reste à confirmer sur Help/Rules (ligne manuelle deadline_rule) | [F] |
| Prix exprimés en pas de 0,1 M£ | …/bootstrap-static/ (elements) + page officielle | 743 joueurs ; now_cost ∈ [38, 145] — mécanique de variation et revente → autorité page officielle (manuel) | [F] |
| L'API expose des statistiques de contribution défensive par joueur | …/bootstrap-static/ (element_stats) + …/event/{gw}/live/ | element_stats=['clearances_blocks_interceptions', 'recoveries', 'tackles', 'defensive_contribution'] ; live GW1=[…] — noms exacts à figer dans le modèle | [F] |
| Équipe <ID masqué …42> lisible sans authentification (profil, historique, picks post-deadline) | …/entry/<ID>/ … | /entry/<ID>/ → OK ; /entry/<ID>/history/ → OK ; /entry/<ID>/event/1/picks/ → OK — ID masqué dans ce rapport | [F] |
| Mini-ligue <ID masqué …17> lisible sans authentification (classement + entry IDs des rivaux) | …/leagues-classic/<ID>/standings/ | OK — 12 managers en page 1 — aucun nom ni ID dans ce rapport | [F] |

## Confirmations manuelles (autorité : pages officielles)

Un [F] exige la trace probante complète : `url_consulted`, `page_title_or_section`, `verified_on`, `confirmed_statement`. Un `confirmed: true` sans ces champs reste [R].

| Règle | Source | Valeur observée | Statut |
|---|---|---|---|
| Le vice-capitaine ne prend le brassard que si le capitaine joue 0 minute | https://fantasy.premierleague.com/help/rules | 2026-08-22 — section « Captains » — énoncé confirmé : « If your captain plays 0 minutes, the captaincy will pass to your vice-captain » (formulation fictive d'exemple) | [F] |
| Règle générale : deadline à 90 minutes avant le premier coup d'envoi | https://fantasy.premierleague.com/help/rules | 2026-08-22 — section « Deadlines » — énoncé confirmé : « … 90 minutes before the kick-off time in the first match of the Gameweek » (exemple) | [F] |
| DEFCON : 2 pts si CBIT ≥ 10 (DEF) / CBIRT ≥ 12 (MIL-ATT), plafond 2 pts | page officielle DEFCON | confirmed=true SANS trace probante — un [F] exige URL, titre/section, date et énoncé confirmé — reste [R] | [R] |
| BPS 2026/27 rééquilibré (chevauchement DEFCON réduit, …) | page officielle | requalifié en hypothèse — 2026-08-22 — section « Bonus » — la page décrit un principe sans les barèmes chiffrés | [H] |
| Cumul maximal de 5 transferts gratuits | https://fantasy.premierleague.com/help/rules | non confirmé (champ 'confirmed' vide) — ouvrir la source et répondre, trace à l'appui | [R] |

## Bilan : 12 × [F], 1 × [H], 4 × [R] sur 17 règles.
Tout [R] exige une action : corriger le dossier, ou documenter pourquoi la vérification reste impossible. Le dossier ne promeut une ligne [F◦] → [F] que sur la foi de ce rapport.
