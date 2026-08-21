# Agent de décision autonome pour Fantasy Premier League — Dossier de conception

**Version 2.0 — 21 août 2026.** Révision intégrant la revue du cofondateur : logique de capitanat corrigée, fuites de compositions retirées des déclencheurs de la GW courante, discount γ supprimé au profit d'un traitement explicite de l'incertitude, optimiseur repositionné en générateur de candidats, sourçage durci, évaluation étagée, V0 réduite au conseiller Classic.

## Avant-propos : statuts épistémiques, sourçage, et une limite assumée

Quatre balises dans tout le dossier :

- **[F]** — fait vérifié par nous, directement à la source officielle (page ou API `premierleague.com`) ;
- **[F◦]** — fait rapporté comme officiel par au moins deux sources secondaires concordantes, avec le lien officiel rattaché à l'affirmation ; vérification directe en attente ;
- **[H]** — hypothèse de modélisation, à valider empiriquement ;
- **[R]** — à revérifier chaque saison.

Limite assumée : depuis l'environnement de rédaction, tout `premierleague.com` — pages *et* API — est bloqué par le proxy réseau (vérifié le 21/08/2026). **Aucun fait réglementaire du dossier ne porte donc l'étiquette [F].** Le tableau ci-dessous rattache chaque fait important à sa source officielle ; le **protocole J0** (`scripts/j0_verification.py`, lecture seule, guide dans `docs/guide-j0.md`), première tâche de la V0, vérifie depuis ta machine les paramètres exposés par l'API officielle et fait confirmer les règles sur les pages Help/Rules — qui restent l'autorité pour tout ce que l'API n'expose pas — puis promeut chaque ligne de [F◦] vers [F], ou corrige le dossier. Une ligne non promue reste provisoire.

