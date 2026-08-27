# -*- coding: utf-8 -*-
"""Audit d'effectif comparatif : où le modèle diverge de l'équipe détenue.

Question posée, une seule : si le moteur repartait de zéro AUJOURD'HUI avec la
valeur d'équipe du manager, quels 15 joueurs achèterait-il, et combien de
points cet effectif idéal rapporterait-il de plus sur l'horizon ?

Trois précautions, parce que la réponse est facile à sur-interpréter :

1. **Rebâtir de zéro ignore le coût des transferts.** L'écart chiffré est un
   plafond théorique atteignable en 15 transferts simultanés — c'est-à-dire par
   un wildcard, pas par la semaine ordinaire. L'audit dit OÙ le modèle diverge,
   pas quoi faire en un coup.
2. **Le prix de vente est approximé par `now_cost`.** L'API publique ne donne
   pas le prix d'achat. Un joueur pris avant une hausse se vend moins cher que
   son prix affiché ; la valeur d'équipe reconstituée ici peut donc être
   légèrement optimiste. Même approximation que `transfers.py`, assumée.
3. **Le chemin de transferts rejoue les MÊMES projections à chaque semaine.**
   Les prix ne bougent pas, les blessures n'arrivent pas, les projections de la
   GW+3 ne se précisent pas. La première étape est une vraie recommandation ;
   les suivantes sont une direction, pas un plan.

Ce module ne lit ni snapshot, ni bootstrap, ni fonction de prévision : il
reçoit des lignes de contrat (`ProjectionSet.rows_for`) et applique les règles
FPL, comme les autres modules d'optimisation.
"""

from .initial import (BUDGET, INITIAL_HORIZON_GWS, MAX_PER_CLUB, SQUAD_QUOTA,
                      build_pool, optimize_squad, squad_value)
from .transfers import TRANSFER_THRESHOLD

AUDIT_HORIZON_GWS = INITIAL_HORIZON_GWS   # 4 GW : même horizon que l'effectif
                                          # initial — on compare deux équipes
                                          # statiques, pas une semaine [H]
PATH_WEEKS = 4          # semaines du chemin proposé, une par transfert gratuit
                        # (pas de hit : hors périmètre V0)


def read_owned(rows, squad_ids):
    """(lignes des joueurs détenus dans l'ordre des picks, identifiants absents).

    Les absents ne sont pas absorbés en silence : un joueur qui n'est plus dans
    le contrat n'est pas projetable, et tout chiffre calculé sans lui est faux
    d'un joueur."""
    by_id = {r["id"]: r for r in rows}
    owned = [by_id[pid] for pid in squad_ids if pid in by_id]
    missing = [pid for pid in squad_ids if pid not in by_id]
    return owned, missing


def team_value(owned, bank):
    """Valeur d'équipe reconstituée = somme des prix affichés + banque.

    On ne lit PAS `entry_history.value` : ce champ agrège des prix d'achat que
    l'API publique ne détaille pas, et le mélanger aux `now_cost` de la
    reconstruction donnerait deux équipes chiffrées sur deux échelles. Ici les
    deux côtés de la comparaison sont évalués au même prix affiché."""
    return sum(r["now_cost"] for r in owned) + int(bank or 0)


def rebuild(rows, gws, budget, owned=None):
    """Les 15 joueurs que le moteur achèterait à cette valeur d'équipe.

    Même vivier et même montée locale que le mode effectif initial ; deux
    différences, toutes deux imposées par la question posée ici.

    1. Le budget n'est plus les 100,0 M£ du départ mais la valeur d'équipe du
       manager.
    2. La montée part de DEUX points — l'effectif le moins cher, comme
       d'habitude, et l'effectif détenu — et garde le meilleur des deux.

    Le point 2 n'est pas un embellissement. Une montée locale partant du moins
    cher peut se bloquer SOUS l'équipe détenue : le rapport annoncerait alors
    un retard négatif, c'est-à-dire « votre équipe bat le modèle », alors que
    la seule chose démontrée serait la faiblesse de la montée. Repartir aussi
    de l'effectif détenu garantit que l'effectif reconstruit le vaut au moins,
    donc que l'écart mesuré est un MINORANT du gain disponible — jamais un
    satisfecit accidentel. Le vivier est élargi aux joueurs détenus pour la
    même raison : sans eux, un échange ne peut jamais les faire revenir.
    """
    pool = build_pool(rows)
    if owned:
        connus = {r["id"] for r in pool}
        pool = pool + [r for r in owned if r["id"] not in connus]
    squad, value = optimize_squad(pool, gws, budget)
    if owned and len(owned) == sum(SQUAD_QUOTA.values()):
        depuis_detenu = optimize_squad(pool, gws, budget, start=list(owned))
        if depuis_detenu[1] > value:
            squad, value = depuis_detenu
    return squad, value, pool


