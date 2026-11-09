# Calibration GW10 — probabilités annoncées contre réalité

Généré le 2026-11-09 18:55 UTC. Projections figées le 2026-11-06T12:16:25.394875+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20261106T121341Z`. 313/672 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.545 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 564 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 36 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 34 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1051 | plus bas est meilleur |
| Brier de référence | 0.2309 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.545** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 259 | 5 % | 3 % | -2% |
| 20 % – 40 % | 78 | 29 % | 29 % | +1% |
| 40 % – 60 % | 65 | 49 % | 46 % | -3% |
| 60 % – 80 % | 102 | 71 % | 85 % | +15% |
| 80 % – 100 % | 60 | 88 % | 93 % | +6% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 564 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 55 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 51 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1011 | plus bas est meilleur |
| Brier de référence | 0.2470 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.590** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 170 | 10 % | 2 % | -7% |
| 20 % – 40 % | 57 | 31 % | 39 % | +7% |
| 40 % – 60 % | 67 | 52 % | 55 % | +3% |
| 60 % – 80 % | 110 | 71 % | 85 % | +14% |
| 80 % – 100 % | 160 | 89 % | 98 % | +9% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
