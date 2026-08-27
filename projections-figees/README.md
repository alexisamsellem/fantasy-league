# Projections figées — traces point-in-time

Un fichier par journée : ce que le moteur croyait **avant** la deadline, figé
avant de connaître le résultat. C'est la seule entrée que `calibrate` accepte,
et la raison est simple : recalculer des projections après les matchs et les
« noter » ne mesure rien du tout.

Ces fichiers ne contiennent **aucune donnée personnelle** — ni effectif, ni
ligue, ni team ID. Le contrat de projections est public par construction ;
c'est ce qui permet de les verser au dépôt.

Produits par :

```bash
cd ~/fantasy-league
python3 -m fpl_advisor freeze --with-history \
    --freeze-projections projections-figees/projections-GW<n>.json.gz
```

Le suffixe `.gz` compresse à la volée (~180 ko au lieu de 1,8 Mo). `calibrate`
relit les deux formes.

Après les matchs de la journée figée :

```bash
python3 -m fpl_advisor collect
python3 -m fpl_advisor calibrate \
    --from-projections projections-figees/projections-GW<n>.json.gz
```

## Inventaire

| Fichier | GW de décision | Horizon | Deadline | Données connues au |
|---|---|---|---|---|
| `projections-GW2.json.gz` | 2 | GW2–GW4 | 2026-08-28T17:30:00Z | 2026-08-27T15:34:32Z |

La GW1 est définitivement perdue pour la calibration : rien n'a été figé avant
sa deadline, et tout snapshot pris depuis contient déjà ses résultats.
