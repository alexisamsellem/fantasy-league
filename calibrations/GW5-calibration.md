# Calibration GW5 — probabilités annoncées contre réalité

Généré le 2026-09-21 09:36 UTC. Projections figées le 2026-09-18T16:10:26.936809+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20260918T160930Z`. 302/667 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.549 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 554 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 38 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 34 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1063 | plus bas est meilleur |
| Brier de référence | 0.2358 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.549** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 275 | 7 % | 5 % | -1% |
| 20 % – 40 % | 59 | 30 % | 34 % | +4% |
| 40 % – 60 % | 64 | 52 % | 62 % | +11% |
| 60 % – 80 % | 97 | 70 % | 81 % | +12% |
| 80 % – 100 % | 59 | 88 % | 97 % | +9% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 554 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 54 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 52 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1145 | plus bas est meilleur |
| Brier de référence | 0.2481 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.539** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 110 | 5 % | 3 % | -2% |
| 20 % – 40 % | 101 | 27 % | 17 % | -11% |
| 40 % – 60 % | 78 | 51 % | 60 % | +9% |
| 60 % – 80 % | 71 | 68 % | 76 % | +8% |
| 80 % – 100 % | 194 | 86 % | 93 % | +7% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
