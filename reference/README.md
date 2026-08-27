# Références publiques versionnées

Fichiers de référence **publics** (aucune donnée personnelle), conservés dans
le dépôt parce qu'ils sont pénibles à reconstituer et qu'ils doivent rester
identiques d'une exécution à l'autre : changer le modèle au milieu d'une série
de calibration rend les journées incomparables.

## `team_priors.csv`

Priors d'attaque et de défense par club, saison **2025/26** (la précédente).

- Source : `https://www.football-data.co.uk/mmz4281/2526/E0.csv`, gratuit.
- Produit le 27/08/2026 par `python3 scripts/build_team_priors.py --e0 E0.csv`,
  apparié contre le bootstrap FPL du snapshot `20260827T153139Z`.
- Résultat de l'appariement : **17/20 clubs FPL appariés**, 3 sans référence —
  Coventry City, Hull City, Ipswich Town, c'est-à-dire exactement les promus.
  Au-delà de 4 clubs sans référence, ce seraient des noms qui ne correspondent
  pas et il faudrait compléter `ALIAS` dans le script.

Le moteur lit ce fichier sous `data/reference/team_priors.csv`, chemin ignoré
par Git (`data/` contient des données personnelles). Pour l'installer :

```bash
cd ~/fantasy-league
mkdir -p data/reference && cp reference/team_priors.csv data/reference/
```

Sans ce fichier, le moteur retombe sur les ratings `strength_*` de l'API FPL,
dont le statut est [R] non validé, et le contrôle `couverture_donnees` le
signale.
