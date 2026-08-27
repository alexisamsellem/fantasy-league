# Calibrations — le seul juge du moteur

Un rapport par journée notée. Chacun compare des projections **figées avant la
deadline** (sous `projections-figees/`) aux minutes réellement jouées.

Ce dossier est versionné exprès. Un score isolé ne dit rien : c'est
l'accumulation, journée après journée, qui distingue un moteur qui a de la
compétence d'un moteur qui a eu de la chance une fois.

Ce qu'on y lit :

- **Brier** : l'erreur quadratique moyenne des probabilités. Plus bas est
  meilleur, 0 est parfait.
- **Brier de référence** : le même score pour un modèle qui prédirait le taux
  de base pour tout le monde.
- **Compétence** : `1 − Brier / Brier_référence`. Positif = le moteur bat le
  taux de base. Négatif = il fait pire que de ne rien savoir.
- **Tableau de fiabilité** : là où le moteur se trompe encore. Un moteur peut
  avoir une bonne compétence globale et rester systématiquement trop confiant
  sur une tranche.

Aucune donnée personnelle : ces rapports ne parlent que de probabilités et de
minutes publiques.

Produit par `python3 scripts/calibrer_en_attente.py`, lancé automatiquement par
le workflow `Conseiller FPL`.

## Journées notées

Aucune pour l'instant. La GW1 est définitivement perdue : rien n'a été figé
avant sa deadline. La GW2 est la première journée notable.
