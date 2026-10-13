# Calibration GW6 — probabilités annoncées contre réalité

Généré le 2026-10-13 11:24 UTC. Projections figées le 2026-10-09T20:35:00.502114+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20261009T203321Z`. 315/667 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.550 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 562 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 37 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 33 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1045 | plus bas est meilleur |
| Brier de référence | 0.2322 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.550** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 282 | 6 % | 4 % | -2% |
| 20 % – 40 % | 56 | 29 % | 34 % | +5% |
| 40 % – 60 % | 73 | 50 % | 56 % | +6% |
| 60 % – 80 % | 94 | 71 % | 86 % | +15% |
| 80 % – 100 % | 57 | 88 % | 95 % | +7% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 562 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 56 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 50 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1200 | plus bas est meilleur |
| Brier de référence | 0.2463 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.513** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 115 | 5 % | 5 % | +1% |
| 20 % – 40 % | 116 | 27 % | 26 % | -1% |
| 40 % – 60 % | 70 | 50 % | 63 % | +12% |
| 60 % – 80 % | 98 | 70 % | 81 % | +11% |
| 80 % – 100 % | 163 | 88 % | 96 % | +8% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
