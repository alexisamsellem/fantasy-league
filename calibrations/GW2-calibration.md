# Calibration GW2 — probabilités annoncées contre réalité

Généré le 2026-09-01 09:27 UTC. Projections figées le 2026-08-28T09:19:20.470355+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20260828T091852Z`. 312/626 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.416 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 571 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 37 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 31 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1356 | plus bas est meilleur |
| Brier de référence | 0.2321 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.416** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 212 | 4 % | 4 % | -1% |
| 20 % – 40 % | 157 | 29 % | 29 % | +1% |
| 40 % – 60 % | 110 | 50 % | 67 % | +17% |
| 60 % – 80 % | 70 | 71 % | 86 % | +15% |
| 80 % – 100 % | 22 | 82 % | 95 % | +13% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 571 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 54 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 54 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1505 | plus bas est meilleur |
| Brier de référence | 0.2484 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.394** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 62 | 0 % | 2 % | +2% |
| 20 % – 40 % | 42 | 30 % | 10 % | -20% |
| 40 % – 60 % | 163 | 44 % | 29 % | -14% |
| 60 % – 80 % | 231 | 68 % | 81 % | +12% |
| 80 % – 100 % | 73 | 88 % | 95 % | +6% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
