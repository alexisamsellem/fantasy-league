# Anomalies constatées

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


## A2 — Le gain d'un transfert était mesuré sur le mauvais objectif — CORRIGÉ

**Constaté le** 23/08/2026, en revue adverse du premier rapport hebdomadaire
réel (GW2 2026/27).
**Présent depuis** le commit `222a0b0` (V0).
**Sévérité** : haute — affectait la seule décision chiffrée du mode
hebdomadaire, sur le chemin de production.

`optimization/transfers.py` comparait les points individuels des deux
joueurs :

```python
delta = ep3(inn["id"]) - ep3(out["id"])
```

Or un remplaçant ne rapporte rien à l'équipe. Sortir un joueur de banc ne rend
pas ses points « manquants », et l'entrant n'ajoute que l'écart avec le
titulaire qu'il déplace. Le gain annoncé était donc surestimé pour tout échange
dont le sortant était sur le banc, d'autant plus que ce sortant avait une faible
probabilité de jouer.

Effet mesuré sur le rapport GW2 réel : `Colwill → Kayode` annoncé à **+8,04 pts
sur 3 GW**, alors que Colwill était sur le banc à `EP = 0,82` et `P(jouer) =
41 %`. Le vrai gain se compte contre le quatrième défenseur du XI, pas contre
Colwill.

**Correction** : `transfer_scan` évalue désormais chaque échange par la somme,
sur l'horizon, du **meilleur XI** avant et après. Deux chiffres sont exposés —
`delta3` (gain sur le XI, celui qui décide) et `delta3_brut` (écart individuel,
conservé pour rendre le biais visible dans le rapport). Repli explicite sur
l'écart individuel si l'effectif ne permet aucune formation légale, avec un
avertissement dans le rapport (`xi_based: False`).

Quatre tests de régression dans `tests/test_advisor.py`
(`TransfertSurLeXiTests`), dont un cas décisif : un échange de banc annoncé à
+7,2 pts par l'ancienne règle, ramené à +0,9 par la nouvelle, qui bascule donc
de « transférer » à « conserver ».

**Ce que ça ne change pas** : aucune projection. La correction porte sur
l'objectif de l'optimiseur, pas sur la prévision. Les échanges dont le sortant
est titulaire donnent exactement le même chiffre qu'avant — un test le vérifie.

## A3 — Le statut d'infirmerie n'était pas affiché dans le XI — CORRIGÉ

**Constaté le** 23/08/2026, même revue.
**Sévérité** : moyenne — aucune erreur de calcul, mais l'information la plus
décisive d'un rapport hebdomadaire restait invisible.

Le moteur lit `status` et `news` de chaque joueur, les transporte dans le
contrat, et les utilise pour calculer `P(jouer)` — mais le tableau du XI ne les
montrait pas. Un joueur signalé incertain apparaissait seulement par un
`P(60+)` plus bas, sans que le lecteur puisse savoir si la cause était une
alerte officielle ou un manque d'historique.

**Correction** : colonne « Alerte » dans le tableau du XI, portant le statut
officiel traduit (incertain, blessé, suspendu, indisponible) et la nouvelle
FPL associée, tronquée à 70 caractères.


## A4 — Un P(60+) bas sans alerte d'infirmerie était inexplicable — CORRIGÉ

**Constaté le** 23/08/2026, revue adverse du rapport GW2 réel.
**Sévérité** : moyenne — aucune erreur de calcul, mais le rapport ne permettait
pas de distinguer « le modèle a vu une absence » de « le modèle se trompe ».

Sur le rapport GW2, Haaland ressortait à `P(jouer) = 63 %` et `P(60+) = 55 %`
avec un statut officiel disponible et aucune nouvelle. Rien dans le rapport ne
disait pourquoi. Reconstitution du calcul : ces deux valeurs correspondent
exactement à un attaquant à ~34 titularisations la saison précédente ayant
joué **zéro minute** en GW1 — `shrink(0, 1, 0.839, 3) = 0.63`, puis
`0.63 × P60_GIVEN_START (0,88) = 0,55`. Le moteur avait raison ; le rapport
était muet.

**Correction** : `minutes_model` compte désormais les titularisations et les
apparitions réellement observées sur la fenêtre de récence, les écrit dans la
base affichée (« historique 1 GW (0 titularisation, 0 apparition) rétréci vers
saison 2025/26 ») et les transporte dans le contrat sous
`provenance.minutes_observed`. Le rapport ajoute une section nommant les
titulaires proposés qui n'ont pas joué, ou qui sont entrés sans démarrer.

`MODEL_VERSION` passe à `forecasting/0.3.0` : le contenu du contrat change,
même si aucune projection ne bouge.

Cinq tests, dont un qui fige la signature `63 % / 55 %` du titulaire absent
d'une journée. **Ce test ne dit pas que ces valeurs sont justes** — aucune
calibration ne l'a montré. Il empêche qu'un changement de priors passe
inaperçu.

