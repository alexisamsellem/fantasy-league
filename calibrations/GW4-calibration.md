# Calibration GW4 — probabilités annoncées contre réalité

Généré le 2026-09-15 09:11 UTC. Projections figées le 2026-09-12T11:46:44.763241+00:00 (modèle forecasting/0.3.1, contrat v1.0), issues de `data/snapshots/20260912T114448Z`. 307/659 joueurs ont joué au moins une minute.

**Le point-in-time est la seule chose qui rend ce document valide** : les projections ont été figées AVANT la deadline, les résultats lus APRÈS les matchs. Rejouer le moteur aujourd'hui sur les données d'aujourd'hui ne mesurerait rien.

## Verdict

Score de compétence +0.501 sur cette journée : le moteur bat le taux de base. UNE journée ne démontre pas la calibration — il faut la répétition, et le tableau de fiabilité pour savoir où il se trompe encore.

## P(60+ minutes)

La mesure décisive : elle porte les points de présence, les clean sheets et l'essentiel du risque de capitaine.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 552 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 36 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 35 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1145 | plus bas est meilleur |
| Brier de référence | 0.2295 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.501** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 258 | 8 % | 4 % | -4% |
| 20 % – 40 % | 67 | 30 % | 31 % | +1% |
| 40 % – 60 % | 78 | 52 % | 59 % | +7% |
| 60 % – 80 % | 91 | 69 % | 74 % | +4% |
| 80 % – 100 % | 58 | 87 % | 91 % | +4% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## P(jouer au moins une minute)

Plus facile à prévoir, donc moins discriminante.

| Mesure | Valeur | Lecture |
|---|---|---|
| Joueurs évalués | 552 | 0 exclus (0 sans match cette GW, 0 absents des données observées) |
| Taux de base observé | 56 % | la fréquence réelle dans cette population |
| Probabilité moyenne annoncée | 54 % | un écart avec le taux de base est un biais global |
| Score de Brier | 0.1273 | plus bas est meilleur |
| Brier de référence | 0.2468 | annoncer le taux de base à tout le monde |
| **Score de compétence** | **+0.484** | **négatif = pire que ne rien savoir** |

| Tranche annoncée | Joueurs | Annoncé | Observé | Écart |
|---|---|---|---|---|
| 0 % – 20 % | 99 | 6 % | 3 % | -3% |
| 20 % – 40 % | 89 | 29 % | 17 % | -12% |
| 40 % – 60 % | 83 | 49 % | 55 % | +6% |
| 60 % – 80 % | 192 | 74 % | 82 % | +8% |
| 80 % – 100 % | 89 | 90 % | 96 % | +6% |

Écart positif : le moteur a été trop prudent sur cette tranche. Écart négatif : trop confiant. Une tranche à faible effectif ne dit rien — regarder la colonne « Joueurs » avant de conclure.

## Ce que ce document ne dit pas

Une seule journée ne démontre aucune calibration : elle peut seulement révéler un défaut grossier. La preuve demande la répétition sur plusieurs GW. Aucun paramètre du moteur ne doit être ajusté sur ce seul résultat — corriger un défaut exige de le démontrer sur les données ET de le figer par un test de régression.
