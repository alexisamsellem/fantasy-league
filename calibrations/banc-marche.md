# Le marché comme juge — probabilités d'équipe

Généré le 2026-10-19 15:16 UTC par `scripts/banc_marche.py`. Journées : GW2, GW3, GW4, GW5, GW6, 50 matchs, 100 côtés de match.

**Moteur** : λ de buts lu exactement dans les contrats figés avant la deadline (composante clean sheet = P(60+) × e^(−λ) × 4). **Marché** : cotes moyennes football-data.co.uk (`AvgH/D/A`, `Avg>2.5/<2.5`, relevées avant le match), marge retirée par normalisation, puis les deux λ de Poisson qui reproduisent P(domicile), P(extérieur) et P(+2,5 buts). **Juge** : log-loss sur les scores réels (FPL et football-data concordants). Δ = moteur − marché : négatif = le moteur gagne. IC 95 % bootstrap par match ; Diebold-Mariano sur les journées.

| Mesure | Log-loss moteur | Log-loss marché | Δ | IC 95 % | DM p | Δ GW2 | Δ GW3 | Δ GW4 | Δ GW5 | Δ GW6 |
|---|---|---|---|---|---|---|---|---|---|---|
| Buts marqués (Poisson), marché ouverture | 1.5389 | 1.5454 | -0.0065 | [-0.0376 ; +0.0246] | 0.66 | -0.0224 | +0.0358 | +0.0144 | -0.0413 | -0.0192 |
| Buts marqués (Poisson), marché clôture | 1.5389 | 1.5431 | -0.0042 | [-0.0331 ; +0.0244] | 0.74 | -0.0064 | +0.0327 | +0.0109 | -0.0344 | -0.0240 |
| Clean sheet, marché ouverture | 0.5591 | 0.5660 | -0.0069 | [-0.0256 ; +0.0132] | 0.59 | -0.0181 | +0.0351 | +0.0018 | -0.0336 | -0.0195 |
| Clean sheet, marché clôture | 0.5591 | 0.5643 | -0.0052 | [-0.0239 ; +0.0142] | 0.64 | -0.0120 | +0.0333 | -0.0214 | -0.0239 | -0.0019 |

## Verdict

**Le marché ne bat pas le moteur** sur ces matchs, ni sur les buts ni sur le clean sheet, ni à l'ouverture ni à la clôture. Rien n'est branché : remplacer une entrée par une autre qui ne fait pas mieux ajouterait une dépendance réseau sans gain mesuré.

Le point estimé est même légèrement en faveur du moteur, mais l'intervalle contient zéro : l'égalité est la lecture honnête.

## Ce que ce document ne dit pas

- 50 matchs : l'intervalle d'une différence de log-loss y est large (±0,03 sur les buts). Un écart réel de l'ordre de 0,01 resterait invisible avant une demi-saison.
- Les cotes `Avg` sont relevées le vendredi après-midi (le mardi en semaine) : proches de la deadline, pas identiques. Elles ne connaissent pas les compositions.
- Le moteur et le marché utilisent ici le même modèle de buts (Poisson indépendants). Le test compare des forces d'équipe, pas des modèles de score.
- Exclus (cotes absentes ou scores discordants) : GW2 0, GW3 0, GW4 0, GW5 0, GW6 0.
