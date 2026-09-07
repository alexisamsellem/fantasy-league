# Calibration GW3 — probabilités annoncées contre réalité

Généré le 2026-09-07 08:55 UTC. Projections figées le 2026-09-04T16:04:21.261969+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20260904T160345Z`. 307/654 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.461 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 553 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 38 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 32 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1275 | plus bas est meilleur |
| Brier de référence | 0.2364 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.461** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 198 | 5 % | 4 % | -1% |
| 20 % – 40 % | 148 | 26 % | 25 % | -1% |
| 40 % – 60 % | 99 | 51 % | 74 % | +23% |
| 60 % – 80 % | 79 | 70 % | 84 % | +13% |
| 80 % – 100 % | 29 | 83 % | 97 % | +14% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 553 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 56 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 54 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1233 | plus bas est meilleur |
| Brier de référence | 0.2470 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.501** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 60 | 0 % | 2 % | +1% |
| 20 % – 40 % | 141 | 32 % | 15 % | -17% |
| 40 % – 60 % | 91 | 53 % | 51 % | -3% |
| 60 % – 80 % | 181 | 74 % | 88 % | +15% |
| 80 % – 100 % | 80 | 89 % | 99 % | +9% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
