# Agent de décision autonome pour Fantasy Premier League — Dossier de conception

**Version 0.1 — 21 août 2026 (jour de la deadline GW1 de la saison 2026/27)**
**Auteurs : cofondateur quantitatif (Claude) & Alexis**

## Avant-propos : statuts épistémiques et sources

Trois statuts balisent tout le dossier : **[F]** fait confirmé par une source officielle (Premier League / FPL) ou la relayant explicitement ; **[H]** hypothèse de modélisation, à valider empiriquement ; **[R]** à revérifier chaque saison.

Transparence : lors de la recherche (21/08/2026), l'accès direct à `premierleague.com` et à Fantasy Football Scout était bloqué par notre proxy réseau. Les [F] proviennent de résumés de recherche citant les pages officielles et de sources secondaires concordantes. Première tâche du projet : re-valider chaque [F] sur `fantasy.premierleague.com/help/rules` et `draft.premierleague.com` — [R] global.

**Socle réglementaire 2026/27** [F] : effectif de 15 joueurs (2 GB, 5 DEF, 5 MIL, 3 ATT), budget 100,0 M£, maximum 3 joueurs par club ; XI avec 1 GB, ≥3 DEF, ≥1 ATT ; 1 transfert gratuit par Gameweek, cumulables jusqu'à 5, transfert excédentaire à −4 pts ; capitaine ×2, vice-capitaine en secours ; deux jeux de chips (2 Wildcards, 2 Free Hits, 2 Bench Boosts, 2 Triple Captains), le premier expirant fin GW19, le second dès GW20 ; contribution défensive (« DEFCON ») : 2 pts pour un défenseur à 10 actions CBIT (tacles, interceptions, blocks, dégagements), 2 pts pour un milieu/attaquant à 12 actions CBIRT (CBIT + récupérations), plafond 2 pts/match. Nouveautés 2026/27 [F] : BPS rééquilibré (moins de chevauchement avec DEFCON, gardiens et latéraux mieux servis, pénalité de dépossession supprimée), classements en temps réel, bonus projetés dès la 20e minute, verrouillage des scores à 09h00 UK le lendemain du dernier match, prédicteur officiel de prix mis à jour toutes les 15 minutes. Saison du 21 août 2026 au 30 mai 2027 [F]. Deadline à 90 minutes du premier coup d'envoi [F de longue date ; R].

---

## 1. La nature du jeu

FPL est l'empilement de six problèmes distincts. Les confondre — ce que fait presque tout le champ — laisse de l'espérance à chaque interface.

**Prévision.** L'unité de base est la distribution des points d'un joueur par Gameweek, `P(points_j,t = k)`, pas sa moyenne. Un attaquant à 5,0 pts espérés avec 30 % de chances de dépasser 10 pts et un milieu défensif à 5,0 dont 90 % de la masse tient entre 2 et 7 sont des actifs radicalement différents pour le capitanat, les chips et les mini-ligues.

**Allocation de capital.** 100 M£, des prix qui bougent chaque nuit de ±0,1 M£ selon les flux nets (seuils cachés) [F], et une revente asymétrique : moitié des hausses, totalité des baisses [F]. Le capital a une trajectoire ; c'est un rendement secondaire, subordonné aux points — le « team value maxing » inverse la hiérarchie.

**Optimisation sous contraintes.** À chaque deadline : 15 joueurs, un XI, un capitaine, un banc ordonné, sous budget, quotas, règle des 3 par club et stock de transferts. C'est un programme linéaire en nombres entiers, résoluble exactement en secondes (section 6). L'humain approxime ce que la machine résout.

