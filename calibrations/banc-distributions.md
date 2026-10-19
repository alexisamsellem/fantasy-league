# Distributions simulées — CRPS sur les journées figées

Généré le 2026-10-19 15:24 UTC par `scripts/banc_distributions.py` (1000 tirages par journée). Journées : GW2, GW3, GW4, GW5, GW6.

**CRPS** (continuous ranked probability score) : E|X − y| − ½ E|X − X'|, où X est tiré de la prévision et y le résultat. Plus bas est meilleur. Il récompense une distribution à la fois centrée et de la bonne largeur ; pour une prévision ponctuelle, il vaut l'erreur absolue — c'est ce qui rend les trois prévisions comparables sur la même échelle.

Δ = CRPS(simulé) − CRPS(référence) : négatif = la distribution gagne. IC 95 % bootstrap apparié par grappes (GW, équipe) ; Diebold-Mariano sur les journées ; « oui » seulement si les deux concluent.

## Par joueur

| Comparaison | n | CRPS simulé | CRPS référence | Δ | IC 95 % | DM p | Le simulé gagne ? | Δ GW2 | Δ GW3 | Δ GW4 | Δ GW5 | Δ GW6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| simulé vs trois scénarios | 2792 | 0.903 | 1.279 | -0.376 | [-0.397 ; -0.355] | 0.000 | **oui** | -0.400 | -0.381 | -0.413 | -0.355 | -0.328 |
| simulé vs espérance seule | 2792 | 0.903 | 1.360 | -0.456 | [-0.479 ; -0.434] | 0.000 | **oui** | -0.479 | -0.464 | -0.499 | -0.433 | -0.405 |

## Par équipe — somme des 11 meilleurs EP

C'est ici que l'aléa partagé se juge : sur un joueur seul, buts partagés ou non donnent la même loi ; sur une somme, la corrélation élargit la distribution.

| Comparaison | n | CRPS simulé | CRPS référence | Δ | IC 95 % | DM p | Le simulé gagne ? | Δ GW2 | Δ GW3 | Δ GW4 | Δ GW5 | Δ GW6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| simulé vs trois scénarios | 100 | 8.782 | 10.467 | -1.686 | [-2.195 ; -1.171] | 0.010 | **oui** | -1.875 | -0.450 | -1.759 | -2.736 | -1.608 |
| simulé vs espérance seule | 100 | 8.782 | 11.816 | -3.034 | [-3.629 ; -2.426] | 0.002 | **oui** | -2.909 | -1.590 | -3.322 | -4.242 | -3.107 |
| buts partagés vs indépendants | 100 | 8.782 | 8.969 | -0.188 | [-0.410 ; +0.028] | 0.230 | **non prouvé** | -0.304 | +0.298 | -0.159 | -0.495 | -0.279 |

## Ce que ce document ne dit pas

- Les trois scénarios sont trois jeux de priors, pas trois issues de match : les battre en CRPS est attendu. L'espérance seule est la référence la plus dure ici, parce qu'elle porte toute l'information du moteur.
- L'apport de l'aléa partagé n'est mesuré que sur des sommes par équipe ; 20 équipes × 5 journées, c'est 100 observations.
- La simulation hérite des P(60+) figés (modèle 0.3.1, avant la recalibration A10) : elle juge la forme de la loi, pas la recalibration.