**Ce que ça ne change pas** : aucune constante, aucune projection. Le calcul
est identique, il est simplement devenu lisible.


## A5 — La reconstruction d'effectif pouvait annoncer un retard négatif — CORRIGÉ

**Constaté le** 27/08/2026, pendant la construction de l'audit d'effectif
comparatif, avant toute publication.
**Présent depuis** le commit `222a0b0` (V0) — c'est une propriété de
`optimize_squad`, partagée avec le mode effectif initial.
**Sévérité** : haute pour l'audit — le chiffre de tête du rapport pouvait
inverser sa conclusion.

`optimization/initial.py` optimise par montée locale à partir de l'effectif le
moins cher. Une montée locale ne rend pas le même résultat selon son point de
départ : elle s'arrête au premier sommet atteint. Rien ne garantit donc que
l'effectif reconstruit vaille au moins l'effectif détenu, même à budget égal.

Mesuré sur le jeu de démonstration : à la valeur d'équipe du manager, la
reconstruction partant du moins cher plafonne **0,91 pt en dessous** de
l'effectif détenu sur 4 GW. Le rapport d'audit aurait affiché « retard :
−0,9 pt », c'est-à-dire « votre équipe bat le modèle » — alors que la seule
chose démontrée était l'échec de la montée à retrouver un sommet déjà connu.

**Correction** : `optimize_squad` accepte un point de départ (`start`), et
`optimization/audit.rebuild` fait la montée **deux fois** — depuis l'effectif
le moins cher, comme avant, et depuis l'effectif détenu — puis garde le
meilleur des deux. Le vivier est élargi aux joueurs détenus, sans quoi un
échange ne pourrait jamais les faire revenir.

Conséquence à écrire dans le rapport : l'écart mesuré est un **minorant** du
gain disponible, jamais un optimum démontré. Un audit qui conclut « aucun
retard » dit seulement que le moteur n'a pas trouvé mieux à partir de ces deux
points de départ.

Test de régression dans `tests/test_audit.py`
(`test_la_reconstruction_ne_peut_pas_valoir_moins_que_le_detenu`) : il vérifie
d'abord que le jeu de démo exerce bien le défaut (la montée depuis le moins
cher reste sous l'effectif détenu), puis que la reconstruction à deux départs
le corrige.

**Ce que ça ne change pas** : aucune projection, et aucun chiffre des modes
existants. `optimize_squad` sans `start` se comporte exactement comme avant —
un test l'affirme, à effectif et valeur identiques.


## A6 — Le XI affiché n'était pas celui qu'on alignerait — CORRIGÉ

**Constaté le** 27/08/2026 par Alexis, à la lecture du rapport GW2 réel :
« si je transfère Tzolis pour Tavernier, comment peut-il être sur le banc ? »
**Présent depuis** le commit `222a0b0` (V0).
**Sévérité** : haute — la feuille de match du rapport décrivait une équipe qui
n'existerait plus.

Le rapport hebdomadaire calcule le XI, le banc et le brassard sur l'effectif
DÉTENU, puis, dans une section séparée, recommande un transfert. Les deux
n'étaient jamais réconciliés. Conséquences sur le rapport GW2 réel :

- le joueur vendu (Tzolis) figurait encore au banc affiché, en rang 2 ;
- l'entrant (Tavernier, EP 3,90 contre 1,58) n'apparaissait nulle part dans le
  onze, alors qu'il y entre nécessairement ;
- la formation annoncée était fausse : 4-4-2 affiché, 3-5-2 après l'échange,
  van Ewijk (EP 2,11) passant sur le banc.

Le gain du transfert, lui, était juste : `transfer_scan` mesure bien l'écart
sur le meilleur XI (correction A2). L'optimiseur SAVAIT que l'entrant jouerait ;
le rapport ne le montrait pas.

**Correction** : `weekly_decision` calcule le second onze là où l'échange est
décidé et le rend sous `apres_transfert` (XI, banc, brassard, entrées et
sorties du onze). Le rapport titre désormais « XI recommandé SI TU CONSERVES »
et ajoute « XI à aligner SI TU TRANSFÈRES », avec la ligne de mouvements, le
banc d'après et un avertissement explicite si le brassard change avec
l'échange. La synthèse annonce les deux formations quand elles diffèrent.

Cinq tests de régression dans `tests/test_weekly.py` (`ApresTransfertTests`),
sur une fixture déterministe — 15 joueurs à 2,0 pts et un entrant à 9,0 pts —
qui exerce exactement le cas fautif : sortant sur le banc, entrant qui doit
prendre une place dans le onze. Un test vérifie aussi qu'une décision
« conserver » ne produit AUCUN second onze : en inventer un serait inventer
une décision.

**Ce que ça ne change pas** : aucune projection, aucune décision. Le capitaine,
le XI et l'arbitrage sont les mêmes qu'avant. C'est l'affichage qui mentait.