**Décision séquentielle.** 38 deadlines liées : un transfert non utilisé devient une option (jusqu'à 5 en banque [F]), un chip joué n'existe plus en avril, un achat d'aujourd'hui se revend au prix de demain. La bonne formalisation : processus de décision markovien à horizon glissant, pas 38 décisions indépendantes.

**Gestion du risque.** La variance est une ressource à doser, structurée par les corrélations : trois joueurs d'Arsenal covarient, un capitaine double la variance de son porteur, un banc solide assure contre les minutes. On raisonne en portefeuille : espérance, variance, corrélations, queues.

**Théorie des jeux.** Le classement est relatif : gagner des points que 60 % du champ gagne aussi ne fait pas monter. La quantité pivot est l'*effective ownership* (section 9) — l'espérance de rang dépend des choix des autres. C'est ce problème qui sépare les cinq contextes (Classic, Draft, rang global, mini-ligue, formats à différenciation) ; les cinq autres leur sont largement communs.

## 2. Les fondamentaux d'un gagnant durable

Thèse : l'edge durable vient d'un petit nombre de compétences mesurables et systématisables, dont la hiérarchie ne suit pas le discours communautaire.

**1. La prévision des minutes — compétence n° 1.** [H, forte conviction] Un joueur à 6,0 pts espérés par 90 min qui en joue 55 vaut moins qu'un 4,8/90 indiscutable. La queue gauche des désastres FPL (banc gâché, capitaine sorti à la 60e, −4 pour un non-joueur) est un échec de minutes, pas de talent. Mesure : log-loss et calibration de `P(titularisation)` et `E[minutes]`. Systématisation : modèle dédié (section 3), priorité absolue de la V0.

**2. La lecture du calendrier.** L'edge n'est pas de voir qu'Arsenal–Coventry est favorable (tout le monde le voit) : c'est de planifier des blocs de 4–6 GW et les bascules, là où le champ réagit avec 1–2 GW de retard. Mesure : points captés par £ sur les fenêtres planifiées vs le champ. Systématisation : projections multi-horizons + optimiseur glissant.

**3. La discipline de capital.** Acheter avant les hausses quand les points justifient déjà l'achat, jamais *pour* la hausse ; connaître son vrai prix de revente. Mesure : points par £ du XI, valeur d'équipe ajustée de la revente. Le prédicteur officiel de prix toutes les 15 min [F] banalise un edge informationnel historique — exemple de signal devenu commodité.

**4. Le capitanat.** La décision à plus forte variance contrôlable, ~76 choix par saison. Mesure : « captaincy delta » = points du choix vs meilleur choix ex ante du modèle, et vs ex post. Systématisation : maximiser l'espérance *ou* un quantile selon le classement (section 9).

**5. Hits et chips.** Un −4 se compare au gain probabiliste multi-GW (section 7) ; un chip est une option réelle qui expire (fin GW19 pour le premier jeu [F]). Mesure : EV réalisée des hits ; valeur capturée par chip vs sa distribution de valeurs possibles.

**6. L'hygiène décisionnelle.** Décider à heure fixe, sur données figées, avec journal ; ne jamais réagir à un résultat. Mesure : part des décisions dans le processus, régret des décisions hors processus. C'est la compétence que l'agent fournit gratuitement : ni tilt, ni biais de récence, ni aversion asymétrique aux pertes.

**Tri des « règles » communautaires.** [H] Causal et robuste : minutes d'abord ; cotes des bookmakers comme meilleur prédicteur public ; régression des sur-performances xG. Corrélé mais confondu : la « forme » sur 5 matchs — surtout du bruit autour de talent + calendrier ; l'acheter revient souvent à acheter au sommet. Dépendant du profil de risque : « jamais de hit précoce », « capitaine premium à domicile toujours » — vrais en moyenne, faux en rattrapage. Bruit quasi pur : « momentum d'équipe », malédictions de chips, eye test d'un match isolé. Chaque heuristique communautaire est une hypothèse falsifiable à tester, jamais un préréglage.

## 3. Le modèle de décision

Principe : des modèles simples, bien calibrés, ancrés sur les marchés quand ils existent, plutôt que sophistiqués et non calibrables.

**Minutes et titularisation — le socle.** Modèle hiérarchique : `P(groupe)` × `P(titulaire | groupe)` × distribution des minutes (titulaire : masse vers 90 avec risque de sortie ; remplaçant : mélange {0, 10–30}). Estimation : gradient boosting ou logistique bayésienne sur compositions passées, schémas de rotation, congestion (Europe, coupes), statut déclaré en conférence de presse. Forces : meilleur ratio signal/effort du système. Limites : changements d'entraîneur, hiérarchies non annoncées ; la sortie doit rester une distribution. Condition d'usage : mise à jour après chaque presser et sur trigger tardif.

**Buts et assists.** Deux étages. (i) Équipe : Poisson bivarié type Dixon-Coles pour la distribution des scores, calibré sur les cotes 1X2/over-under, qui agrègent l'information mieux que nos features [H]. (ii) Joueur : partage du gâteau offensif par npxG/90 et xA/90 (Understat/FBref), penalties et coups de pied arrêtés, conditionné aux minutes simulées. Le talent de finition est rétréci vers la moyenne (shrinkage bayésien) : l'écart réalisé vs xG sur une demi-saison est surtout du bruit hors finisseurs d'élite [H]. Limites : recrues et promus (Coventry, Hull) sans historique PL — prior par cotes et championnat d'origine, incertitude élargie.

**Clean sheets.** Sous-produit du modèle d'équipe : `P(CS) = P(0 but encaissé)` × `P(minutes ≥ 60)` du défenseur, ancré sur les cotes CS. Piège : la CS est commune à toute la défense — jamais indépendante entre coéquipiers ; cela gonfle la variance d'une défense empilée (utile en Bench Boost, dangereux en mini-ligue serrée).

**Bonus.** Modéliser le BPS, pas le bonus : régression des composantes BPS sur les statistiques simulées, puis attribution 3/2/1 par classement simulé. Le BPS 2026/27 a été rééquilibré [F] : tout historique pré-2026 doit être retraité [R] ; en attendant les données, une approximation `E[bonus] = f(buts, assists, CS, DEFCON, saves)` recalibrée en cours de saison suffit [H].

**Cartons, CSC, penalties manqués.** Faible signal : base rates par joueur/arbitre, intégrés pour l'honnêteté de la queue gauche, sans y chercher d'edge.

**DEFCON.** Gisement systématisable : modèle de comptage (binomiale négative) des CBIT/CBIRT par 90 selon rôle et possession adverse projetée → `P(CBIT ≥ 10)` défenseur, `P(CBIRT ≥ 12)` milieu [F sur les seuils]. Les stoppeurs d'équipes dominées et milieux récupérateurs gagnent une valeur plancher que le marché FPL sous-évalue encore [H — le champ apprend vite].

**Blessures, rotations, changements de rôle.** Les modèles de survie prédisent mal : priors grossiers (fragilité, âge, surcharge) et surtout réaction rapide à l'information (section 11). Les changements de rôle (nouveau tireur de penalty, repositionnement) se détectent par ruptures de features (touches dans la surface, ordre sur coups de pied arrêtés) — détecteur de drift avec alerte humaine.

**Adversaires et calendrier.** Ratings attaque/défense continus réestimés chaque semaine, avantage domicile ; effets de congestion, d'Europe et de trêves — réels mais modestes, régularisation forte [H]. Spécifique 2026/27 : saison post-Coupe du monde, fatigue des internationaux sans historique fiable — traitée en incertitude élargie, pas en effet moyen [H].

## 4. Les données

Architecture : chaque source est capturée en **snapshots horodatés immuables** (object store), puis normalisée dans un entrepôt (Postgres/DuckDB) sous une couche de features *point-in-time* : on ne peut interroger que ce qui était connu à l'instant T. Condition non négociable du backtesting sans leakage (section 12).

**Famille 1 — Officielles (API FPL).** Endpoints publics non documentés mais stables : `bootstrap-static` (joueurs, prix, ownership global, statuts de blessure, calendrier), `fixtures`, `element-summary/{id}`, `event/{gw}/live`, endpoints de ligue (équipes des rivaux lisibles après deadline). Fréquence : quotidienne + rafales pré/post-deadline. Fiabilité : référence absolue pour prix, propriété, règles ; les flags de blessure officiels sont en revanche *lents* — ils suivent la presse. Usage : univers de décision, contraintes, résultats, ownership. Risque : API non contractuelle, schéma mouvant chaque été [R].

**Famille 2 — Performance.** Understat (xG/xA par tir), FBref (données Opta : actions défensives indispensables au DEFCON), datasets communautaires (vaastav/Fantasy-Premier-League pour l'historique multi-saisons). Fréquence : post-match, latence de quelques heures. Fiabilité : bonne, mais définitions d'xG hétérogènes — ne jamais mélanger deux fournisseurs dans une feature. Usage : taux par 90, priors de talent. Risques : scraping fragile, licences à clarifier pour usage non personnel [R].

**Famille 3 — Marché (cotes).** 1X2, over/under, clean sheet, buteur anytime via agrégateur (The Odds API), clôtures historiques (football-data.co.uk) pour l'entraînement. Fréquence : quotidienne, horaire en approche de match. Fiabilité : le prédicteur public le mieux calibré des issues d'équipe [H solide]. Usage : ancrage des modèles d'équipe après retrait de la marge, prior buteur. Risques : les cotes n'intègrent les compositions qu'à ~1h du match, après notre deadline ; couverture inégale des marchés joueurs ; coût.

**Famille 4 — Nouvelles d'équipe.** Conférences de presse (jeudi/vendredi), agrégateurs de blessures (Premier Injuries, Ben Dinnery), journalistes de club, fuites de compositions à ~1h. La famille au plus fort impact et à la fiabilité la plus variable, d'où un **filtre à trois niveaux** : T1 officiel — action automatique ; T2 journaliste de club établi — action si le coût est faible (changement de XI, pas un hit) ; T3 ITK/rumeur — alerte humaine uniquement. Chaque source porte un score de fiabilité historique (précision vérifiée a posteriori) qui module le filtre [H].

**Famille 5 — Signaux communautaires.** Ownership et EO du top 10k (LiveFPL), prédicteurs de prix, templates, sentiment. Fréquence : quotidienne. Usage : exclusivement pour la couche théorie des jeux (section 9) et l'anticipation des prix — jamais comme signal de qualité d'un joueur : le consensus est déjà dans les prix et l'ownership, l'imiter n'apporte aucun edge par construction. Biais : herding, sur-réaction au dernier match, échantillons « top 10k » non représentatifs.

## 5. Le moteur de projection

Le livrable central n'est pas un « expected points » par joueur : c'est la **distribution jointe** des points de tous les joueurs pertinents, par GW, avec ses corrélations. L'EP en est la moyenne ; les décisions difficiles se prennent dans les queues.

**Décomposition.**

```
points(j,m) = pts_minutes + pts_buts + pts_assists + pts_CS + pts_DEFCON
            + pts_saves + pts_bonus − malus (cartons, buts encaissés…)
EP(j,m) = Σ_composantes E[composante | rôle, adversaire, minutes]
```

**Simulation Monte Carlo (implémentation de référence).** Par GW, N ≈ 10 000 tirages : (1) scénario de minutes de chaque joueur — la racine de l'arbre ; (2) score de chaque match (Poisson bivarié calibré sur les cotes) ; (3) allocation multinomiale des buts/assists aux joueurs présents, pondérée par les taux individuels ; (4) comptages DEFCON, saves, cartons ; CS et malus déduits du score ; (5) BPS simulé → bonus 3/2/1 ; (6) agrégation : distributions par joueur **et corrélations gratuites** — coéquipiers liés par le même score simulé, capitaine corrélé à son porteur, adversaires anticorélés. Cette structure jointe permet de simuler une équipe entière (auto-substitutions et vice-capitaine appliqués règle par règle) et de répondre en distribution : `P(équipe > 70 pts)`, `P(battre le rival R)`, plafond (p90), plancher (p10).

**Incertitude.** Deux couches : l'aléa du football (irréductible, capturé par la simulation) et l'incertitude de paramètres (talent d'un promu, rôle d'une recrue), propagée en tirant aussi les paramètres de leur postérieure ou par ensembles. Sortie type : EP, p10/p50/p90, `P(retour ≥ 6)`, `P(blank ≤ 2)`, variance. Les intervalles s'élargissent avec l'horizon.

**Trois horizons systématiques.** (i) GW+1 : pleine information, distributions fines ; (ii) GW+2 à GW+5 : minutes en probabilités décroissantes, pas de cotes publiées → modèle d'équipe seul ; (iii) long terme : taux par 90 × calendrier, pour la valeur de revente et les chips. Toute décision cite les trois.

**Calibration a posteriori — le vrai différenciateur.** Chaque semaine : diagrammes de fiabilité et log-loss sur les événements binaires (titularisation, CS, buteur), CRPS et histogrammes PIT sur les distributions, par position et tranche de prix. Une dérive détectée déclenche une recalibration isotonique avant tout raffinement. Règle de culture : un modèle simple et calibré bat un modèle riche et non calibré pour *décider* [H, conviction forte].

## 6. L'optimisation de l'équipe

Formulation MILP, résoluble exactement (HiGHS/CBC via PuLP). Notations : t ∈ {1..H} (horizon glissant, H ≈ 6–8), j les joueurs, p(j) le poste, c(j) le club.

**Variables binaires** : `x[j,t]` (effectif 15), `y[j,t]` (XI), `cap[j,t]`, `vice[j,t]`, `b[j,t,r]` (banc rang r), `in[j,t]`, `out[j,t]` ; entières : `hits[t] ≥ 0`, `ft[t] ∈ [0,5]`.

**Contraintes** [F pour toutes les règles] :

```
Σ_j x[j,t] = 15 ; quotas 2 GB / 5 DEF / 5 MIL / 3 ATT
Σ_{j: c(j)=c} x[j,t] ≤ 3                     ∀ club c
Σ_j y[j,t] = 11 ; y ≤ x ; 1 GB ; ≥3 DEF ; ≥1 ATT
Σ cap = 1 ; Σ vice = 1 ; cap+vice ≤ y
x[j,t] = x[j,t−1] + in[j,t] − out[j,t]
B[t] = B[t−1] + Σ sell(j)·out[j,t] − Σ prix(j,t)·in[j,t] ≥ 0
   sell(j) = achat(j) + floor((prix(j,t) − achat(j))/2)  si profit, prix courant sinon
n[t] = Σ_j in[j,t] ; hits[t] ≥ n[t] − ft[t]
ft[t+1] = min(5, ft[t] − n[t] + hits[t] + 1)   (linéarisé par bornes)
```

**Objectif** :

```
max Σ_t γ^t [ Σ_j EP(j,t)·(y[j,t] + cap[j,t]) + Σ_{j,r} π_r·EP(j,t)·b[j,t,r] − 4·hits[t] ]
    + λ_V·ValeurRevente(x[·,H]) + λ_F·AttraitCalendrier(x[·,H])
```

où `γ ≈ 0,84`/GW [H] actualise l'incertitude croissante (une espérance à GW+5 pèse ~40 % d'une espérance à GW+1), `π_r` est la probabilité d'entrée du banc de rang r par auto-substitution (estimée par simulation), et les termes terminaux évitent la myopie de fin d'horizon (équipe vidée de valeur de revente ou face à un mur de fixtures). Les blocs de fixtures sont capturés naturellement : EP(j,t) varie par adversaire, l'optimiseur voit les fenêtres.

**Au-delà de l'espérance.** Le MILP est aveugle aux distributions. Deux extensions : (i) terme de variance signé dans l'objectif (`+ κ·σ(équipe)`, κ selon le contexte de classement) via les covariances simulées ; (ii) optimisation par scénarios : S ≈ 200 tirages Monte Carlo, maximiser un quantile ou `P(battre le rival)` — indispensable pour mini-ligues et chips, où l'espérance est le mauvais critère. En pratique : le MILP-espérance génère 5–10 candidats proches, la simulation complète les départage — exactement le cas d'usage « Monte Carlo quand les décisions sont proches ».

**Horizon glissant.** À chaque deadline : résoudre sur H GW, n'exécuter que la GW courante, recommencer avec l'information nouvelle. Chips planifiés par méta-optimisation : MILP avec/sans chip à chaque GW candidate, comparaison des trajectoires (section 7).

## 7. Toutes les décisions FPL

Format : **règle décisionnelle → données requises → compromis risque/rendement.**

**Sélection initiale (GW1).** Règle : MILP sur H = 8 avec γ réduit (0,80 : incertitude d'avant-saison maximale) ; ≥2 places de banc « jouables » (P(titularisation) > 70 %) ; aucun pari de minutes dans le XI. Données : cotes d'avant-saison, minutes de préparation, hiérarchies déclarées. Compromis : une équipe sur-optimisée pour GW1 se paie en transferts dès GW3 — viser la meilleure *trajectoire*.

**Titulaires vs banc.** Règle : XI = argmax de l'espérance simulée d'équipe, auto-subs incluses — presque toujours les 11 meilleurs EP, sauf quand un EP légèrement supérieur porte une `P(0 minute)` élevée : la simulation arbitre. Données : minutes, EP. Compromis : quasi nul — la décision la plus mécanisable.

**Ordre du banc.** Règle : maximiser `Σ_r π_r·EP(banc_r)` en simulant les absences du XI et les contraintes de formation qui conditionnent qui peut entrer. Compromis : quelques points par saison, gratuits.

**Capitaine.** Règle en mode EV : `argmax EP(j) × P(minutes ≥ 60)` ; en mode différenciation (section 9) : maximiser l'espérance de *gain de rang*, qui peut désigner un choix à EO faible et p90 élevé. Données : distributions complètes (EP *et* variance), EO du champ pertinent. Compromis : le cœur du dosage hebdomadaire. Exemple : capitaine EO 90 % à EP 8,1 vs différentiel EO 8 % à EP 7,3 — l'EV dit le premier ; à 30 pts de retard en mini-ligue à 6 GW de la fin, le second gagne souvent en probabilité de titre.

**Vice-capitaine.** Règle : parmi les quasi-certains (P(jouer) > 95 %), maximiser EP conditionnel au forfait du capitaine ; éviter le même match que le capitaine si un scénario de report existe. Compromis : assurance gratuite.

**Transferts — et les conserver.** Règle : transférer si

```
ΔEV = Σ_{t=1..K} γ^t [EP(in,t) − EP(out,t)] + ΔValeurRevente − CoûtOption > 0
```

où `CoûtOption` est la valeur du transfert gratuit conservé — l'option d'attendre une meilleure information (≈ 0,3–0,8 pt selon l'incertitude pendante [H] ; ~0 à 5/5 en banque, maximal à 0/5). Banquer est le défaut quand ΔEV est petit : l'information arrive gratuitement, pas les transferts. Données : projections multi-horizons ; le risque de hausse/baisse de prix en correction marginale, jamais en motif principal. Compromis : sur-trader détruit l'EV par churn ; sous-trader laisse pourrir des minutes mortes — l'agent tranche par calcul, pas par tempérament.

**Hits (−4).** Règle : accepter si `ΔEV(K GW) > 4 + marge` (marge ≈ 1 pt [H], contre l'optimisme des modèles sur leurs propres swaps). Exemples : blessé (EP 1,0/GW) remplacé par un titulaire à EP 5,2 sur 3 GW ≈ +12,6 − 4 = +8,6 → hit clair ; « pour le fixture », un 4,8 remplacé par un 5,6 sur 2 GW = +1,6 − 4 → refus. Compromis : chaque hit ajoute de la variance (jugement frais) — seuil relevé en protection d'avance, abaissé en rattrapage.

**Chips — choix et timing.** [F : 2 jeux, frontière GW19/GW20] Règle générale : chaque semaine, valeur d'exercice aujourd'hui vs distribution des valeurs futures restantes (arrêt optimal approché par simulation du calendrier). **Bench Boost** : exercer si `E[points du banc] >` ~12–15 pts [H], typiquement une DGW préparée au wildcard. **Triple Captain** : chip de *plafond* — cible une DGW d'un premium contre deux faibles ; départager par p90, pas par EP. **Free Hit** : couvrir une BGW décimée ou capturer une DGW sans détruire l'équipe ; valeur = points de la GW jouée − points de l'équipe normale, maximale quand celle-ci s'effondre ponctuellement. **Wildcard 1** : correction structurelle (souvent GW4–8, quand les hiérarchies réelles émergent) ou pivot de bloc de fixtures. **Wildcard 2** : préparer la meilleure fenêtre DGW/BGW du printemps. Contrainte dure : le jeu 1 expire fin GW19 — l'agent force l'exercice avant expiration même à valeur médiocre. Compromis : plus gros levier de variance de la saison — c'est ici que le mode (rang global vs mini-ligue) change le plus la politique.

**Planification des doubles et blanks.** Les DGW/BGW naissent des reprogrammations de coupes [R chaque saison]. Règle : maintenir des probabilités par GW (`P(GW29 blank | clubs en FA Cup)`), planifier les chips en espérance sur ces scénarios, garder de la flexibilité (stock de FT, banc large) à l'approche des fenêtres probables. Compromis : s'engager tôt capture prix et disponibilité, tard capture l'information — trade-off quantifié chaque GW.

**Bascule de stratégie selon rang / mini-ligue.** Règle-cadre (détail section 9) : maximiser `P(objectif final)` et non l'EP dès que les deux divergent. Le leader de mini-ligue *couvre* (réplique les menaces à EO locale élevée) ; le poursuivant *diverge* (plafond, anticorrélation avec le leader) ; le joueur de rang global suit l'EV pur puis ajuste en fin de saison. Données : équipes des rivaux (lisibles via l'API après deadline [F]), EO locale, GW restantes, écart. Compromis : le méta-paramètre du système — il ne change pas les modèles, il change la fonction objectif.

## 8. Le cas Draft — un jeu cousin, jamais confondu

Différences structurelles [F] : pas de budget ni de prix, chaque joueur PL n'appartient qu'à un manager par ligue, pas de capitaine, pas de chips ; scoring identique au Classic par ailleurs, bonus et DEFCON inclus d'après les sources spécialisées — à re-confirmer sur `draft.premierleague.com` [R]. Conséquence : **toute la couche prix/ownership/EO disparaît, remplacée par la rareté** — la valeur d'un joueur est relative au meilleur disponible à son poste, pas à un prix.

**Valeur relative : VORP.** `VORP(j) = EP_saison(j) − EP_saison(remplacement(p(j)))`, le niveau de remplacement étant le meilleur joueur du poste vraisemblablement disponible en free agency (ligue de 8 : 120 joueurs retenus). Les courbes de rareté par poste pilotent tout : si la courbe des milieux s'aplatit après le 10e mais décroche chez les attaquants après le 6e, l'attaquant rare passe devant un milieu à EP supérieur. Sans capitanat, la *régularité* (plancher, minutes sûres) prend un premium par rapport au Classic où le plafond est monétisé par le brassard [H].

**Draft initiale (snake).** Règle : à chaque pick, `argmax VORP` ajusté de `P(survie jusqu'au pick suivant)` (estimée par ADP communautaire ou par les besoins adverses). Les coudes du snake favorisent les stratégies par paires. Les minutes priment encore plus qu'en Classic : sans marché de correction fluide, un pick de rotation gâche un actif pour des semaines.

**Enchères (le cas échéant).** La plateforme officielle ne propose que le snake [R — non retrouvé en source officielle ; l'auction existe sur des plateformes tierces]. Si enchères : valorisation en % du budget par VORP normalisé, plafonds par joueur fixés avant séance, jamais dépassés (anti winner's curse).

**Waivers et priorités.** Fonctionnement [F] : demandes classées, traitement 24 h avant la deadline, puis free agency premier arrivé–premier servi. Priorité initiale : inverse de l'ordre de draft ; une demande satisfaite renvoie en fin de file (rolling). **Contradiction relevée entre sources** : une source décrit une priorité par classement inversé (usage de plateformes tierces), l'autre le rolling order — à trancher dans la configuration de la ligue réelle [R]. Règle : une réclamation dépense un actif (la priorité) → exécuter si `ΔEP_horizon × durabilité > valeur d'option de la priorité` ; brûler sa priorité pour un stream d'une semaine est presque toujours une erreur ; la garder pour le retour de blessure majeur ou le breakout durable est la norme [H]. La free agency, gratuite, absorbe les streams : y être rapide (alertes automatiques sur tout joueur de valeur droppé) est un edge mécanique que l'agent fournit trivialement.

**Trades.** Règle : proposer/accepter si le gain est positif aux VORP *selon notre modèle* et si l'échange reste attractif selon le narratif public de l'adversaire — vendre la sur-performance xG, acheter la sous-performance. Vérifier le régime de veto de la ligue (4 réglages possibles [F]).

**Streaming.** Les postes 5e milieu / 3e attaquant / 2e gardien tournent sur les fixtures : `argmax EP(GW+1)` sur les libres, avec un œil sur GW+2 pour économiser un mouvement. Le gardien est le streaming le plus rentable via la variance des cotes CS [H].

## 9. Game theory — jouer contre le champ, pas contre le jeu

**La quantité centrale : l'effective ownership.** `EO(j) = ownership(j) + part_capitaine(j) (+ triple)` dans la population de référence (top 10k pour le rang global, les N rivaux en mini-ligue). Le gain de rang d'une GW se lit `Δrang ∝ Σ_j (exposition(j) − EO(j)) × points(j)`. Posséder un joueur à EO 100 % ne rapporte aucun rang : c'est une couverture ; ne pas le posséder est une position courte. Tout le jeu relatif tient dans cette phrase.

**Arbitrage populaires vs différentiels.** (i) En régime d'espérance, l'EV des points prime : on prend le différentiel seulement s'il est aussi (quasi) le meilleur choix en EV — le « différentiel pour être différent » est une taxe. (ii) La position au classement change la convexité de l'objectif : derrière, la fonction de gain est convexe → chercher variance et anticorrélation avec les rivaux ; devant, concave → couvrir les menaces (posséder ce que le rival possède annule sa variance relative). (iii) Les GW restantes fixent le taux d'actualisation du risque : 40 pts de retard se comblent par l'EV sur 20 GW (~2 pts/GW d'edge [H]), mais exigent des paris à 5 GW de la fin. Formellement : choisir d maximisant `P(Σ écarts futurs > retard | d)` — le simulateur le calcule en simulant *les deux équipes* avec leurs corrélations.

**Mini-ligue : le duel simulé.** Après chaque deadline, lire les équipes rivales via l'API [F], estimer leur politique (suivent-ils le template ? capitaine par défaut ?), simuler la fin de saison jointe (10 000 trajectoires) et piloter par `ΔP(titre)` plutôt que ΔEP. Exemples : couvrir le capitaine Haaland d'un rival menant de 10 pts coûte ~0 d'EV et supprime une grande part de sa variance relative ; en chasse à 25 pts à 4 GW de la fin, un Triple Captain sur un différentiel à p90 = 24 bat le TC « safe » en probabilité de titre tout en perdant en EV.

**Rang global.** Le champ pertinent est l'EO du voisinage du rang visé (les EO top 10k diffèrent du global). Politique : EV-max tant que le rang cible reste dans l'intervalle central de la trajectoire simulée ; bascule en mode variance (différentiels corrélés entre eux, chips à plafond) quand `P(cible | politique EV) < seuil`. La bascule est une décision datée et journalisée, pas une humeur.

**Formats à différenciation dominante** (head-to-head, cash leagues, très petites ligues) : anticiper les choix adverses pèse autant que prévoir le football ; des stratégies en réponse au champ deviennent viables. Module d'opponent modeling dédié, hors périmètre V1 [H].

## 10. Architecture de l'agent

Douze modules, tous réalisables en stack Python standard (cron/Prefect, Postgres + object store, PuLP/HiGHS, pandas/scikit-learn, LLM optionnel pour les explications).

1. **Ingestion** — collecteurs par source : API FPL (horaire + rafales pré/post-deadline), scrapers xG/FBref (post-match), cotes (quotidien, horaire J-1), nouvelles d'équipe (événementiel), signaux communautaires (quotidien). Chaque collecte écrit un snapshot brut horodaté, immuable.
2. **Stockage** — lac de snapshots bruts + entrepôt normalisé (joueur-match-GW), historique multi-saisons amorcé par les datasets communautaires.
3. **Validation des données** — schéma, fraîcheur (alerte si une source n'a pas publié à l'heure), cohérence croisée (prix API vs prédicteur officiel ; minutes FBref vs FPL), quarantaine des aberrations. Une donnée non validée n'atteint jamais l'optimiseur — premier garde-fou anti-automatisation aveugle.
4. **Feature store point-in-time** — toute feature est requêtable « telle que connue à T » ; production et backtest partagent le même code.
5. **Prévisions** — modèles de la section 3, versionnés en registre (données, hyperparamètres, calibration figées par version).
6. **Simulateur Monte Carlo** — section 5 ; expose `simuler(GW, équipes[, politique])` pour joueurs, équipes, duels de mini-ligue.
7. **Optimiseur** — section 6 ; produit systématiquement le top 5 des plans candidats avec leurs distributions, jamais un plan unique.
8. **Mémoire** — journal structuré de chaque décision : date, versions de données et modèles, plan choisi, alternatives rejetées avec leurs EV, hypothèses actives. Matière première de l'évaluation.
9. **Tableau de bord** — état de l'équipe, projections 3 horizons, calibration, calendrier DGW/BGW probabilisé, position vs rivaux.
10. **Explications** — pour chaque recommandation, une carte en clair : *décision, espérance, risque (p10/p90), hypothèses critiques, alternatives rejetées, événement qui la ferait changer*. Règle de conception : pas de carte, pas de proposition.
11. **Alertes** — triggers de révision urgente (section 11), avec fiabilité de la source et action conditionnelle pré-calculée.
12. **Journal d'audit** — trace immuable de toute action (lectures, calculs, recommandations, exécutions futures).

## 11. Boucle opérationnelle — le rituel de deadline

Rythme type (deadline samedi ; officiellement H-90 min du premier match [F]) :

- **Lendemain de GW, 09h00+ (post-lockdown [F])** : ingestion des scores finaux, attribution (EV réalisée vs projetée, par décision), mise à jour des calibrations et des ratings d'équipes.
- **J-6 à J-3** : recalcul des projections 3 horizons ; surveillance des prix (mouvement de minuit [F], prédicteur officiel en entrée) ; pré-plan de transferts (top 5 du MILP), **aucune exécution**.
- **J-2/J-1 (conférences de presse)** : mise à jour des minutes après chaque presser ; convergence du plan ; hits argumentés en carte de décision.
- **H-24** : solve final (MILP + départage Monte Carlo). Verrouillables dès ici : ordre du banc, vice-capitaine.
- **H-2 → deadline** : veille pure. Plan figé, mais chaque décision porte ses **conditions de révision** pré-calculées : « si X annoncé forfait par source T1/T2 → plan B (déjà résolu) ». On n'improvise jamais dans les deux dernières heures ; on exécute des branches préparées.
- **Pendant les matchs** : aucune décision à prendre en Classic ; collecte pour l'attribution.

**Signaux de révision urgente** (filtrés par fiabilité, section 4) : titulaire forfait ou transféré ; changement d'entraîneur ; rotation massive annoncée ; composition fuitée contredisant une `P(titularisation) > 80 %` ; report de match. Seuils : T1 → exécution automatique du plan B autorisée (V2+) ; T2 → notification avec recommandation ; T3 → simple annotation.

**Verrouillé vs contrôle humain.** V1 : tout passe par validation humaine. V2 : exécution directe pour l'ordre du banc, le vice-capitaine, le XI sans ambiguïté (ΔEV > 1 pt) ; contrôle humain pour transferts, hits, capitaine différentiel, chips — l'irréversible à fort levier. V3 : l'humain garde les chips et un veto à H-2. Garde-fous permanents : budget de risque hebdomadaire (au plus 1 hit sans validation, jamais de chip auto), interdiction d'agir sur donnée non validée ou source non fiabilisée — les faux signaux communautaires (faux ITK, hoax de blessure) sont précisément le vecteur d'attaque d'un agent trop automatique.

## 12. Évaluation — savoir si l'on est bon, et pourquoi

**Backtesting sans leakage.** Rejouer les saisons passées en n'exposant, à chaque deadline historique, que les snapshots antérieurs (d'où le feature store point-in-time). Pièges concrets : les cotes de clôture contiennent les compositions, postérieures à notre décision — utiliser des cotes horodatées H-24 ; certains dumps réécrivent rétroactivement les statuts de blessure ; les prix historiques doivent porter l'heure du relevé. Un backtest qui bat le champ avec des données de clôture ne prouve rien.

**Baselines pertinentes** (toutes rejouables) : (i) l'équipe « template EO » — XI des plus fortes EO top 10k, capitaine le plus capitainé : LA baseline à battre, elle encode le consensus gratuit ; (ii) set-and-forget : meilleure équipe GW1 jamais touchée ; (iii) EP-naïf : décisions pilotées par la moyenne des points passés ; (iv) la distribution réelle des managers (percentiles publics par GW). Définition de l'edge : battre (i) de façon répétée sur des saisons non vues.

**Qualité des prédictions.** Log-loss et calibration par composante (titularisation, CS, buteur), CRPS sur les distributions de points, et comparaison systématique au marché : si nous ne battons pas les cotes dé-vigées, on les utilise — les battre n'est pas un prérequis, l'edge peut venir entièrement des couches optimisation et théorie des jeux [H, important].

**Décisions perdantes à bonne espérance.** Décomposer chaque semaine `résultat = EV décidée + chance` : une décision se juge sur l'EV qu'elle avait avec l'information du moment (enregistrée en mémoire), pas sur son issue. Deux courbes cumulées au tableau de bord : « EV capturée vs alternative » et « écart de réalisation ». EV décidée positive et résultats négatifs → on tient bon ; EV décidée qui se dégrade → on cherche le bug. Seul antidote institutionnel au results-oriented thinking.

**Anti-overfitting.** Walk-forward par saison entière, jamais de mélange intra-saison ; peu d'hyperparamètres, priors forts ; règles de décision pré-enregistrées avant chaque saison, protocole immuable en cours de route sauf incident documenté ; une saison de holdout jamais touchée ; méfiance active envers tout signal sans mécanisme causal plausible (les « effets » d'arbitre ou de pelouse sur les points FPL sont des pièges classiques de data mining). Accepter la borne : règles stables depuis peu (DEFCON n'existe que depuis 2025/26 [F]), 38 observations par saison — les conclusions doivent rester grossières et robustes, pas fines et fragiles.

## 13. Feuille de route — trois versions

**V0 — Prototype utile (4–6 semaines).** Livrables : ingestion API FPL + cotes + un dataset xG ; modèle de minutes v1 (logistique + veille presser manuelle) ; EP par décomposition ancrée sur les cotes ; MILP mono-GW + horizon 4 simplifié ; recommandations hebdomadaires (transferts, capitaine, XI, banc) avec cartes d'explication ; journal de décisions. Données : gratuites uniquement. Difficultés : fiabilité des scrapers ; calibration avec peu de recul ; résister à la tentation de tout modéliser. Métriques de succès : log-loss de P(titularisation) < baseline naïve ; battre la baseline template-EO sur 8+ GW glissantes ; 100 % des décisions journalisées. Priorité : une boucle complète bout-en-bout, même grossière, avant tout raffinement.

**V1 — Système robuste pour une saison.** Livrables : simulateur Monte Carlo complet avec corrélations ; optimiseur glissant H=8 avec valeur terminale ; planificateur de chips et DGW/BGW probabilisé ; filtre de fiabilité des sources ; tableau de bord ; backtests propres sur 3 saisons. Données : API de cotes payante, ownership top-10k. Difficultés : le feature store point-in-time (le gros œuvre) ; la validation des corrélations du simulateur ; les cas tordus du MILP (DGW = deux matchs par joueur, deadlines décalées). Métriques : CRPS stable ; EV décidée cumulée > +1,5 pt/GW vs template-EO [H comme cible] ; zéro décision hors processus ; chips joués dans le quartile supérieur de leur distribution de valeur simulée.

**V2 — Agent semi-autonome, puis autonome.** Livrables : exécution automatisée des décisions verrouillées (section 11) avec garde-fous et budget de risque ; branches conditionnelles pré-résolues exécutables sur signal T1 ; opponent modeling de mini-ligue ; module Draft complet (VORP, waivers, alertes free agency — c'est en Draft que l'automatisation de la *vitesse* paie le plus). Données : fournisseur événementiel pro (Opta) seulement si le ROI est démontré — hypothèse par défaut : non [H]. Difficultés majeures : l'exécution suppose une session authentifiée sur le compte FPL — pas d'API d'écriture officielle documentée, et l'automatisation d'un compte doit être validée contre les conditions d'utilisation du jeu avant toute mise en œuvre [R, bloquant] ; robustesse aux faux signaux critique dès que l'humain sort de la boucle ; les chips restent humains par choix. Métriques : zéro incident d'exécution ; latence signal→action < 5 min sur branches préparées ; sur-performance deux saisons de suite vs baselines et vs la version N−1.

---

## Recommandation nette

**Le meilleur point de départ technique** : le couple *modèle de minutes + moteur d'EP ancré sur les cotes*, branché sur un MILP mono-GW, avec journal de décisions dès le premier jour. Pas le simulateur complet, pas les chips, pas le Draft. Justification : la prévision de minutes est le socle dont tout dépend ; les cotes fournissent gratuitement une calibration d'équipe de qualité professionnelle ; l'optimiseur transforme immédiatement ces deux briques en décisions ; le journal transforme chaque semaine en donnée d'évaluation.

**Le plus petit produit qui crée déjà un avantage mesurable** : un « conseiller de deadline » hebdomadaire produisant trois choses — le XI + banc ordonné optimal ; le capitaine avec distribution (EP, p10, p90, EO) ; la décision de transfert unique évaluée contre sa conservation (formule ΔEV de la section 7, hit inclus le cas échéant) — chacune avec sa carte d'explication. Mesurable dès 6–8 GW contre la baseline template-EO, il couvre les décisions qui concentrent l'essentiel de l'EV contrôlable hebdomadaire (capitaine + transfert [H]), et chaque brique est un composant définitif des versions suivantes.

## Cinq questions décisives

1. **Mode et terrain de jeu réels** : Classic seul, ou aussi une ligue Draft — et si Draft, quelle plateforme (officielle ou tierce) et quelles règles de ligue (taille, trades, veto, waivers) ? Le module Draft entier en dépend.
2. **Objectif principal, hiérarchisé** : rang global (top 100k, 10k, 1k ?) ou victoire dans une mini-ligue précise (combien de rivaux, quel niveau) ? La fonction objectif — EV pure vs P(titre) — n'est pas la même ; laquelle prime en cas de conflit ?
3. **Automatisation acceptable** : jusqu'où l'agent peut-il *exécuter* (connexion authentifiée à ton compte, risque conditions d'utilisation compris) versus recommander — et quelles décisions gardes-tu contractuellement (chips ? hits ? tout) ?
4. **Budget données** : quel budget mensuel (API de cotes ~20–50 €/mois ; données événementielles pro bien plus) — ou contrainte stricte au gratuit pour V0/V1 ?
5. **Environnement technique** : où l'agent vit-il (VPS, cloud, machine locale), quelles préférences de stack, et qui maintient le code au quotidien entre nous deux ?

---

## Annexe — sources principales consultées (21/08/2026)

Officielles (accès direct bloqué par notre proxy ce jour — contenus obtenus via résumés et relais concordants ; re-vérification directe = première tâche du projet) : [Changements FPL 2026/27](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627) · [Chips 2026/27](https://www.premierleague.com/en/news/4362085) · [DEFCON 2026/27](https://www.premierleague.com/en/news/4361991/whats-happening-with-defensive-contribution-points-in-202627-fantasy) · [Dates de saison](https://www.premierleague.com/en/news/4468487/dates-for-202627-premier-league-season-confirmed) · [FPL Draft — trading](https://www.premierleague.com/en/news/1245445/fpl-draft-how-to-do-player-trading) · [Mécanique des prix](https://www.premierleague.com/en/news/2858775).

Relais et spécialisées : [Fantasy Football Fix — nouveautés 2026/27](https://www.fantasyfootballfix.com/blog-index/fpl-2026-27-new-rules/) · [Fantasy Football Scout — 5 changements](https://www.fantasyfootballscout.co.uk/2026/07/20/fpl-2026-27-5-rule-changes-new-features-announced) · [Flashscore — récap](https://www.flashscore.com/news/soccer-premier-league-fpl-rule-changes-defensive-contributions-double-chips-extra-free-transfers/xdGbtADF) · [Draft FC — règles](https://draftfc.co.uk/fpl-draft-rules) · [Draft FC — scoring](https://draftfc.co.uk/fpl-draft-scoring) · [Draft FC — trades](https://draftfc.co.uk/fpl-draft-trades) · [FFS — prix](https://www.fantasyfootballscout.co.uk/2026/07/20/how-do-fpl-price-changes-work) · [LiveFPL — prix](https://livefpl.com/blog/fpl-price-changes) · [Guide API FPL](https://medium.com/@frenzelts/fantasy-premier-league-api-endpoints-a-detailed-guide-acbd5598eb19) · [Dataset vaastav](https://github.com/vaastav/Fantasy-Premier-League) · [FPL Core Insights](https://github.com/olbauday/FPL-Core-Insights).
