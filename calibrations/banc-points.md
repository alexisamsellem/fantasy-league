# Banc d'essai sur les points — moteur contre `ep_next`

Généré le 2026-10-19 15:06 UTC par `scripts/banc_points.py`. Journées notées : GW2, GW3, GW4, GW5, GW6.

**Ce qui est comparé.** Pour chaque journée, le dernier contrat figé AVANT la deadline porte deux prévisions de la même date : `ep` (le moteur, scénario central) et `ep_next` (FPL, stocké dans le même fichier). Les deux sont confrontées aux points FPL réels (`total_points` du live, journée validée `data_checked`).

**Comment l'incertitude est mesurée.** Δ = perte(moteur) − perte(ep_next) : négatif = le moteur se trompe moins. IC 95 % par bootstrap apparié (10000 répliques) qui rééchantillonne des couples (GW, équipe), parce que les joueurs d'un même match ne sont pas indépendants. Contre-épreuve : Diebold-Mariano sur la série des écarts par journée (Student, n−1 ddl). Verdict « oui » seulement si les deux concluent au seuil de 5 %.

## Verdict — tous les joueurs ayant un match

- **Erreur quadratique** : Δ = -1.199, IC 95 % bootstrap par grappes [-1.597 ; -0.806] ; Diebold-Mariano t = -3.76 (4 ddl), p = 0.020 → **oui**
- **Erreur absolue** : Δ = -0.107, IC 95 % [-0.162 ; -0.056] ; DM t = -2.84, p = 0.047 → **oui**

| GW | Joueurs | MSE moteur | MSE ep_next | Δ MSE | IC 95 % Δ | MAE moteur | MAE ep_next | Biais moteur | Biais ep_next |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 571 | 5.192 | 6.038 | -0.846 | [-1.159 ; -0.584] | 1.379 | 1.583 | -0.03 | +0.07 |
| 3 | 553 | 4.680 | 6.793 | -2.113 | [-3.146 ; -1.064] | 1.347 | 1.520 | -0.08 | +0.07 |
| 4 | 552 | 5.588 | 6.187 | -0.599 | [-1.473 ; +0.255] | 1.446 | 1.467 | -0.06 | +0.00 |
| 5 | 554 | 5.593 | 6.216 | -0.623 | [-1.537 ; +0.357] | 1.355 | 1.377 | -0.18 | -0.15 |
| 6 | 562 | 4.800 | 6.616 | -1.816 | [-2.912 ; -0.819] | 1.272 | 1.386 | -0.08 | +0.01 |
| **toutes** | 2792 | 5.170 | 6.369 | **-1.199** | **[-1.597 ; -0.806]** | 1.360 | 1.467 | -0.09 | +0.00 |

## Joueurs envisageables (max(ep, ep_next) ≥ 2)

Sous-population définie sur les prévisions, jamais sur le résultat : elle retire la masse des joueurs que personne n'alignerait et que les deux prévisions donnent à ~0.

- **Erreur quadratique** : Δ = -2.566, IC 95 % bootstrap par grappes [-3.501 ; -1.649] ; Diebold-Mariano t = -3.11 (4 ddl), p = 0.036 → **oui**
- **Erreur absolue** : Δ = -0.383, IC 95 % [-0.505 ; -0.265] ; DM t = -3.79, p = 0.019 → **oui**

| GW | Joueurs | MSE moteur | MSE ep_next | Δ MSE | IC 95 % Δ | MAE moteur | MAE ep_next | Biais moteur | Biais ep_next |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 276 | 8.502 | 9.583 | -1.080 | [-1.669 ; -0.589] | 1.939 | 2.094 | -0.30 | -0.37 |
| 3 | 224 | 9.068 | 14.320 | -5.252 | [-7.673 ; -2.717] | 2.112 | 2.856 | -0.56 | +0.44 |
| 4 | 237 | 11.132 | 12.578 | -1.446 | [-3.522 ; +0.505] | 2.419 | 2.710 | -0.48 | +0.21 |
| 5 | 223 | 10.414 | 11.753 | -1.340 | [-3.576 ; +1.118] | 2.280 | 2.558 | -0.57 | +0.09 |
| 6 | 229 | 7.301 | 11.385 | -4.084 | [-6.779 ; -1.593] | 2.024 | 2.528 | -0.21 | +0.62 |
| **toutes** | 1189 | 9.260 | 11.826 | **-2.566** | **[-3.501 ; -1.649]** | 2.148 | 2.531 | -0.42 | +0.18 |

## Traçabilité

| GW | Contrat | Figé le | Deadline | Modèle | Résultats lus le | Exclus |
|---|---|---|---|---|---|---|
| 2 | `projections-GW2.json.gz` | 2026-08-28T09:19:20.470355+00:00 | 2026-08-28T17:30:00Z | forecasting/0.3.1 | 2026-10-19T15:04:58Z | sans_match 0, non_observes 0, ep_next 0 |
| 3 | `projections-GW3.json.gz` | 2026-09-04T16:04:21.261969+00:00 | 2026-09-04T17:30:00Z | forecasting/0.3.1 | 2026-10-19T15:04:59Z | sans_match 0, non_observes 0, ep_next 0 |
| 4 | `projections-GW4.json.gz` | 2026-09-12T11:46:44.763241+00:00 | 2026-09-12T12:30:00Z | forecasting/0.3.1 | 2026-10-19T15:04:59Z | sans_match 0, non_observes 0, ep_next 0 |
| 5 | `projections-GW5.json.gz` | 2026-09-18T16:10:26.936809+00:00 | 2026-09-18T17:30:00Z | forecasting/0.3.1 | 2026-10-19T15:04:59Z | sans_match 0, non_observes 0, ep_next 0 |
| 6 | `projections-GW6.json.gz` | 2026-10-09T20:35:00.502114+00:00 | 2026-10-10T10:00:00Z | forecasting/0.3.1 | 2026-10-19T15:04:59Z | sans_match 0, non_observes 0, ep_next 0 |

## Ce que ce document ne dit pas

- 5 journées seulement : Diebold-Mariano n'a que 4 degrés de liberté. Le bootstrap par grappes est plus puissant mais suppose les équipes indépendantes entre elles au sein d'une journée, ce qui est faux pour les deux équipes d'un même match.
- `ep_next` est un repère grossier (forme récente). Le battre est le minimum, pas une preuve de qualité absolue.
- L'erreur moyenne sur ~550 joueurs ne mesure pas directement la qualité des DÉCISIONS (capitaine, transfert), qui se jouent sur une dizaine de joueurs en haut du classement.
