# Backlog V0 — durcissements J0 reportés (revue du 21/08/2026)

J0 est gelé après la correction des snapshots (répertoire immuable par run +
manifeste) et l'ajout des tests de fumée. Les points suivants, validés sur le
principe, sont reportés au chantier V0 — à reprendre après la première
recommandation FPL produite de bout en bout :

1. **Trace manuelle stricte** : rendre `url_consulted` réellement obligatoire
   (aujourd'hui l'authority pré-remplie fait foi) et valider `verified_on`
   comme date ISO — une URL vide ou une date invalide maintient la règle en [R].
2. **Fenêtres de chips exactes** : vérifier, pour chacun des quatre types,
   exactement une fenêtre GW1–19 et une fenêtre GW20–38 (le test actuel accepte
   des sous-fenêtres).
3. **Ligue et picks dynamiques** : paginer entièrement le classement de la
   ligue ; remplacer le test codé en dur sur `/event/1/picks/` par la dernière
   GW à deadline passée, GW testée indiquée dans le rapport.
4. **Tests supplémentaires** : dates invalides, fenêtres de chips incorrectes,
   masquage des IDs, pagination.
