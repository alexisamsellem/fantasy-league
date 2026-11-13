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
était muet. (Chiffres d'époque : `P60_GIVEN_START` vaut 0,954 depuis A9, ce
qui porte cet exemple à 0,60. Le raisonnement est inchangé.)

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


## A7 — Une journée à moitié jouée a été notée, et le verdict versé au journal — CORRIGÉ

**Constaté le** 01/09/2026, en relisant le premier vrai résultat de calibration.
**Présent depuis** le commit `d95a350` (mise en place du robot).
**Sévérité** : haute — c'est le journal de calibration qui était corrompu,
c'est-à-dire la seule chose qui juge ce moteur.

Le 28/08 à 23h54 UTC, le robot a noté la GW2. À cette heure-là, **un seul
match sur dix était terminé** (Crystal Palace – Man City, coup d'envoi 19h00).
32 joueurs sur 622 avaient foulé le terrain ; les 590 autres attendaient leur
match et ont été comptés comme « n'a pas joué ».

Résultat versé au dépôt, commit `be38866` :

    Taux de base observé      4 %      (au lieu de 37 %)
    Score de compétence   −3.199      « ÉCHEC, le moteur fait PIRE que
                                        d'annoncer le taux de base »

Recalculée une fois les dix matchs terminés, la MÊME journée, avec les MÊMES
projections figées, donne **+0,416**. Le rapport ne mesurait pas le modèle, il
mesurait l'avancement du calendrier.

**Cause** : `observed_minutes` exigeait « au moins une minute non nulle »
quelque part dans le fichier live. Ce garde-fou protège d'une journée PAS
ENCORE COMMENCÉE. Il ne protège pas d'une journée EN COURS — dès le premier
match, la condition est remplie.

**Correction** : `collect.gw_complete` établit qu'une journée est terminée en
lisant le CALENDRIER, match par match. `event.finished` du bootstrap ne
convient pas : FPL le laisse à faux pendant des jours après le dernier coup de
sifflet, le temps de figer les bonus — au 01/09, la GW2 avait ses dix matchs
terminés et portait encore `finished: false`.

Le refus est posé aux trois entrées : `scripts/calibrer_en_attente.py`, la
commande `calibrate`, et la fonction de garde elle-même. Le message nomme le
compte exact (« 1/10 matchs terminés »), parce qu'un refus sans chiffre est
indiscernable d'une panne.

Six tests de régression, dont un qui rejoue le cas exact du 28/08 : un match
fini, des minutes déjà présentes dans le fichier live — l'ancien garde-fou
laissait passer, le nouveau refuse.

**Ce que ça ne change pas** : aucune projection, aucune décision. Le figeage
point-in-time du 28/08 09h19 était valide et l'est resté ; seule sa NOTATION
était prématurée. Le rapport fautif a été remplacé par le bon.


## A8 — Un transfert déjà passé n'est pas visible avant la deadline — CONSTATÉ, NON CORRIGÉ

**Constaté le** 28/08/2026 à 16h31 UTC, une heure avant la deadline GW2.
**Sévérité** : moyenne — produit de fausses alertes, et prive le contrôle
`effectif_a_jour` de son signal au moment précis où il servirait.

Le transfert `Tzolis → Tavernier` a été enregistré par le manager à **14h14
UTC**. Interrogé à **16h31**, `GET /api/entry/{id}/transfers/` a rendu une
liste **vide** pour l'événement 2. Le même appel, après la deadline, montre le
transfert avec son horodatage de 14h14.

Conséquence immédiate : une alerte fausse envoyée au manager (« ton transfert
n'est PAS enregistré ») alors qu'il était fait depuis deux heures.

**Cause non établie.** Deux explications tiennent : soit FPL masque
délibérément les transferts en attente avant la deadline, soit la réponse
était servie par un cache. Les deux mènent à la même conclusion pratique :
**ce signal n'est pas fiable avant la deadline.**

Conséquence sur le moteur : `weekly.pending_transfers` lit exactement cet
endpoint, et le contrôle qualité `effectif_a_jour` en dépend. Ce contrôle est
donc structurellement incapable de détecter le cas qu'il vise — des picks
périmés parce qu'un transfert a déjà été passé pour la GW à venir.

**Non corrigé faute de signal de remplacement** : l'API publique n'expose
aucune autre trace d'un transfert en attente. Deux options à trancher :
retirer le contrôle plutôt que de laisser croire qu'il protège, ou le laisser
en le requalifiant explicitement en « ne détecte qu'après coup ». À décider
avant d'ajouter d'autres contrôles qui dépendraient de la même source.

## A9 — `P60_GIVEN_START` valait 0.88 sans avoir jamais été mesuré — CORRIGÉ

**Constaté le** 08/09/2026, au deuxième point de calibration.
**Sévérité** : haute — sous-cotait tout titulaire confirmé, donc le XI, le
capitaine et l'ordre du banc.

Les tableaux de fiabilité des GW2 et GW3 montraient le même défaut, dans le
même sens, sur les mêmes tranches :

| Tranche P(60+) | GW2 annoncé → observé | GW3 annoncé → observé |
|---|---|---|
| 40 – 60 % | 50 % → 67 % (+17) | 51 % → 74 % (+23) |
| 60 – 80 % | 71 % → 86 % (+15) | 70 % → 84 % (+13) |
| 80 – 100 % | 82 % → 95 % (+13) | 83 % → 97 % (+14) |

La tranche haute donne la clé. Dans `minutes_model` :

    p60 = min(avail, avail * r_start * P60_GIVEN_START * tilt)

avec `r_start ≤ 1`, le moteur **ne pouvait structurellement pas annoncer
plus de 88 %**, alors que la population des titulaires acquis convertit à
97 %. Le plafond était l'anomalie, pas le rétrécissement.

**Mesure directe.** `P60_GIVEN_START` est P(60+ minutes | titularisé) : une
grandeur observable, pas une sortie de modèle. Relevée sur le champ officiel
`starts` de `/api/event/{gw}/live/`, GW1 à GW3 (10 matchs chacune, donc
220 titulaires par journée — un relevé complet, pas un échantillon) :

| Journée | Titularisations | Dont 60+ | Taux |
|---|---|---|---|
| GW1 | 220 | 210 | 0.955 |
| GW2 | 220 | 209 | 0.950 |
| GW3 | 220 | 211 | 0.959 |
| **Total** | **660** | **630** | **0.9545** |

Écart-type 0.0081 : l'ancienne valeur 0.88 était à **neuf écarts-types** de la
mesure. Dispersion inter-journée : 0.9 point. La constante est passée à
**0.954**, et perd son marqueur `[H]`.

**Effet mesuré sur les deux journées figées.** `P60_GIVEN_START` entre comme
multiplicateur pur — le `min()` ne mord jamais tant que la constante est
inférieure à 1 — donc les contrats figés se rejouent exactement, sans
reconstruire les snapshots :

| Journée | Compétence P(60+) avant | après | Δ |
|---|---|---|---|
| GW2 | +0.4157 | +0.4359 | +0.0202 |
| GW3 | +0.4607 | +0.4838 | +0.0231 |

La tranche 80–100 % passe de +13/+14 à +5/+5 d'écart. Les deux journées
s'améliorent, dans le même sens et dans le même ordre de grandeur.

**Régression** : `tests/test_priors.py::P60SiTitulaireTests`. Le relevé des
660 titularisations y est figé comme fixture ; la constante doit rester dans
son intervalle de confiance à 99 %, et le test vérifie explicitement que
0.88 en reste exclu — sans quoi il ne démontrerait plus rien. Un troisième
test fige la proportionnalité de `p60` à la constante, condition de validité
du rejeu ci-dessus.

**Ce que cette correction ne règle pas.** La tranche 40–60 % reste
sous-confiante après correction (+17 en GW2, +20 en GW3). C'est un défaut
distinct, cohérent avec un `MINUTES_PRIOR_MATCHES = 3.0` trop agressif en
début de saison, où l'historique ne pèse qu'une ou deux journées. **Non
corrigé** : aucune mesure directe de cette constante n'existe, et son effet
est confondu avec la faible taille de l'historique — la modifier maintenant
reviendrait à l'ajuster sur deux journées. À reprendre vers la GW6, quand
l'historique observé pèsera plus que le prior.

## A10 — Les probabilités de minutes étaient trop prudentes sur les disponibles — CORRIGÉ

**Constaté le** 13/11/2026, sur les neuf points de calibration GW2-GW10.
**Sévérité** : moyenne — sous-cotait l'espérance des titulaires probables
d'environ 0,4 point par GW, sans changer leur classement.

**Le défaut, cumulé et prouvé.** 5043 paires (joueur, GW), GW2-GW3 rejouées
sous `P60_GIVEN_START = 0.954` (rejeu exact, voir A9). Intervalles à 95 % par
bootstrap sur les joueurs : un joueur revient chaque semaine, les paires ne
sont pas indépendantes.

| Tranche P(60+) | n | Annoncé | Observé | Écart (IC95) | GW où observé > annoncé |
|---|---|---|---|---|---|
| 40 – 60 % | 663 | 50,2 % | 60,5 % | +10,3 (+6,3 ; +14,7) | 8/9 |
| 60 – 80 % | 803 | 70,0 % | 80,8 % | +10,8 (+7,9 ; +13,8) | 9/9 |
| 80 – 100 % | 544 | 87,2 % | 92,3 % | +5,0 (+2,4 ; +7,3) | 8/9 |

P(jouer) montre le même étirement manquant : trop haut en bas de l'échelle
(20-40 % : −6,6 points), trop bas en haut (60-80 % : +10,4 ; 80-100 % : +7,0).
Les probabilités étaient écrasées vers le milieu.

**Correction.** `p = sigmoïde(a · logit(p_brute) + b)`, appliquée aux seuls
joueurs au statut officiel « disponible ». Paramètres (`priors.MINUTES_RECALIBRATION`)
ajustés par régression logistique sur GW2-GW10 : P(60+) a = 1,295, b = +0,333 ;
P(jouer) a = 1,618, b = +0,076. La transformation est monotone : l'ordre des
joueurs disponibles sur la probabilité ne bouge pas (un disponible peut en
revanche passer devant un incertain non corrigé). Les valeurs brutes, la
disponibilité et le fait d'avoir été corrigé sont figés dans le contrat
(`provenance.minutes_brut`) : un réajustement futur pourra repartir du brut.

**Validation hors échantillon** (chaque GW corrigée par des paramètres appris
sans elle) :

| Mesure | Avant | Après | GW améliorées |
|---|---|---|---|
| Brier P(60+) | 0,1128 | 0,1088 | 9/9 |
| Brier P(jouer) | 0,1219 | 0,1151 | 9/9 |
| Erreur quadratique moyenne sur les points (RMSE) | 2,221 | 2,206 | 8/9 |
| Corrélation de rang points (Spearman) | 0,693 | 0,695 | — |

Tranche 60-80 % corrigée : 71 % annoncé, 70 % observé. Même résultat sur
GW4-GW10 seules (moteur jamais rejoué) : Brier 7/7, RMSE 6/7.

**Pourquoi seuls les disponibles.** Sur les 189 paires de joueurs incertains
(statut « d »), la même correction dégradait le Brier (0,154 → 0,167).

**Piège de mesure évité.** L'erreur absolue moyenne sur les points se
DÉGRADE avec la correction (1,334 → 1,353). Ce n'est pas un signal :
l'erreur absolue récompense la médiane (1 à 2 points), pas la moyenne (1,6 à
3,7). `ep` est une espérance, son juge est l'erreur quadratique.

**Ce que cette correction ne règle pas.** Elle ne change presque pas le
classement des joueurs, donc presque pas les décisions (capitaine, XI). Son
apport : des probabilités honnêtes pour tout calcul de risque, et une
espérance juste sur les titulaires. La cause en amont (rétrécissement des
minutes, `MINUTES_PRIOR_MATCHES`) reste non mesurée : la corriger exigerait
de reconstruire les snapshots, que le dépôt ne conserve pas.

**Limites relevées en revue adversariale (non bloquantes).**
- Les paramètres de P(jouer) dérivent : GW2-GW3 seules donnent a = 2,19,
  GW4-GW10 seules a = 1,53. Ceux de P(60+) sont stables (a entre 1,26 et 1,40
  par GW, sauf GW8 à 1,03). Validation plus stricte — n'apprendre que sur
  les GW passées — : Brier P(60+) meilleur 7/7, P(jouer) 6/7, points 6/7.
- Les seuils en aval (alerte capitaine `CAPTAIN_P60_WARN`, alertes
  P(jouer) < 0,9 du rapport et du mail) sont exprimés sur l'échelle
  corrigée et se déclenchent donc moins souvent. Non réévalués.

**Traçabilité.** A9 n'avait pas incrémenté `MODEL_VERSION` : GW2-GW3 (avant
A9) et GW4-GW10 (après) portent la même étiquette `forecasting/0.3.1` pour
deux moteurs différents. Cette correction passe à `forecasting/0.4.0`.