| Fait réglementaire 2026/27 | Source officielle rattachée | Statut |
|---|---|---|
| Effectif 15 (2 GB, 5 DEF, 5 MIL, 3 ATT) ; budget 100,0 M£ ; max 3 par club ; XI : 1 GB, ≥3 DEF, ≥1 ATT | [Récapitulatif officiel des changements](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627) + `bootstrap-static` (J0) | [F◦] |
| 1 transfert gratuit/GW, cumul max 5 ; transfert excédentaire −4 pts | [Récapitulatif officiel](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627) | [F◦] |
| Capitaine ×2 ; le vice ne prend le brassard que si le capitaine joue 0 minute dans la GW | Help/Rules officiel (lecture J0) | [F◦] [R] |
| Chips : 2 Wildcards, 2 Free Hits, 2 Bench Boosts, 2 Triple Captains ; jeu 1 expirant fin GW19, jeu 2 dès GW20 | [Guide chips officiel](https://www.premierleague.com/en/news/4362085) | [F◦] |
| DEFCON : 2 pts si CBIT ≥ 10 (défenseurs) ou CBIRT ≥ 12 (milieux/attaquants, récupérations incluses) ; plafond 2 pts/match | [Article officiel DEFCON 2026/27](https://www.premierleague.com/en/news/4361991/whats-happening-with-defensive-contribution-points-in-202627-fantasy) | [F◦] |
| BPS 2026/27 rééquilibré : moins de chevauchement avec DEFCON, gardiens/latéraux mieux servis, pénalité de dépossession supprimée | [Récapitulatif officiel](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627) | [F◦] [R] |
| Prix : ±0,1 M£/nuit selon flux nets (seuils cachés) ; revente = achat + moitié de la hausse (arrondie au 0,1 inférieur), baisse subie en totalité ; prédicteur officiel de prix (15 min) | [Mécanique officielle des prix](https://www.premierleague.com/en/news/2858775) | [F◦] |
| Deadline à 90 min du premier coup d'envoi de la GW ; verrouillage des scores à 09h00 UK le lendemain du dernier match | [Récapitulatif officiel](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627) | [F◦] |
| Saison du 21/08/2026 au 30/05/2027 | [Dates officielles](https://www.premierleague.com/en/news/4468487/dates-for-202627-premier-league-season-confirmed) | [F◦] |
| Draft : snake, pas de prix ni budget, joueur unique par ligue, pas de capitaine ni chips ; waivers traités 24 h avant deadline puis free agency ; 4 régimes de trades | [FPL Draft officiel — trading](https://www.premierleague.com/en/news/1245445/fpl-draft-how-to-do-player-trading) + `draft.premierleague.com` (J0) | [F◦] [R] |

## Paramètres actés (revue du 21/08/2026)

Décisions du cofondateur, traitées comme des contraintes de conception : **mode** Classic uniquement en V0/V1, architecture extensible vers Draft mais aucun module Draft maintenant ; **objectif** victoire d'une mini-ligue privée précise, le rang global servant de benchmark et de contrainte secondaire ; **automatisation** validation humaine de toute décision pendant une saison complète, aucun transfert, hit, capitaine ou chip automatique ; **budget** quasi nul en V0, API de cotes payante seulement après preuve de calibration du modèle de minutes et du processus, pas de données événementielles premium avant ROI démontré ; **environnement** Python, DuckDB, snapshots horodatés, dépôt Git local, VPS seulement quand la fiabilité opérationnelle l'exigera.

---

## 1. La nature du jeu

FPL est l'empilement de six problèmes distincts ; les confondre laisse de l'espérance à chaque interface.

**Prévision.** L'unité de base est la distribution des points d'un joueur par Gameweek, pas sa moyenne : à 5,0 pts espérés, un attaquant volatil et un milieu défensif régulier sont des actifs radicalement différents pour le brassard, les chips et une mini-ligue.

**Allocation de capital.** 100 M£, des prix nocturnes de ±0,1 M£, une revente asymétrique [F◦]. Le capital a une trajectoire ; c'est un rendement secondaire, subordonné aux points.

**Optimisation sous contraintes.** À chaque deadline : 15 joueurs, un XI, un brassard, un banc ordonné, sous budget, quotas, 3 par club, stock de transferts. Le sous-problème d'une deadline à espérances données se résout exactement ; le problème saisonnier complet, non — notre architecture est une approximation assumée de ce problème-là (section 6).

**Décision séquentielle.** 38 deadlines liées : un transfert non utilisé devient une option (cumul 5 [F◦]), un chip joué n'existe plus en avril, un achat se revend au prix de demain. Cadre : décision séquentielle sous incertitude, replanifiée chaque GW.

**Gestion du risque.** La variance est une ressource à doser, structurée par les corrélations : coéquipiers covariants, brassard qui double la variance de son porteur, banc comme assurance sur les minutes.

**Théorie des jeux.** Le classement est relatif ; la quantité pivot est l'*effective ownership* (section 9). C'est ce problème qui sépare les cinq contextes (Classic, Draft, rang global, mini-ligue, formats à différenciation). Notre objectif principal étant une mini-ligue précise, cette couche n'est pas un raffinement : c'est la fonction objectif.

## 2. Les fondamentaux d'un gagnant durable

L'edge durable vient d'un petit nombre de compétences mesurables, dont la hiérarchie ne suit pas le discours communautaire.

**1. La prévision des minutes — compétence n° 1.** [H, forte conviction] La queue gauche des désastres FPL (banc gâché, brassard sur un remplaçant, −4 pour un non-joueur) est un échec de minutes, pas de talent. Mesure : log-loss, Brier et calibration de `P(titularisation)`. Première brique de la V0, premier critère d'évaluation (section 12).

**2. La lecture du calendrier.** L'edge n'est pas de voir qu'Arsenal–Coventry est favorable : c'est de planifier des blocs de 4–6 GW là où le champ réagit avec retard.

**3. La discipline de capital.** Acheter avant les hausses quand les points justifient déjà l'achat, jamais *pour* la hausse. Le prédicteur officiel de prix [F◦] a banalisé l'edge informationnel des outils communautaires — exemple de signal devenu commodité.

**4. Le brassard.** ~38 choix par saison, la plus forte variance contrôlable. Mesure : « captaincy delta » — points du choix vs meilleur choix ex ante du modèle, et vs ex post.

**5. Hits et chips.** Un −4 se compare à un gain probabiliste multi-GW (section 7) ; un chip est une option qui expire (fin GW19 pour le jeu 1 [F◦]). Mesure : EV réalisée des hits ; valeur capturée par chip vs sa distribution simulée.

**6. L'hygiène décisionnelle.** Décider à heure fixe, sur données figées, avec journal ; ne jamais réagir à un résultat. La compétence que l'agent fournit gratuitement : ni tilt, ni biais de récence, ni aversion asymétrique aux pertes.

**Tri des « règles » communautaires.** [H] Plausiblement causal : minutes d'abord ; régression des sur-performances xG ; les cotes comme référence d'équipe — *prior utile et benchmark, pas « meilleur prédicteur » tant que nous ne l'avons pas testé contre nos propres modèles* (section 12). Corrélé mais confondu : la « forme » sur 5 matchs — surtout du bruit autour de talent + calendrier. Dépendant du profil de risque : « jamais de hit précoce », « brassard premium à domicile toujours ». Bruit quasi pur : « momentum d'équipe », malédictions de chips, eye test d'un match isolé. Chaque heuristique communautaire est une hypothèse falsifiable, jamais un préréglage.

## 3. Le modèle de décision

Principe : des modèles simples et calibrés, ancrés sur des références externes quand elles existent, avec une hiérarchie d'incertitude explicite. Aucune composante ne prétend à une précision que ses données ne permettent pas.

**Minutes et titularisation — le socle.** Modèle hiérarchique : `P(groupe)` × `P(titulaire | groupe)` × distribution des minutes (titulaire : masse vers 90 avec risque de sortie ; remplaçant : mélange {0, 10–30}). V0 : régression logistique régularisée sur compositions passées, rotation, congestion, statut déclaré en conférence de presse — plus une couche de règles manuelles documentées (un presser du vendredi prime le modèle). Limites : entraîneurs nouveaux, hiérarchies non annoncées ; la sortie reste une distribution, jamais un nombre. Les compositions officielles et fuitées de la GW écoulée servent à deux choses : nourrir la prévision de la GW **suivante**, et valider la calibration — jamais à modifier la GW courante (section 11).

**Buts et assists.** Deux étages. (i) Équipe : Poisson bivarié type Dixon-Coles sur les scores, cotes 1X2/over-under en prior d'ancrage [H — supériorité présumée, testée en section 12]. (ii) Joueur : partage du volume offensif par npxG/90 et xA/90, penalties et coups de pied arrêtés, conditionné aux minutes simulées ; finition rétrécie vers la moyenne (l'écart vs xG sur une demi-saison est surtout du bruit hors finisseurs d'élite [H]). Promus et recrues (Coventry, Hull) : prior par cotes et championnat d'origine, incertitude élargie.

**Clean sheets.** Sous-produit du modèle d'équipe : `P(0 but encaissé)` croisé avec les minutes du défenseur. La CS est commune à toute la défense — jamais indépendante entre coéquipiers ; une défense empilée a une variance gonflée (utile en Bench Boost, dangereux en mini-ligue serrée).

**Bonus (BPS).** Le BPS 2026/27 est rééquilibré [F◦] : l'historique pré-2026 est non représentatif [R]. V0 : approximation `E[bonus] = f(buts, assists, CS, DEFCON, saves)` recalibrée en cours de saison sur les données officielles [H] ; modéliser le BPS action par action attendra d'avoir assez de matchs sous la nouvelle formule.

**DEFCON.** Modèle de comptage (binomiale négative) des actions par 90 selon rôle et possession adverse → `P(seuil atteint)`. **Contrainte de validation des données** : ne pas présumer que FBref/Understat comptent les mêmes actions que FPL. Vérité terrain = les statistiques défensives par match exposées par l'API FPL officielle (noms de champs à relever au protocole J0 [R]) ; toute source externe n'entre comme feature qu'après réconciliation joueur-match contre les comptes officiels sur un échantillon, avec seuil d'acceptation documenté (ex. ≥95 % de concordance exacte). Jusque-là, le modèle DEFCON n'utilise que les données FPL.

**Cartons, CSC, penalties manqués.** Base rates par joueur, intégrés pour l'honnêteté de la queue gauche, sans y chercher d'edge.

**Blessures, rotations, changements de rôle.** Les modèles prédictifs de blessure ont peu de pouvoir : priors grossiers et réaction rapide à l'information de presse (sections 4 et 11). Changements de rôle : détecteur de ruptures sur features (tireur de penalty, position moyenne) avec alerte humaine.

**Adversaires et calendrier.** Ratings attaque/défense réestimés chaque semaine, avantage domicile ; effets de congestion et d'Europe régularisés fortement [H]. Saison post-Coupe du monde : traitée en incertitude élargie, pas en effet moyen inventé [H].

## 4. Les données

Architecture : chaque source est capturée en **snapshots horodatés immuables**, puis normalisée dans DuckDB sous une couche *point-in-time* — on ne peut interroger que ce qui était connu à l'instant T. C'est la condition du backtesting sans leakage, et notre archive propre commence au J0 : ses limites sont dites en section 12.

**Famille 1 — Officielles (API FPL).** Endpoints publics non documentés mais stables [R chaque été] : `bootstrap-static` (joueurs, prix, ownership, statuts, règles), `fixtures`, `element-summary/{id}`, `event/{gw}/live`, endpoints de ligue et d'équipe — les picks d'une équipe sont publics après la deadline, ce qui rend l'objectif mini-ligue instrumentable (à confirmer au J0 [R]). Référence absolue pour prix, propriété, règles, points, et vérité terrain des statistiques (DEFCON inclus) ; les flags de blessure officiels suivent la presse, ils ne la précèdent pas.

**Famille 2 — Performance.** Understat (xG/xA par tir), FBref (événements défensifs), datasets communautaires (vaastav) pour l'historique. Latence post-match de quelques heures. Règles d'usage : jamais deux définitions d'xG mélangées dans une feature ; réconciliation contre les comptes officiels FPL avant tout usage DEFCON/BPS (section 3) ; scraping fragile et licences à clarifier [R].

**Famille 3 — Marché (cotes).** 1X2, over/under, clean sheet, buteur. V0 : sources gratuites et clôtures historiques (football-data.co.uk) pour l'étalonnage ; API payante seulement après la preuve de calibration exigée par les paramètres actés. Statut épistémique : prior d'ancrage et benchmark de nos modèles d'équipe [H] — pas une vérité. Limites : les cotes intègrent les compositions à ~1 h du match, après notre deadline ; couverture inégale des marchés joueurs.

**Famille 4 — Nouvelles d'équipe.** Conférences de presse (J-1/J-2 des matchs), agrégateurs de blessures, journalistes de club — la seule famille qui change légitimement une décision tard, *avant la deadline*. Filtre à trois niveaux : T1 officiel (club, presser retranscrit) ; T2 journaliste de club établi ; T3 rumeur/ITK — n'influence jamais une décision, alerte humaine seulement. Chaque source porte un score de fiabilité historique [H]. **Les fuites de compositions à H-1 sont hors du périmètre décisionnel de la GW courante** : la deadline est à H-90 [F◦], cette information arrive structurellement trop tard ; elle est archivée pour la GW suivante et pour la validation du modèle de minutes.

**Famille 5 — Signaux communautaires.** Ownership et EO (LiveFPL et équivalents), templates, sentiment. Usage : la couche théorie des jeux (section 9) et l'anticipation des prix — jamais comme signal de qualité d'un joueur : le consensus est déjà dans les prix et l'ownership, l'imiter n'apporte aucun edge par construction. En mode mini-ligue, la donnée pertinente est locale : les équipes réelles de tes rivaux, lues à la source officielle après chaque deadline.

## 5. Le moteur de projection

Le livrable central est la **distribution des points** par joueur et par GW — l'EP n'en est que la moyenne — puis, en V1, la distribution **jointe** d'équipes entières avec leurs corrélations.

**Décomposition (V0).**

```
points(j,m) = pts_minutes + pts_buts + pts_assists + pts_CS + pts_DEFCON
            + pts_saves + pts_bonus − malus
```

En V0, chaque composante produit une distribution par joueur (les scénarios de minutes en racine), et les tirages entre joueurs sont indépendants [H, assumé] : c'est suffisant pour choisir un XI, ordonner un banc et poser le brassard, pas pour estimer la distribution d'une équipe entière ni un duel de mini-ligue.

**Simulation jointe (V1).** N ≈ 10 000 tirages par GW : minutes de chaque joueur (la racine), score de chaque match (Poisson bivarié), allocation multinomiale des buts/assists aux présents, comptages DEFCON/saves/cartons, CS et malus déduits du score, bonus approché. Les corrélations structurelles sont gratuites — coéquipiers liés par le même score simulé, adversaires anticorélés. Ce niveau permet plafond p90, plancher p10, `P(équipe > x)` et surtout `P(battre le rival R)` — le critère de notre objectif principal.

**La règle du brassard, simulée exactement.** Le couple (capitaine c, vice v) est évalué par la règle FPL elle-même : les points de c sont doublés s'il joue au moins une minute ; s'il joue 0 minute, c'est v qui est doublé (s'il joue) [F◦, lecture exacte au J0]. Sans ambiguïté, le total simulé d'une GW s'écrit :

```
Total(XI, c, v) = Σ_{j ∈ XI*} X_j  +  X_c·1{M_c > 0}  +  X_v·1{M_c = 0}·1{M_v > 0}
```

où XI* est le XI après auto-substitutions, et où les deux derniers termes sont le **bonus additionnel du brassard** — la copie supplémentaire des points du porteur, qui s'ajoute à ses points déjà comptés dans la somme du XI (capitaine ×2 = une fois dans le XI + une fois ici). À XI fixé, maximiser ce bonus équivaut à maximiser le total. Correction sur la V1 : `argmax EP × P(minutes ≥ 60)` était doublement faux — risque de minutes déjà contenu dans l'EP, et seuil (60 min) qui n'est pas celui de la règle (0 minute). Le choix se fait par simulation directe du couple (c, v), jamais par formule composée.

**Incertitude.** Deux couches : l'aléa du football (irréductible, capturé par les tirages) et l'incertitude de paramètres (promu, recrue, nouvelle formule BPS), propagée en tirant aussi les paramètres [V1]. Sortie type : EP, p10/p50/p90, `P(retour ≥ 6)`, `P(blank ≤ 2)`. Les intervalles s'élargissent avec l'horizon, et cet élargissement est *le* traitement de la valeur temporelle des points futurs — pas un coefficient.

**Trois horizons.** (i) GW+1 : pleine information ; (ii) GW+2 à GW+5 : minutes en probabilités décroissantes, pas de cotes publiées → modèle d'équipe seul, intervalles élargis ; (iii) au-delà : taux par 90 × calendrier, uniquement pour la planification (chips, valeur de revente). Toute décision cite les trois.

**Calibration a posteriori — le vrai différenciateur.** Chaque semaine : fiabilité et log-loss sur les événements binaires (titularisation d'abord, puis CS, buteur, DEFCON), CRPS et histogrammes PIT sur les distributions, par position et tranche de prix. Une dérive déclenche une recalibration avant tout raffinement. Un modèle simple et calibré bat un modèle riche et non calibré pour *décider* [H, conviction forte].

## 6. L'optimisation de l'équipe — un générateur de candidats, pas un oracle

Repositionnement explicite : le MILP **ne résout pas le jeu**. Il résout exactement un sous-problème délibérément simplifié — et c'est sa valeur : produire vite des plans *faisables* et variés, que la simulation départage ensuite sur le vrai critère.

**Ce que le MILP couvre** (sous-problème déterministe, 4 à 6 GW, espérances figées en entrée) :

```
Variables : x[j,t] (effectif), y[j,t] (XI), b[j,t,r] (banc ordonné),
            in/out[j,t] (transferts), hits[t], ft[t] ∈ [0,5]
Contraintes [F◦] : effectif 15 (2/5/5/3) ; ≤3 par club ; XI 11 avec 1 GB, ≥3 DEF, ≥1 ATT ;
  continuité x[j,t] = x[j,t−1] + in − out ; budget avec prix d'achat et de vente
  FIGÉS à leurs valeurs connues du jour ; comptabilité ft/hits (−4 par transfert excédentaire)
Objectif : max Σ_t Σ_j EP(j,t)·y[j,t] + pondération de banc − 4·hits[t]
```

Sorties : les K meilleurs plans distincts (K ≈ 5–20, par coupes d'exclusion), pas un plan unique.

**Ce qui reste hors MILP, et où c'est traité.** (i) *Brassard et auto-substitutions* : logique événementielle non linéaire → simulation (section 5). (ii) *Prix futurs et revente dépendante du prix d'achat* : la valeur de vente dépend du prix payé et du chemin des prix — non linéaire et path-dépendant → prix figés au jour de la décision dans le MILP, scénarios de prix en analyse de sensibilité autour des candidats. (iii) *Free Hit, Wildcard, Bench Boost, Triple Captain* : jamais dans le MILP — chaque chip s'évalue par résolutions comparées (« avec chip à la GW g » vs « sans ») sur des scénarios de calendrier, arbitrées par simulation. (iv) *Les objectifs dépendant des rivaux* (`P(gagner la mini-ligue)`) : simulation uniquement. (v) *L'incertitude des EP* : le MILP consomme des moyennes ; tout ce qui est distributionnel se joue à l'étape suivante.

**L'arbitrage final, par simulation.** Les K candidats (plus « ne rien faire ») passent au simulateur : distribution des points cumulés et — critère principal — `ΔP(titre de mini-ligue)` sur le duel simulé (section 9). Décision = le candidat dominant, avec sa carte d'explication (section 10). Candidats statistiquement indiscernables : on le dit, et on choisit le moins coûteux en flexibilité.

**Le temps sans coefficient magique.** La V1 du dossier actualisait le futur par `γ = 0,84` — arbitraire, retiré. Le traitement honnête a trois morceaux : (1) l'incertitude croissante des projections lointaines est déjà dans leurs distributions élargies — les points de GW+5 « pèsent moins » parce qu'ils sont moins sûrs, pas par décret ; (2) la **valeur d'option d'un transfert conservé** s'estime par comparaison simulée — « agir maintenant » vs « attendre une semaine, laisser l'information se révéler, puis agir au mieux » : la différence des deux espérances *est* la valeur d'attente, recalculée à chaque décision au lieu d'être posée en constante ; (3) les **scénarios de calendrier** (reprogrammations, DGW/BGW probabilisés) entrent explicitement dans la comparaison des candidats. Si une pondération scalaire s'avère utile en V0 pour dégrossir, elle sera étiquetée [H], estimée par backtest et documentée — jamais un 0,84 posé d'avance.

## 7. Toutes les décisions FPL

Format : **règle décisionnelle → données requises → compromis risque/rendement.** Tout est produit en mode conseiller : recommandation argumentée, exécution humaine (paramètre acté).

**Sélection initiale (GW1).** Règle : générateur de candidats sur H = 6, incertitude d'avant-saison élargie ; ≥2 places de banc « jouables » (P(titularisation) > 70 %) ; aucun pari de minutes dans le XI. Compromis : une équipe sur-optimisée pour GW1 se paie en transferts dès GW3 — viser la trajectoire.

**Titulaires vs banc.** Règle : XI = argmax de l'espérance simulée d'équipe, auto-substitutions incluses — presque toujours les 11 meilleurs EP, sauf quand un EP légèrement supérieur porte une `P(0 minute)` élevée : la simulation arbitre. Compromis : quasi nul — la décision la plus mécanisable, et la première que le journal validera.

**Ordre du banc.** Règle : maximiser l'espérance des entrées par auto-substitution, en simulant les absences du XI et les contraintes de formation. Compromis : quelques points par saison, gratuits.

**Capitaine et vice — une décision jointe.** Règle : évaluer les couples (c, v) plausibles par simulation directe de la règle du brassard (section 5). En mode EV : maximiser `E[brassard(c,v)]` ; en mode mini-ligue : maximiser `ΔP(titre)` — selon la position, couverture du capitaine adverse ou différentiel à p90 élevé (section 9). Données : distributions jointes, brassards probables des rivaux. Compromis : le cœur du dosage hebdomadaire, là où l'objectif acté mord le plus tôt. Contrainte du vice : jamais un joueur dont le match peut être reporté en même temps que celui du capitaine.

**Transferts — et les conserver.** Règle : comparer par simulation trois familles de plans sur la fenêtre de 4–6 GW — « transférer maintenant », « conserver et décider la semaine prochaine » (avec révélation d'information simulée), « conserver deux semaines ». Transférer si « maintenant » domine ; la valeur d'option du transfert conservé sort de cette comparaison, elle n'est plus une constante (section 6). Données : projections multi-horizons, stock de FT, pressers à venir ; le risque de prix en correction marginale, jamais en motif principal. Compromis : sur-trader détruit l'espérance par churn ; sous-trader laisse pourrir des minutes mortes.

**Hits (−4).** Règle : accepter si le plan avec hit domine le meilleur plan sans hit d'au moins 4 pts d'espérance simulée sur la fenêtre, plus une marge de sécurité [H, à estimer sur notre propre journal — les modèles sont optimistes sur leurs propres swaps]. Exemple type : blessé (EP ~1/GW) remplacé par un titulaire à EP 5 sur 3 GW → dominance nette ; upgrade « pour le fixture » de +0,8 pt/GW sur 2 GW → refus. Compromis : un hit ajoute aussi de la variance ; en mode mini-ligue, le seuil bouge avec la position (section 9).

**Chips — choix et timing.** [F◦ : 2 jeux, frontière GW19/GW20] Méthode uniforme : pour chaque chip et chaque GW candidate, résolutions comparées avec/sans chip sur scénarios de calendrier, arbitrées par simulation — y compris `ΔP(titre)`. Lignes directrices : **Bench Boost** sur une DGW préparée, quand l'espérance simulée du banc dépasse nettement sa normale ; **Triple Captain** : chip de plafond, départagé par p90 et par l'état du duel, pas par la seule EP ; **Free Hit** : couvrir une BGW décimée ou saisir une DGW sans casser l'équipe ; **Wildcard 1** : correction structurelle quand les hiérarchies émergent (GW4–8 typiquement) ; **Wildcard 2** : la meilleure fenêtre du printemps. Contrainte dure : l'expiration du jeu 1 fin GW19 — alerte dès GW15, analyse d'exercice forcée avant expiration. Compromis : plus gros levier de variance de la saison ; en mini-ligue, le timing relatif aux chips *des rivaux* compte autant que le calendrier.

**Planification des doubles et blanks.** Les DGW/BGW naissent des reprogrammations de coupes [R chaque saison]. Règle : probabilités par GW mises à jour à chaque tour de coupe, chips planifiés en espérance sur ces scénarios, flexibilité maintenue à l'approche (stock de FT, banc jouable). Compromis : s'engager tôt capture prix et disponibilité, tard capture l'information.

**Bascule de stratégie selon rang / mini-ligue.** Ici, la bascule n'est pas un mode d'exception : **le mode mini-ligue est le mode par défaut** (paramètre acté). La politique EV-max sert de base ; l'écart à cette base est piloté par `ΔP(titre)` simulé, la position au classement, les GW restantes et les chips restants des deux côtés (section 9). Le rang global sert de benchmark : l'agent publie chaque semaine l'écart d'EV entre le plan choisi et le plan EV-max — le prix payé pour l'objectif — et ce prix doit rester explicite et borné.

## 8. Le cas Draft — hors périmètre, séparation maintenue

Paramètre acté : aucun module Draft en V0/V1. Cette section subsiste comme note de séparation et d'extension, pas comme spécification.

Ce qui interdit tout partage de logique décisionnelle avec le Classic [F◦] : pas de budget ni de prix (la couche capital disparaît), un joueur n'appartient qu'à un manager par ligue (la rareté remplace l'ownership), pas de capitaine ni de chips (la couche brassard et la couche options disparaissent), waivers traités 24 h avant deadline puis free agency, trades sous quatre régimes de veto. La valeur y est *relative au remplacement* : `VORP(j) = EP_saison(j) − EP_saison(meilleur disponible au poste)` — un cadre entièrement différent de l'EO. Contradiction relevée entre sources sur l'ordre de priorité des waivers (rolling officiel vs classement inversé sur plateformes tierces) : à trancher sur la ligue réelle le jour où le module s'ouvre [R].

Ce que l'architecture prépare sans rien construire : les projections par joueur (sections 3 et 5) sont agnostiques au format ; seules les couches valeur (VORP au lieu de prix/EO) et décisions (draft, waivers, trades, streaming au lieu de transferts/brassard/chips) seraient à écrire. Décision de conception : aucune abstraction commune prématurée — le jour venu, module séparé consommant les mêmes projections.

## 9. Game theory — gagner *ta* mini-ligue

**La quantité centrale : l'effective ownership locale.** `EO_locale(j)` = part des rivaux possédant j, brassards comptés double. Le gain de rang d'une GW se lit `Δ ∝ Σ_j (exposition(j) − EO_locale(j)) × points(j)` : posséder ce que toute la ligue possède ne fait rien bouger ; ne pas le posséder est une position courte. Dans une ligue de 6–20 managers, l'EO locale est un recensement exact, pas un échantillon : les équipes rivales se lisent après chaque deadline via l'API officielle (à confirmer au J0 [R]).

**Le duel simulé, cœur du système.** Chaque semaine : équipes rivales réelles + un modèle simple de leur politique (template ? brassard par défaut ? fréquence de hits ?), simulation jointe de la fin de saison — mêmes matchs simulés pour tous, corrélations entre rivaux automatiques — sortie : `P(titre)` par manager et sensibilité à chaque décision candidate. C'est le critère qui arbitre les candidats de la section 6.

**Règles de posture.** (i) La politique EV-max est la base ; on ne s'en écarte que si `ΔP(titre)` le justifie — le « différentiel pour être différent » est une taxe. (ii) La position change la convexité : en tête, couvrir (répliquer les fortes EO locales annule la variance relative des rivaux) ; derrière, diverger (plafond, anticorrélation avec le leader). (iii) Les GW restantes fixent l'agressivité : un retard modéré se comble par l'edge hebdomadaire s'il reste du temps ; en fin de saison, seuls les paris à forte variance déplacent `P(titre)` — le simulateur dit lesquels. (iv) Les chips restants des deux côtés sont des états du duel : garder un Triple Captain quand le rival a joué le sien est une option de rattrapage [H].

**Exemples concrets.** Leader de 12 pts, rival brassard sur Haaland : couvrir coûte ~0 en EV et neutralise l'essentiel de sa variance relative. Poursuivant à 25 pts à 4 GW de la fin : le TC « safe » maximise l'EV, le TC différentiel à p90 élevé maximise `P(titre)` — le simulateur chiffre l'écart, la carte de décision l'explique.

**Rang global (benchmark).** Politique EV-max implicite, suivie par le percentile hebdomadaire publié au tableau de bord. Aucune décision n'est prise *pour* le rang global tant que l'objectif mini-ligue est vivant ; le coût d'EV des choix mini-ligue est simplement mesuré et affiché (section 7).

## 10. Architecture de l'agent

Stack acté : Python, DuckDB, snapshots horodatés, dépôt Git local ; VPS seulement quand la fiabilité opérationnelle l'exigera. Douze modules, dimensionnés pour un binôme :

1. **Ingestion** — collecteurs par source : API FPL (quotidien + rafales pré/post-deadline), xG/événements (post-match), cotes gratuites (quotidien), nouvelles d'équipe (veille semi-manuelle en V0). Chaque collecte écrit un snapshot brut horodaté, immuable.
2. **Stockage** — snapshots bruts versionnés + DuckDB normalisé (joueur-match-GW), historique amorcé par les datasets communautaires, pedigree documenté.
3. **Validation des données** — schéma, fraîcheur, cohérence croisée, réconciliation DEFCON/BPS (section 3), quarantaine des aberrations. Une donnée non validée n'atteint jamais l'optimiseur.
4. **Couche point-in-time** — toute feature requêtable « telle que connue à T » ; production et évaluation partagent le même code.
5. **Prévisions** — modèles de la section 3, versionnés (données, hyperparamètres, calibration figées par version).
6. **Simulateur** — V0 : distributions par joueur + règle du brassard ; V1 : simulation jointe avec corrélations et duel de mini-ligue.
7. **Générateur de candidats** — le MILP de la section 6, K plans faisables + le plan « ne rien faire », jamais un plan unique.
8. **Mémoire** — journal structuré de chaque décision : date, versions de données et modèles, plan recommandé, alternatives figées avec leurs distributions, hypothèses actives, décision humaine finale (suivie ou non).
9. **Tableau de bord** — état de l'équipe, projections 3 horizons, calibration en cours, duel de mini-ligue (`P(titre)` par manager), percentile global, calendrier DGW/BGW probabilisé.
10. **Explications** — pour chaque recommandation, une carte en clair : *décision, espérance, risque (p10/p90), hypothèses critiques, alternatives rejetées, événement qui la ferait changer*. Pas de carte, pas de recommandation.
11. **Alertes** — signaux de révision (section 11) avec niveau de fiabilité de la source et plan B pré-calculé, toujours à destination de l'humain (paramètre acté).
12. **Journal d'audit** — trace immuable de toute lecture, calcul et recommandation.

## 11. Boucle opérationnelle — le rituel de deadline

Rythme type (deadline à H-90 du premier match [F◦]) :

- **Lendemain de GW, 09h00+ (post-verrouillage [F◦])** : ingestion des scores finaux, attribution (réalisé vs projeté, décision par décision), mise à jour des calibrations et des ratings ; archivage des compositions officielles de la GW écoulée pour l'entraînement et la validation du modèle de minutes.
- **J-6 à J-3** : projections 3 horizons ; surveillance des prix (mouvement nocturne [F◦], prédicteur officiel en entrée) ; pré-plans de transferts, aucune exécution.
- **J-2/J-1 — conférences de presse** : minutes mises à jour après chaque presser ; convergence des candidats ; hits argumentés en carte.
- **H-24** : arbitrage final par simulation (duel inclus) ; recommandations remises à l'humain : XI, banc ordonné, couple capitaine-vice, transfert ou conservation.
- **H-2 → deadline** : veille. Plan figé ; seules des **branches pré-résolues** peuvent le remplacer (« si X forfait selon source T1/T2 → plan B »). L'humain exécute. On n'improvise jamais dans les deux dernières heures.
- **Après la deadline** : lecture des équipes rivales dès publication, mise à jour du duel et de l'EO locale — matière de la semaine suivante.

**Signaux de révision urgente pré-deadline** (filtrés par fiabilité) : titulaire déclaré forfait (T1/T2), changement d'entraîneur, rotation massive annoncée en presser, report de match. **Explicitement retirés des déclencheurs de la GW courante : les fuites de compositions** — à H-90 la deadline est passée quand elles arrivent ; elles nourrissent la GW suivante et la validation de `P(titularisation)` (section 4). T3 (rumeurs) : annotation, jamais d'action.

**Verrouillé vs contrôle humain.** Saison 2026/27 entière : *toutes* les décisions sont exécutées par l'humain sur recommandation argumentée (paramètre acté) — y compris XI et ordre du banc. Ce que l'agent verrouille, c'est son propre processus : heures fixes, données figées, cartes obligatoires, journal complet. La question de l'exécution automatisée ne se rouvrira qu'après une saison de journal et un audit des conditions d'utilisation du jeu [R, bloquant] — il n'existe pas d'API d'écriture officielle documentée.

## 12. Évaluation — une échelle de preuve, pas un slogan

Correction assumée : « battre le template sur 8 GW » et « +1,5 pt d'EV par GW » ne prouvent rien — 8 observations d'une variable dont l'écart-type hebdomadaire se compte en dizaines de points ne distinguent pas un edge du bruit. L'évaluation est une **échelle à quatre niveaux**, chacun avec son horizon et son niveau de preuve accessible.

**Niveau 1 — Calibration des minutes (dès GW3–6).** Le premier verdict : Brier, log-loss et diagrammes de fiabilité de `P(titularisation)` par tranche, en fenêtres glissantes, contre deux baselines naïves (persistance « le XI passé rejoue » ; fréquence sur 6 GW). Tant que ce niveau n'est pas passé, rien d'autre n'a de sens — c'est le critère de passage V0 → suite.

**Niveau 2 — Calibration des composantes (mi-saison).** CS, buteur, DEFCON, distributions de points : fiabilité, log-loss, CRPS, PIT. Benchmark d'équipe : nos probabilités vs les cotes dé-vigées — si nous ne faisons pas mieux, les cotes restent l'ancrage et c'est très bien : l'edge peut venir entièrement des couches décision et mini-ligue [H, important].

**Niveau 3 — Qualité des décisions en temps réel (12–16 GW).** À chaque deadline, le journal fige la recommandation *et* des alternatives complètes : le XI template-EO du moment, « ne rien faire », le choix effectif d'Alexis s'il diverge. Comparaison par différences hebdomadaires appariées, intervalles bootstrap. Ce niveau valide le *processus* — il ne « prouve » pas un edge, et le tableau de bord l'affiche avec ses intervalles, pas en verdict.

**Niveau 4 — Edge de classement (≥ 1 saison complète).** Juger la capacité à gagner une mini-ligue exige au minimum une saison entière, intervalles à l'appui — et une saison reste peu : 38 observations d'un signal de quelques points par GW donnent des intervalles larges, on le dira tel quel. La décomposition `résultat = EV décidée + chance`, journalisée chaque semaine, est le seul antidote au jugement par les résultats : une décision se juge sur ce qu'elle savait, pas sur ce qu'il est advenu.

**Backtesting, avec ses limites dites.** Notre archive point-in-time commence au J0 2026/27 : les backtests multi-saisons reposent sur des archives tierces à la discipline de snapshot inégale (cotes de clôture contenant les compositions, statuts de blessure réécrits, prix sans horodatage) [R]. Conséquence : le backtest sert au développement des *composantes de prévision* ; la qualité *décisionnelle* s'évalue d'abord en prospectif, par le journal. Anti-overfitting : walk-forward par saison, peu d'hyperparamètres, priors forts, règles pré-enregistrées avant la saison, une saison de holdout, méfiance active envers tout signal sans mécanisme causal plausible. DEFCON n'existe que depuis 2025/26 et le BPS vient de changer [F◦] : sur ces composantes, l'histoire utile est courte et les conclusions resteront grossières.

## 13. Feuille de route — trois versions

**V0 — Conseiller Classic (4–6 semaines, budget quasi nul).** Périmètre acté, rien de plus : ingestion API FPL + snapshots horodatés ; minutes probabilistes (modèle simple + veille presser manuelle) ; projections par composante, cotes gratuites en ancrage ; recommandations hebdomadaires XI/banc ordonné, couple capitaine-vice simulé par la règle du brassard, « transférer vs conserver » ; journal complet avec alternatives figées. **Hors périmètre V0** : Draft, module de chips (ceux de l'automne se décident à la main, projections à l'appui), simulateur de saison complet, duel de mini-ligue automatisé, automatisation de compte, données payantes. Difficultés : fiabilité des collecteurs ; discipline du rituel ; résister à l'envie de tout modéliser. Critères de succès : protocole J0 exécuté (faits promus [F] ou corrigés) ; niveau 1 d'évaluation passé ; 100 % des décisions journalisées avec carte.

**V1 — Système robuste pour la saison.** Ajoute : simulation jointe avec corrélations ; duel de mini-ligue (lecture automatique des rivaux, `P(titre)` hebdomadaire) ; générateur de candidats MILP 4–6 GW + arbitrage simulé ; analyses de chips par scénarios, alerte d'expiration GW19 ; réconciliation DEFCON/BPS des sources externes ; API de cotes payante *si et seulement si* le niveau 1 est passé (paramètre acté). Difficultés : la couche point-in-time (le gros œuvre) ; la validation des corrélations ; les cas tordus (DGW, deadlines décalées). Critères : niveaux 1–2 passés, niveau 3 en cours avec intervalles publiés, chips de printemps décidés sur scénarios documentés.

**V2 — Vers la semi-autonomie (après une saison complète de journal).** Conditions d'ouverture, dans l'ordre : niveau 3 concluant sur 2026/27 ; audit des conditions d'utilisation pour toute exécution automatisée [R, bloquant] ; garde-fous éprouvés. Alors seulement : exécution des décisions à faible enjeu (ordre du banc, vice), branches pré-résolues sur signal T1, l'humain gardant transferts, hits, brassard et chips. Extension Draft : module séparé consommant les mêmes projections, si une ligue Draft redevient d'actualité. Métriques : zéro incident d'exécution, latence signal→recommandation < 5 min, niveau 4 mesuré sur deux saisons.

---

## Recommandation nette

**Le point de départ** : la V0, en commençant par le protocole J0 (vérification des faits à la source officielle depuis ta machine, promotion des [F◦]), puis le collecteur de snapshots et le modèle de minutes. Tout le reste — simulateur joint, MILP, duel de mini-ligue — s'appuie sur ces trois fondations, et aucune ne demande un centime.

**Le plus petit produit qui crée un avantage mesurable** : le conseiller de deadline hebdomadaire — XI + banc ordonné, couple capitaine-vice simulé, « transférer vs conserver » — avec journal et alternatives figées. « Mesurable » au sens de la section 12 : calibration des minutes d'abord (GW3–6), qualité du processus ensuite (12–16 GW, avec intervalles), aucune prétention d'edge prouvé avant une saison complète.

**Ce qu'il me faut pour démarrer la V0** (rien d'autre n'est bloquant) : ton team ID FPL et l'ID de la mini-ligue cible (comment les retrouver : `docs/guide-j0.md`), la liste de ses managers ; l'exécution du protocole J0 depuis ta machine (`scripts/j0_verification.py`, cinq minutes) ; et ton créneau hebdomadaire fixe pour la revue de deadline.

---

## Annexe — sources principales (21/08/2026)

Officielles, rattachées aux faits dans le tableau de l'avant-propos (accès direct bloqué depuis l'environnement de rédaction ; vérification J0 requise) : [changements FPL 2026/27](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627) · [chips](https://www.premierleague.com/en/news/4362085) · [DEFCON](https://www.premierleague.com/en/news/4361991/whats-happening-with-defensive-contribution-points-in-202627-fantasy) · [dates de saison](https://www.premierleague.com/en/news/4468487/dates-for-202627-premier-league-season-confirmed) · [Draft — trading](https://www.premierleague.com/en/news/1245445/fpl-draft-how-to-do-player-trading) · [mécanique des prix](https://www.premierleague.com/en/news/2858775).

Secondaires concordantes ayant servi de relais : [Fantasy Football Fix — nouveautés 2026/27](https://www.fantasyfootballfix.com/blog-index/fpl-2026-27-new-rules/) · [Fantasy Football Scout — changements](https://www.fantasyfootballscout.co.uk/2026/07/20/fpl-2026-27-5-rule-changes-new-features-announced) · [Flashscore — récap](https://www.flashscore.com/news/soccer-premier-league-fpl-rule-changes-defensive-contributions-double-chips-extra-free-transfers/xdGbtADF) · [Draft FC — règles](https://draftfc.co.uk/fpl-draft-rules) et [scoring](https://draftfc.co.uk/fpl-draft-scoring) · [LiveFPL — prix](https://livefpl.com/blog/fpl-price-changes). Outillage : [guide API FPL](https://medium.com/@frenzelts/fantasy-premier-league-api-endpoints-a-detailed-guide-acbd5598eb19) · [dataset vaastav](https://github.com/vaastav/Fantasy-Premier-League) · [FPL Core Insights](https://github.com/olbauday/FPL-Core-Insights) · [football-data.co.uk](https://www.football-data.co.uk/) (clôtures historiques).
