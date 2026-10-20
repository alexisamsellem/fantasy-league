# Calibration GW7 — probabilités annoncées contre réalité

Généré le 2026-10-20 18:32 UTC. Projections figées le 2026-10-17T07:36:45.524893+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20261017T073617Z`. 305/668 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.564 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 562 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 36 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 34 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.0998 | plus bas est meilleur |
| Brier de référence | 0.2292 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.564** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 271 | 6 % | 4 % | -1% |
| 20 % – 40 % | 68 | 30 % | 18 % | -13% |
| 40 % – 60 % | 64 | 50 % | 61 % | +11% |
| 60 % – 80 % | 88 | 70 % | 80 % | +9% |
| 80 % – 100 % | 71 | 87 % | 94 % | +7% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 562 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 54 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 51 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1304 | plus bas est meilleur |
| Brier de référence | 0.2483 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.475** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 165 | 10 % | 8 % | -2% |
| 20 % – 40 % | 61 | 32 % | 36 % | +4% |
| 40 % – 60 % | 71 | 50 % | 56 % | +6% |
| 60 % – 80 % | 107 | 71 % | 74 % | +3% |
| 80 % – 100 % | 158 | 89 % | 94 % | +5% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