def divergence(owned, rebuilt):
    """Où les deux effectifs ne se recouvrent pas, par poste et joueur."""
    owned_ids = {r["id"] for r in owned}
    rebuilt_ids = {r["id"] for r in rebuilt}
    communs = [r for r in owned if r["id"] in rebuilt_ids]
    absents = sorted((r for r in owned if r["id"] not in rebuilt_ids),
                     key=lambda r: -r["ep4"])
    entrants = sorted((r for r in rebuilt if r["id"] not in owned_ids),
                      key=lambda r: -r["ep4"])
    par_poste = {}
    for et in SQUAD_QUOTA:
        par_poste[et] = {
            "communs": sum(1 for r in communs if r["element_type"] == et),
            "detenus_ecartes": [r for r in absents if r["element_type"] == et],
            "retenus_non_detenus": [r for r in entrants if r["element_type"] == et],
        }
    return {"recouvrement": len(communs), "communs": communs,
            "detenus_ecartes": absents, "retenus_non_detenus": entrants,
            "par_poste": par_poste}


def _clubs(squad):
    c = {}
    for r in squad:
        c[r["team"]] = c.get(r["team"], 0) + 1
    return c


def best_swap(squad, pool, gws, bank, base=None):
    """Meilleur échange un-pour-un réalisable, ou None.

    Contraintes appliquées telles quelles : même poste (donc quotas conservés),
    prix d'entrée ≤ prix de sortie + banque, 3 joueurs maximum par club. Le
    gain est mesuré sur la VALEUR DE L'EFFECTIF (meilleur XI de chaque GW +
    bonus exact du brassard), jamais sur les points individuels — c'est la même
    correction que celle apportée à l'arbitrage hebdomadaire (anomalie A2)."""
    squad_ids = {r["id"] for r in squad}
    clubs = _clubs(squad)
    base = squad_value(squad, gws) if base is None else base
    best = None
    for i, out in enumerate(squad):
        for inn in pool:
            if inn["id"] in squad_ids or inn["element_type"] != out["element_type"]:
                continue
            if inn["now_cost"] > out["now_cost"] + bank:
                continue
            if inn["team"] != out["team"] \
                    and clubs.get(inn["team"], 0) + 1 > MAX_PER_CLUB:
                continue
            candidate = squad[:i] + [inn] + squad[i + 1:]
            value = squad_value(candidate, gws)
            if value > base + 1e-9 and (best is None or value > best["value"]):
                best = {"out": out, "in": inn, "value": value,
                        "gain": value - base, "squad": candidate,
                        "bank_after": bank + out["now_cost"] - inn["now_cost"]}
    return best


def transfer_path(owned, rows, bank, gws, weeks=PATH_WEEKS, pool=None):
    """Chemin glouton d'un transfert gratuit par semaine, depuis l'effectif
    détenu.

    Chaque étape prend l'échange qui ajoute le plus à la valeur de l'effectif,
    puis repart de l'équipe obtenue. C'est une montée locale, pas un optimum :
    la meilleure séquence de 4 transferts n'est pas forcément la suite des 4
    meilleurs transferts pris un par un. L'ordre proposé reste celui qui
    encaisse le gain le plus tôt, ce qui est le bon réflexe quand l'horizon est
    court et les projections incertaines.

    S'arrête dès qu'aucun échange n'améliore la valeur : une liste plus courte
    que `weeks` est un résultat, pas une erreur.
    """
    pool = build_pool(rows) if pool is None else pool
    squad = list(owned)
    value = squad_value(squad, gws)
    depart = value
    etapes = []
    for semaine in range(1, weeks + 1):
        step = best_swap(squad, pool, gws, bank, base=value)
        if step is None:
            break
        etapes.append({
            "semaine": semaine, "out": step["out"], "in": step["in"],
            "gain": step["gain"], "valeur_apres": step["value"],
            "cumul": step["value"] - depart, "banque_apres": step["bank_after"],
            "au_dessus_du_seuil": step["gain"] > TRANSFER_THRESHOLD,
        })
        squad, value, bank = step["squad"], step["value"], step["bank_after"]
    return {"etapes": etapes, "valeur_depart": depart, "valeur_arrivee": value,
            "gain_total": value - depart, "seuil_hebdomadaire": TRANSFER_THRESHOLD,
            "semaines_demandees": weeks, "effectif_arrivee": squad}


def audit(rows, squad_ids, bank, gws, weeks=PATH_WEEKS):
    """Audit complet, à partir des seules lignes du contrat et de l'effectif.

    Retourne les faits ; ni verdict de publication, ni mise en forme."""
    owned, missing = read_owned(rows, squad_ids)
    budget = team_value(owned, bank)
    rebuilt, valeur_ideale, pool = rebuild(rows, gws, budget, owned)
    valeur_detenue = squad_value(owned, gws) if len(owned) >= 15 else None
    chemin = transfer_path(owned, rows, bank, gws, weeks, pool) \
        if valeur_detenue is not None else None
    retard = (valeur_ideale - valeur_detenue) if valeur_detenue is not None else None
    return {
        "horizon": list(gws),
        "owned": owned, "missing_ids": missing,
        "bank": int(bank or 0), "budget": budget, "budget_initial": BUDGET,
        "rebuilt": rebuilt, "pool_size": len(pool),
        "valeur_detenue": valeur_detenue, "valeur_ideale": valeur_ideale,
        "retard": retard,
        "cout_detenu": sum(r["now_cost"] for r in owned),
        "cout_ideal": sum(r["now_cost"] for r in rebuilt),
        "divergence": divergence(owned, rebuilt),
        "chemin": chemin,
        "part_rattrapee": (chemin["gain_total"] / retard
                           if chemin and retard and retard > 1e-9 else None),
    }
