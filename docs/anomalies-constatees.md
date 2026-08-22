# Anomalies constatées, non corrigées

Défauts fonctionnels repérés en marge d'un autre chantier. Ils sont consignés
ici plutôt que corrigés au passage : une correction silencieuse dans un commit
de refactoring rendrait impossible de distinguer un déplacement de code d'un
changement de comportement.

## A1 — Capitaine implausible dans la démo de pré-saison — CORRIGÉ

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

**Corrigé le** 22/08/2026, dans un commit isolé de tout refactoring.
`build_parsed_initial()` construit désormais l'historique de saison passée
**avant** la remise à zéro des compteurs. Effet mesuré sur la démo : capitaine
`Alpha-MIL1` à `P(60+) = 68 %` au lieu de 14 %, et le verdict de la démo passe
de `bloqué` (`capitaine_plausible`) à `avertissement` (`couverture_donnees`,
inchangé : la démo reste synthétique).

Deux tests de régression dans `tests/test_initial.py`
(`FixtureSynthetiqueTests`) : au moins un tiers des joueurs synthétiques garde
un historique de titulaire, et le capitaine de la démo reste au-dessus du seuil
`CAPTAIN_P60_WARN`.

**Ce que ça ne change pas** : aucun chiffre du chemin de production, aucune
donnée réelle. La démo reste utilisable pour ce à quoi elle sert — exercer les
invariants — et son rapport porte déjà l'avertissement « démo synthétique ».
