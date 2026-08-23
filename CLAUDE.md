# Instructions de travail pour Claude

## Langue et verdict

- Travailler et répondre en français.
- Ouvrir les comptes rendus par le verdict réel, sans préambule flatteur.
- Employer un verdict net lorsque le travail porte sur la qualification du moteur :
  - `candidat initial publiable avec avertissements` ; ou
  - `toujours bloqué`.
- Ne jamais présenter des tests verts comme une preuve de qualité prédictive.
- Ne jamais qualifier le moteur de « conseiller crédible » sans preuve sur données réelles et calibration mesurée.

## Manière d'expliquer le projet

Quand tu expliques le système, son architecture, un changement ou un résultat, commence par une chaîne chronologique et causale unique.

Présente d'abord la colonne vertébrale complète :

`objectif → données → temps de jeu → production attendue → projections → contrôle qualité → optimisation → équipe candidate → validation humaine`

Pour chaque étape, explique dans cet ordre :

1. **Entrée** — ce que l'étape reçoit.
2. **Transformation** — ce qu'elle calcule ou vérifie concrètement.
3. **Sortie** — ce qu'elle produit.
4. **Lien causal** — pourquoi cette sortie est nécessaire à l'étape suivante.

Relie toujours le résultat final à l'objectif de départ : proposer une équipe FPL Classic de 15 joueurs susceptible de gagner la mini-ligue, sans agir sur le compte et sans retirer la décision finale à l'utilisateur.

Ne présente pas l'architecture comme un catalogue de fichiers, modules, métriques ou décisions indépendantes. Les noms de fichiers et les détails d'implémentation viennent après l'explication du rôle causal de la composante.

## Niveau de technicité

Vulgariser ne signifie pas retirer la technique. Quand un concept technique devient nécessaire — prior, shrinkage, calibration, Brier score, contrat sérialisable, inversion de dépendance, optimum local ou fuite temporelle — explique :

1. sa définition simple mais exacte ;
2. le problème concret qu'il résout ici ;
3. son fonctionnement dans ce projet ;
4. ce qu'il reçoit et produit ;
5. ce qui se passerait s'il était absent ou incorrect.

Utilise une analogie seulement si elle éclaire réellement le mécanisme. Ne remplace jamais l'explication technique par l'analogie.

Si davantage de détails sont demandés, conserve la même chaîne principale et approfondis les étapes concernées. N'abandonne pas la structure causale au profit d'un inventaire exhaustif.

## Structure des réponses importantes

Pour une explication, une revue ou un compte rendu substantiel :

1. donner le verdict ou le résultat en une phrase ;
2. rappeler l'objectif recherché ;
3. dérouler la chaîne causale dans l'ordre ;
4. approfondir seulement les détails techniques nécessaires ;
5. terminer par :
   - ce qui fonctionne ;
   - ce qui reste à prouver ;
   - ce qui bloque ;
   - la prochaine action concrète.

Évite les tableaux de bord, les longues séries de cartes, les glossaires séparés du raisonnement, les listes sans relations explicites et les répétitions. Si plusieurs branches ou exceptions existent, explique d'abord le chemin principal, puis rattache chaque exception à l'étape qu'elle affecte.

## Garde-fous méthodologiques du projet

- L'agent reste un conseiller en lecture seule. Toute décision est validée par un humain.
- Utiliser uniquement des données publiques gratuites.
- Ne mettre aucune donnée personnelle dans Git. `data/` et `config.local.json` restent ignorés.
- Ne pas remplacer la validation réelle par une démonstration synthétique.
- Ne pas interpréter le recouvrement avec `ep_next` de la démo : cette valeur y est aléatoire.
- Un résultat de stabilité de `11/15` échoue au seuil `STABILITY_MIN_OVERLAP = 12`.
- Ne pas ajuster les constantes pour imiter l'ownership, le template communautaire ou `ep_next`.
- Corriger uniquement un défaut démontré par les données, accompagné d'un test de régression.
- Une collecte destinée à un test prospectif doit être effectuée avant la deadline de la GW1.
- En cas de porte qualité bloquée, appeler l'équipe calculée « candidat technique », jamais « recommandation ».

## Architecture à préserver

Le dépôt reste organisé en trois couches :

1. `forecasting` transforme les données en projections ;
2. `evaluation` vérifie la qualité et la stabilité de ces projections et sélections ;
3. `optimization` compose l'effectif à partir du contrat de projections.

Le contrat sérialisable de `forecasting/contract.py` est la frontière entre prévision et optimisation. L'optimiseur ne doit lire ni l'API ni le snapshot brut.

`evaluation` déclare le besoin abstrait `SelectionBackend` ; `wiring.py` fournit l'implémentation. Ne pas introduire une dépendance directe de `evaluation` vers `optimization`.

Conserver les façades de compatibilité existantes tant qu'une migration explicite ne permet pas de les retirer sans casser les imports.

## Périmètre

Ne pas ajouter sans demande explicite : Draft, automatisation du compte, interface utilisateur, chips, simulation de mini-ligue, données payantes, nouvel optimiseur, second dépôt ou agent LLM dans le produit.

Ne pas mélanger une correction fonctionnelle avec un commit de refactoring. Documenter séparément les anomalies observées lorsque leur correction n'appartient pas au périmètre courant.

## Examen indépendant des affirmations

Ne traite pas l'opinion, la préférence ou la confiance de l'utilisateur comme une preuve. Reformule mentalement toute conclusion comme une question neutre et vérifie-la contre les données, le code et les tests disponibles.

Si le cadrage contient une prémisse incorrecte, corrige-la avant de raisonner à l'intérieur de ce cadrage. En cas de désaccord possible, examine l'argument contraire le plus solide avant de conclure. Recherche l'exactitude, pas l'approbation ni la contradiction systématique.
