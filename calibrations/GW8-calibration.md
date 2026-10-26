# Calibration GW8 — probabilités annoncées contre réalité

Généré le 2026-10-26 15:17 UTC. Projections figées le 2026-10-23T13:36:38.457432+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20261023T133452Z`. 303/669 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.473 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 562 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 37 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 33 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1233 | plus bas est meilleur |
| Brier de référence | 0.2340 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.473** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 280 | 6 % | 5 % | -1% |
| 20 % – 40 % | 66 | 30 % | 47 % | +17% |
| 40 % – 60 % | 60 | 50 % | 58 % | +8% |
| 60 % – 80 % | 89 | 71 % | 82 % | +11% |
| 80 % – 100 % | 67 | 87 % | 84 % | -4% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 562 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 54 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 51 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1169 | plus bas est meilleur |
| Brier de référence | 0.2485 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.530** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 164 | 10 % | 4 % | -5% |
| 20 % – 40 % | 62 | 32 % | 31 % | -1% |
| 40 % – 60 % | 83 | 50 % | 61 % | +12% |
| 60 % – 80 % | 94 | 71 % | 79 % | +8% |
| 80 % – 100 % | 159 | 89 % | 96 % | +7% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