**Régression** : `tests/test_recalibration_minutes.py`, sur les fichiers figés
et `tests/fixtures/resultats-GW2-GW10.csv.gz` (minutes et points publics, aucune
donnée personnelle). Il vérifie que le défaut existait, que les constantes
livrées sont celles des données, et que la correction gagne hors échantillon
chaque semaine sur les probabilités et au total sur les points.

## A11 — La conduite de ligue était fixée à la main et contredite par la simulation — CORRIGÉ

**Constaté le** 13/11/2026, par simulation de la fin de saison.
**Sévérité** : moyenne — la lecture de position conseillait de parier à
partir de 15 pts de retard, quel que soit le nombre de journées restantes.

**Méthode.** Monte Carlo GW11-GW38, 10 000 tirages, deux mini-ligues réelles
(24 managers ; identifiants et noms hors dépôt). Pour chaque GW simulée, une
GW passée (1 à 10) est tirée, commune à tous, et l'effectif GW10 de chacun est
noté sur ses points réels, remplacements automatiques compris : les joueurs
partagés créent la corrélation entre managers. S'y ajoutent :
- un talent par manager : moyenne GW1-10 hors chips, rétrécie de 49 % vers le
  groupe (part du bruit mesurée sur les écarts entre managers) ;
- un bruit propre de 4,2 pts/GW, calibré sur la variance observée des écarts
  entre paires ;
