# Calibration GW11 — probabilités annoncées contre réalité

Généré le 2026-11-24 23:31 UTC. Projections figées le 2026-11-20T20:32:01.660071+00:00 (modèle forecasting/0.4.0, contrat v1.0), issues de `data/snapshots/20261120T203038Z`. 313/674 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.461 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 566 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 36 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 37 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1240 | plus bas est meilleur |
| Brier de référence | 0.2300 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.461** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 264 | 4 % | 5 % | +1% |
| 20 % – 40 % | 54 | 29 % | 28 % | -1% |
| 40 % – 60 % | 66 | 49 % | 50 % | +1% |
| 60 % – 80 % | 57 | 71 % | 70 % | -1% |
| 80 % – 100 % | 125 | 90 % | 81 % | -9% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 566 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 55 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 54 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.0997 | plus bas est meilleur |
| Brier de référence | 0.2472 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.597** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 183 | 6 % | 4 % | -2% |
| 20 % – 40 % | 41 | 31 % | 39 % | +8% |
| 40 % – 60 % | 47 | 48 % | 55 % | +7% |
| 60 % – 80 % | 56 | 70 % | 77 % | +6% |
| 80 % – 100 % | 239 | 93 % | 92 % | -1% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
