# Résultats observés — la vérité terrain du banc d'essai

Un fichier par journée **validée par FPL** (`data_checked`) : minutes, points
et principales statistiques de chaque joueur, plus le score de chaque match.
Lus sur `GET /api/event/{gw}/live/` et `GET /api/fixtures/` ; la date de
lecture est dans `fetched_at`.

Ils sont figés pour la même raison que les projections : un banc d'essai qui
relit l'API à chaque exécution peut changer de résultat sans que le moteur ait
changé. Données publiques, aucune donnée personnelle.

```bash
python3 scripts/figer_resultats.py    # fige les journées validées manquantes
python3 scripts/banc_points.py        # → calibrations/banc-points.md
```
