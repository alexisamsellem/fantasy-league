# -*- coding: utf-8 -*-
"""Point d'entrée du mode hebdomadaire : snapshot → recommandation complète.

Ce fichier ne contient plus aucune règle métier. Il fait trois choses :

  1. il lit l'effectif détenu et la banque dans le snapshot (données
     personnelles, qui n'entrent jamais dans le contrat de projections) ;
  2. il délègue prévision, décision et verdict à `weekly.py` ;
  3. il rattache la lecture de la mini-ligue, elle aussi personnelle.

La séparation compte : tout ce qui est au-dessus de la ligne 2 est jugeable et
rejouable à partir du seul contrat ; tout ce qui est en dessous est du contexte
qui ne doit influencer aucune projection.
"""

from . import weekly
from .rivals import exposure_conflicts, league_views


def build_recommendation(parsed, now=None, freeze_to=None):
    """`freeze_to` écrit le contrat de projections sur disque : c'est la trace
    auditable de ce que le moteur croyait au moment de la décision. Elle ne
    contient aucune donnée personnelle — ni effectif, ni ligue, ni team ID."""
    # L'effectif d'abord : sans lui il n'y a pas de décision hebdomadaire, et le
    # diagnostic doit arriver avant le coût d'un calcul complet de projections.
    squad_ids, bank = weekly.read_squad(parsed)

    contract = weekly.build_contract(parsed)
    frozen = contract.save(freeze_to) if freeze_to else None
    rec = weekly.build_from_contract(
        contract, squad_ids, bank, now=now,
        already_transferred=weekly.pending_transfers(parsed, contract.gw),
        pick_gw=parsed.get("last_closed_gw"))
    rec["frozen_projections"] = str(frozen) if frozen else None

    # Plusieurs mini-ligues peuvent compter à la fois : elles sont lues
    # séparément, jamais moyennées. La première reste la vue par défaut pour
    # tout ce qui n'en attend qu'une.
    vues = league_views(parsed)
    rec.update({"leagues": vues,
                "exposure_conflicts": exposure_conflicts(vues),
                "exposure": vues[0]["exposure"] if vues else [],
                "exposure_meta": vues[0]["meta"] if vues else {},
                "standings": vues[0]["standings"] if vues else {}})
    return rec
