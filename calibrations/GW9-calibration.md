# Calibration GW9 — probabilités annoncées contre réalité

Généré le 2026-11-03 15:18 UTC. Projections figées le 2026-10-31T09:49:45.861338+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20261031T094818Z`. 310/670 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.533 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 563 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 37 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 34 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1085 | plus bas est meilleur |
| Brier de référence | 0.2325 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.533** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 271 | 6 % | 6 % | -0% |
| 20 % – 40 % | 65 | 30 % | 28 % | -3% |
| 40 % – 60 % | 68 | 49 % | 57 % | +8% |
| 60 % – 80 % | 98 | 70 % | 79 % | +8% |
| 80 % – 100 % | 61 | 88 % | 95 % | +7% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 563 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 55 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 51 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1127 | plus bas est meilleur |
| Brier de référence | 0.2474 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.544** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 164 | 10 % | 3 % | -7% |
| 20 % – 40 % | 55 | 32 % | 33 % | +1% |
| 40 % – 60 % | 79 | 50 % | 65 % | +15% |
| 60 % – 80 % | 106 | 70 % | 81 % | +11% |
| 80 % – 100 % | 159 | 89 % | 94 % | +6% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