- les chips restants, jeu 1 avant la GW19, jeu 2 ensuite (règles officielles
  2026/27) ; triple capitaine et banc renforcé notés sur les points réels,
  wildcard et free hit supposés valoir 6 et 5 pts.

Contrôle : écart-type par GW des écarts au groupe, 12,3 simulé contre 12,9
observé.

**Résultat (ligue où l'on est 2ᵉ à 17 pts, 28 GW restantes).** P(finir 1er) :
maximiser l'espérance 27 %, copier le leader 28 %, paris modérés 26 %,
capitaine différentiel 12 %. Parier ne rapporte rien ; l'ancienne règle
disait de parier.

**Grille simulée** (meilleure conduite, P(1er)) — E maximiser, C couvrir,
P paris modérés (+10 pts d'écart-type par GW, coût 0,5 pt/GW) :

| GW restantes | −60 | −40 | −25 | −17 | −10 | −5 | 0 | +5 | +25 |
|---|---|---|---|---|---|---|---|---|---|
| 28 | P 13 % | E 18 % | E 24 % | C 28 % | C 35 % | C 40 % | C 44 % | C 49 % | C 67 % |
| 18 | P 10 % | P 15 % | P 21 % | E 24 % | E 28 % | E 31 % | E 34 % | C 38 % | C 61 % |
| 10 | P 6 % | P 12 % | P 19 % | P 23 % | P 27 % | E 30 % | C 34 % | C 41 % | C 67 % |
| 5 | P 3 % | P 9 % | P 16 % | P 21 % | P 26 % | E 31 % | E 36 % | C 43 % | C 72 % |

Les écarts entre E, C et P sont souvent de 1 à 3 points, de l'ordre du bruit
de simulation : la règle retient ce qui est robuste. Revue adversariale
comprise (5 tirages × 4000 par case) :

- **Couvrir** avec au moins 5 pts d'avance. À égalité, couvrir et maximiser
  se valent (18 GW : 32,8 % contre 33,6 %) : on maximise.
- **Copier le leader en retard** : à 24-28 GW restantes, copier égale ou bat
  maximiser (−10 pts : 34,9 % contre 30,8 %). C'est dû à l'avance de chips de
  CE manager sur le leader, donc propre à sa situation. La règle ne le
  déconseille donc pas à ce stade. Dès 18 GW restantes, copier coûte cher
  (15 % contre 24 % à 17 pts) : la règle le déconseille.
- **Parier** au-delà de 45 pts de retard (≥ 24 GW restantes), 20 pts (12 à
  23) et 8 pts (moins de 12). **[H]** : ces seuils valent pour des paris à
  +10 pts d'écart-type par GW et 0,5 pt/GW de coût. Avec 1 pt/GW de coût, à
  18 GW et −25 pts, parier perd 2,8 points de P(1er). Avec 6 pts d'écart-type,
  parier ne paie nulle part sur la grille.
- **Jamais de capitaine différentiel** : −16 points de P(1er).

**Arbitrage entre ligues.** Une équipe pour deux ligues. Mesuré à 28 GW
restantes seulement : parier pour la ligue lointaine (91 pts) fait passer
P(1er) de 1,3 % à 2,0 % là-bas, et de 27,4 % à 26,3 % dans la ligue proche.
La conduite sans pari l'emporte. Plus tard, le rapport s'inverse : à 10 GW,
parier coûte 0,8 point à −5 et rapporte 2,0 à −25. En deçà de 24 GW
restantes, et pour couvrir contre maximiser, l'arbitrage n'est pas mesuré :
le rapport et le mail le disent et laissent choisir.

**Sensibilité.** P(1er) dans la ligue proche va de 15 % (talents supposés
égaux) à 37 % (talents non rétrécis). Le classement des conduites tient,
sauf E contre C qui s'inversent selon l'hypothèse de talent. Les deux
leviers dominants sont, d'une part, l'espérance (+1 pt/GW fait passer de
28 % à 42 %) et, d'autre part, l'avance de chips (sans elle, 22 %).

**Limites.** Effectifs figés à la GW10, timing des chips aléatoire, wildcard
et free hit supposés. Le script de simulation lit des données personnelles :
il reste hors dépôt.

**Régression** : `tests/test_ligues.py::ConduiteMesureeTests` et
`ArbitrageTests` figent la règle sur les cases de la grille.

## A12 — Les chips n'étaient pas suivis — CORRIGÉ

**Constaté le** 13/11/2026. Le README le disait : « pas d'optimisation de
chips ». Or un manager suivi n'avait joué aucun de ses 4 chips de première
moitié, qui expirent à la GW19. Dans la simulation A11, cette avance de chips
valait 6 points de P(finir 1er).
**Sévérité** : haute pour l'usage — un chip non joué avant sa fin de fenêtre
est perdu.

**Ce qui a été mesuré avant de rien écrire** (backtest : 24 managers réels,
effectif de la GW précédente, projections figées GW2-GW10, 216 paires ;
données personnelles hors dépôt) :

| Chip | Signal du moteur | Corrélation EP → points |
|---|---|---|
| Banc renforcé | EP du banc (4 remplaçants choisis par le moteur) | 0,59 (pente 1,32) |
| Triple capitaine | EP du capitaine | 0,03 (pente 0,23) |

- **Banc renforcé** : la règle « jouer quand l'EP du banc de la GW est au
  moins celle des deux suivantes » rapporte 9,8 pts contre 8,1 pour une
  semaine au hasard (+1,8 ; IC90 −0,1 ; +4,0). Signal faible mais réel.
- **Triple capitaine** : aucun signal. Sur données publiques, parmi les 57
  candidats capitaines à EP ≥ 4,5, le Spearman EP → points vaut 0,00. Le
  meilleur EP de chaque GW (5,4 à 7,0) a rapporté de 1 à 23 pts sans lien.
  Seul un double match change l'espérance, mécaniquement.
- **Wildcard, free hit** : rien de mesurable ici. Le plafond de gain d'un
  wildcard est déjà chiffré par l'audit d'effectif (`retard`).

**Correction.** `fpl_advisor/chips.py`, section « Chips » du rapport
hebdomadaire :
1. fenêtres lues dans `bootstrap-static → chips` (jamais inventées) et chips
   joués lus dans l'historique du manager ;
2. contrainte « un chip par GW » : marge = GW restantes − chips restants ; à
   zéro, un chip doit partir ;
3. consignes : banc renforcé sur l'EP du banc ; triple capitaine « libre »
   sauf double match ; une seule consigne « jouer » par GW (double match,
   puis banc, puis contrainte).

**Régression** : `tests/test_chips.py`. Il fige les fenêtres, la marge et
l'urgence, les consignes, et la prémisse publique du triple capitaine : si un
futur moteur classe enfin les capitaines, le test échoue et la règle doit être
revue.
