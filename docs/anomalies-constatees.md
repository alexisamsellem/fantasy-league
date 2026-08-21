# Anomalies constatées, non corrigées

Défauts fonctionnels repérés en marge d'un autre chantier. Ils sont consignés
ici plutôt que corrigés au passage : une correction silencieuse dans un commit
de refactoring rendrait impossible de distinguer un déplacement de code d'un
changement de comportement.

## A1 — Capitaine implausible dans la démo de pré-saison

**Constaté le** 21/08/2026, pendant la séparation en trois couches.
**Présent depuis** le commit `4f9fa89` (introduit avec `build_parsed_initial`).
**Sévérité** : moyenne — affecte le jeu de démonstration synthétique, pas le
chemin de production.

Dans `fpl_advisor/demo.py`, `build_parsed_initial()` remet à zéro les
compteurs de la saison en cours (`minutes`, `starts`) **avant** d'appeler
`synthetic_history_past()`. Or cette fonction déduit le statut de titulaire de
la saison passée depuis ces mêmes compteurs :

```python
starter = e["starts"] > 0 or e["minutes"] >= 180
```

Après la remise à zéro, `starter` est faux pour tout le monde. Chaque joueur
reçoit donc un historique de remplaçant (`starts = max(1, 6 - k)`, soit 5
titularisations au mieux au lieu de 31). Conséquence visible : le capitaine
recommandé par la démo affiche `P(60+) = 14 %`.

Le contrôle qualité introduit dans le même chantier détecte l'anomalie et
bloque la publication (`capitaine_plausible`). Le comportement est donc
correct — c'est la fixture qui est fausse.

**Correction attendue** : construire l'historique de saison passée à partir du
rôle du joueur, pas de compteurs déjà remis à zéro, ou appeler
`synthetic_history_past()` avant la remise à zéro. Un test de régression devra
vérifier qu'un titulaire de la démo obtient une probabilité de titularisation
cohérente avec son historique.

**Ce que ça ne change pas** : aucun chiffre du chemin de production, aucune
donnée réelle. La démo reste utilisable pour ce à quoi elle sert — exercer les
invariants — et son rapport porte déjà l'avertissement « démo synthétique ».
