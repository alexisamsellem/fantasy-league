# -*- coding: utf-8 -*-
"""Tests du rythme des envois et du bilan — hors ligne, aucun envoi.

Ce qui doit tenir absolument :

  1. au plus DEUX mails avant une deadline, et le second seulement si la
     décision a changé ;
  2. un mail déjà parti ne repart jamais, un passage manqué est rattrapé ;
  3. un seul bilan par journée, et jamais celui d'une journée ancienne.
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import bilan, envois, mail                       # noqa: E402
from fpl_advisor.advise import build_recommendation               # noqa: E402
from fpl_advisor.demo import build_parsed                         # noqa: E402

UTC = timezone.utc


def _paris(dt):
    return dt.astimezone(envois.PARIS).strftime("%a %H:%M")


def _events(deadline, gw=7, precedente=None):
    """Calendrier minimal : la GW précédente jouée et validée, puis `gw`."""
    precedente = precedente or deadline - timedelta(days=7)
    return [
        {"id": gw - 2, "deadline_time": "2026-09-01T10:00:00Z",
         "finished": True, "data_checked": True},
        {"id": gw - 1, "deadline_time": precedente.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "finished": True, "data_checked": True},
        {"id": gw, "deadline_time": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "finished": False, "data_checked": False},
    ]


VENDREDI = datetime(2026, 10, 23, 17, 30, tzinfo=UTC)   # 19 h 30 à Paris


class Horaires(unittest.TestCase):

    def test_deadline_du_vendredi_soir_donne_12h_et_17h(self):
        p, r = envois.horaires(VENDREDI)
        self.assertEqual(_paris(p), "Fri 12:00")
        self.assertEqual(_paris(r), "Fri 17:00")

    def test_en_hiver_aussi(self):
        # 18 h 30 à Londres = 18:30 UTC en hiver = 19 h 30 à Paris.
        p, r = envois.horaires(datetime(2026, 12, 4, 18, 30, tzinfo=UTC))
        self.assertEqual(_paris(p), "Fri 12:00")
        self.assertEqual(_paris(r), "Fri 17:00")

    def test_deadline_du_samedi_midi_ne_reveille_personne(self):
        # Cas réel de la GW7 : samedi 17/10, 12 h à Paris.
        p, r = envois.horaires(datetime(2026, 10, 17, 10, 0, tzinfo=UTC))
        self.assertEqual(_paris(p), "Fri 20:00")
        self.assertEqual(_paris(r), "Sat 09:30")


class Planifier(unittest.TestCase):

    def _plan(self, maintenant, journal=None, **kw):
        return envois.planifier(_events(VENDREDI), journal or {"gw": {"6": {"bilan": {}}}},
                                maintenant, **kw)

    def test_trop_tot_rien(self):
        self.assertEqual(self._plan(VENDREDI - timedelta(hours=30))["conseil"], "rien")

    def test_a_l_heure_du_principal(self):
        self.assertEqual(self._plan(VENDREDI - timedelta(hours=7))["conseil"],
                         "principal")

    def test_le_principal_ne_part_qu_une_fois(self):
        j = {"gw": {"6": {"bilan": {}}, "7": {"principal": {"decision": {}}}}}
        self.assertEqual(self._plan(VENDREDI - timedelta(hours=5), j)["conseil"], "rien")

    def test_a_l_heure_du_rappel(self):
        j = {"gw": {"6": {"bilan": {}}, "7": {"principal": {"decision": {}}}}}
        self.assertEqual(self._plan(VENDREDI - timedelta(hours=2), j)["conseil"], "rappel")

    def test_le_rappel_ne_part_qu_une_fois(self):
        j = {"gw": {"6": {"bilan": {}}, "7": {"principal": {}, "rappel": {}}}}
        self.assertEqual(self._plan(VENDREDI - timedelta(hours=1), j)["conseil"], "rien")

    def test_principal_manque_rattrape_au_rappel(self):
        plan = self._plan(VENDREDI - timedelta(hours=2))
        self.assertEqual(plan["conseil"], "rappel")
        self.assertIn("jamais parti", plan["raison"])

    def test_trop_pres_de_la_deadline_rien(self):
        self.assertEqual(self._plan(VENDREDI - timedelta(minutes=10))["conseil"], "rien")

    def test_forcer_envoie_tout_de_suite(self):
        plan = self._plan(VENDREDI - timedelta(hours=40), forcer=True)
        self.assertEqual((plan["conseil"], plan["force"]), ("principal", True))

    def test_retard_de_sept_heures_du_cron_absorbe(self):
        # Passages horaires, chacun 7 h en retard : il en tombe quand même un
        # dans chaque fenêtre, et chaque mail ne part qu'une fois.
        journal = {"gw": {"6": {"bilan": {}}}}
        envoyes = []
        t = VENDREDI - timedelta(hours=13, minutes=13)   # passages à :17
        while t < VENDREDI:
            plan = envois.planifier(_events(VENDREDI), journal, t)
            if plan["conseil"] != "rien":
                envoyes.append((plan["conseil"], _paris(t)))
                envois.noter(journal, 7, plan["conseil"], True,
                             {"capitaine": "X"} if plan["conseil"] == "principal" else None,
                             maintenant=t)
            t += timedelta(hours=1)
        self.assertEqual([m for m, _ in envoyes], ["principal", "rappel"])
        self.assertEqual(envoyes[0][1], "Fri 12:17")


class Bilan(unittest.TestCase):

    def test_la_journee_qui_vient_de_se_jouer(self):
        plan = envois.planifier(_events(VENDREDI), {"gw": {}},
                                VENDREDI - timedelta(days=3))
        self.assertEqual(plan["bilan_gw"], 6)

    def test_une_seule_fois(self):
        plan = envois.planifier(_events(VENDREDI), {"gw": {"6": {"bilan": {"envoye_le": "x"}}}},
                                VENDREDI - timedelta(days=3))
        self.assertIsNone(plan["bilan_gw"])

    def test_jamais_une_journee_ancienne_au_premier_deploiement(self):
        # Cas réel du 13/10 : GW6 jouée mais pas validée, GW5 validée depuis
        # un mois. Le journal est vide : pas de bilan de la GW5.
        ev = _events(VENDREDI)
        ev[1].update(finished=False, data_checked=False)
        plan = envois.planifier(ev, {"gw": {}}, VENDREDI - timedelta(days=3))
        self.assertIsNone(plan["bilan_gw"])

    def test_semaine_a_deux_journees_bilan_rattrape(self):
        # GW6 validée après la deadline de la GW7 : on l'a conseillée, on
        # l'analyse quand même.
        ev = _events(VENDREDI)
        ev[2]["deadline_time"] = "2026-10-20T17:30:00Z"
        ev.append({"id": 8, "deadline_time": "2026-10-30T17:30:00Z"})
        j = {"gw": {"6": {"principal": {"decision": {}}}}}
        plan = envois.planifier(ev, j, datetime(2026, 10, 21, tzinfo=UTC))
        self.assertEqual(plan["bilan_gw"], 6)

    def test_points_non_valides_pas_de_bilan(self):
        ev = _events(VENDREDI)
        ev[1]["data_checked"] = False
        plan = envois.planifier(ev, {"gw": {}}, VENDREDI - timedelta(days=3))
        self.assertIsNone(plan["bilan_gw"])


class Arbitrer(unittest.TestCase):
    A = {"transfert": "aucun", "capitaine": "Salah", "vice": "Haaland",
         "onze": ["Haaland", "Palmer", "Salah"]}

    def _journal(self):
        return {"gw": {"7": {"principal": {"decision": dict(self.A)}}}}

    def test_principal_part_toujours(self):
        self.assertEqual(envois.arbitrer({"gw": {}}, 7, "principal", self.A), (True, []))

    def test_rappel_inchange_ne_part_pas(self):
        self.assertEqual(envois.arbitrer(self._journal(), 7, "rappel", dict(self.A)),
                         (False, []))

    def test_rappel_change_part_avec_le_detail(self):
        b = dict(self.A, capitaine="Haaland", vice="Salah",
                 onze=["Haaland", "Saka", "Salah"])
        envoyer, diff = envois.arbitrer(self._journal(), 7, "rappel", b)
        self.assertTrue(envoyer)
        texte = " ".join(diff)
        self.assertIn("Salah → **Haaland**", texte)
        self.assertIn("**Saka** entre", texte)
        self.assertIn("Palmer sort", texte)

    def test_rappel_sans_principal_part(self):
        self.assertEqual(envois.arbitrer({"gw": {}}, 7, "rappel", self.A), (True, []))

    def test_le_rappel_parti_seul_devient_la_reference(self):
        j = envois.noter({"gw": {}}, 7, "rappel", True, dict(self.A))
        self.assertEqual(j["gw"]["7"]["principal"]["decision"], self.A)
        self.assertTrue(j["gw"]["7"]["rappel"]["envoye"])


class Journal(unittest.TestCase):

    def test_aller_retour_et_elagage(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "envois" / "journal.json"
            j = envois.charger(chemin)
            for gw in range(1, 10):
                envois.noter(j, gw, "bilan", True)
            envois.sauver(j, chemin)
            relu = envois.charger(chemin)
            self.assertEqual(sorted(relu["gw"], key=int),
                             [str(g) for g in range(4, 10)])

    def test_journal_illisible_ne_bloque_rien(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "journal.json"
            chemin.write_text("{pas du json", encoding="utf-8")
            self.assertEqual(envois.charger(chemin), {"version": 1, "gw": {}})


class MailDeRappel(unittest.TestCase):

    def setUp(self):
        self.rec = dict(build_recommendation(build_parsed()))

    def test_la_decision_reprend_le_mail(self):
        dec = envois.decision(self.rec)
        lignes = dict((t, q) for t, q, _ in mail.decisions(self.rec))
        self.assertEqual(dec["capitaine"], lignes["Capitaine"])
        self.assertEqual(len(dec["onze"]), 11)

    def test_sans_changement_le_mail_est_celui_d_avant(self):
        self.assertNotIn("CHANGEMENT", mail.sujet(self.rec))
        self.assertNotIn("Ça a changé", mail.render_html(self.rec))

    def test_le_changement_ouvre_le_mail_dans_les_deux_formes(self):
        self.rec["changements"] = ["Capitaine : A → **B**."]
        self.assertTrue(mail.sujet(self.rec).startswith("CHANGEMENT · "))
        html, texte = mail.render_html(self.rec), mail.render_texte(self.rec)
        self.assertLess(html.index("Ça a changé"), html.index("Ce que tu fais"))
        self.assertIn("<strong>B</strong>", html)
        self.assertIn("Capitaine : A → B.", texte)


def _donnees_bilan(**surcharges):
    """Une journée jouée, construite à la main : 11 titulaires, 4 remplaçants."""
    elements = [{"id": i, "web_name": f"J{i}", "element_type": t}
                for i, t in zip(range(1, 16),
                                [1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 1, 2, 3, 4])]
    elements += [{"id": 99, "web_name": "Sortant", "element_type": 4}]
    pts = {i: 2 for i in range(1, 16)}
    pts.update({9: 8, 10: 13, 14: 7, 99: 1})
    minutes = {i: 90 for i in range(1, 16)}
    minutes[99] = 90
    picks = [{"element": i, "position": i, "multiplier": 1 if i <= 11 else 0,
              "is_captain": i == 9, "is_vice_captain": i == 10}
             for i in range(1, 16)]
    picks[8]["multiplier"] = 2
    d = {
        "gw": 6, "team_id": 42,
        "bootstrap": {"elements": elements,
                      "events": [{"id": 6, "average_entry_score": 50,
                                  "highest_score": 120}]},
        "live": {"elements": [{"id": i, "stats": {"total_points": pts.get(i, 0),
                                                  "minutes": minutes.get(i, 0)}}
                              for i in list(range(1, 16)) + [99]]},
        "history": {"current": [
            {"event": 5, "overall_rank": 200000},
            {"event": 6, "points": 46, "event_transfers_cost": 4, "rank": 3000000,
             "overall_rank": 150000, "points_on_bench": 13}]},
        "transfers": [{"event": 6, "element_in": 10, "element_out": 99},
                      {"event": 5, "element_in": 3, "element_out": 98}],
        "picks": {"picks": picks, "active_chip": None, "automatic_subs": []},
        "leagues": [{"name": "Les potes", "rows": [
            {"entry": 7, "entry_name": "Rival", "rank": 1, "last_rank": 2,
             "event_total": 70},
            {"entry": 42, "entry_name": "Moi", "rank": 2, "last_rank": 1,
             "event_total": 46}]}],
    }
    d.update(surcharges)
    return d


class BilanContenu(unittest.TestCase):

    def test_score_brassard_transfert_classement(self):
        b = bilan.build(_donnees_bilan())
        self.assertEqual((b["points"], b["net"]), (46, 42))
        c = b["capitaine"]
        self.assertEqual((c["porteur"], c["pts"], c["ideal"], c["perte"]),
                         ("J9", 8, "J10", 5))
        self.assertEqual(b["transferts"], [{"sortant": "Sortant", "entrant": "J10",
                                            "pts_sortant": 1, "pts_entrant": 13}])
        texte = bilan.render_texte(b)
        self.assertIn("42 pts (46 − 4 de pénalité de transfert)", texte)
        self.assertIn("−8 par rapport à la moyenne générale", texte)
        self.assertIn("5 pts laissés sur la table", texte)
        self.assertIn("Transfert Sortant → J10 : +12 pts", texte)
        self.assertIn("50\u202f000 places gagnées", texte)
        self.assertIn("Les potes : 2ᵉ / 2 (↓1)", texte)
        self.assertIn("meilleur : Rival (70)", texte)
        self.assertIn("Bilan GW6 · 42 pts (moy. 50)", bilan.sujet(b))

    def test_capitaine_absent_le_vice_prend_le_brassard(self):
        d = _donnees_bilan()
        for e in d["live"]["elements"]:
            if e["id"] == 9:
                e["stats"]["minutes"] = 0
        b = bilan.build(d)
        self.assertEqual(b["capitaine"]["porteur"], "J10")
        self.assertFalse(b["capitaine"]["a_joue"])
        self.assertIn("vice, J9 n'a pas joué", bilan.render_texte(b))

    def test_remplacement_automatique_compte_dans_le_onze(self):
        d = _donnees_bilan()
        d["picks"]["automatic_subs"] = [{"element_out": 5, "element_in": 14}]
        b = bilan.build(d)
        noms = {j["nom"] for j in b["joueurs"]}
        self.assertIn("J14", noms)
        self.assertNotIn("J5", noms)
        self.assertIn("Remplacement auto : J14 pour J5", bilan.render_texte(b))

    def test_wildcard_resume_en_une_ligne(self):
        d = _donnees_bilan()
        d["picks"]["active_chip"] = "wildcard"
        d["transfers"] = [{"event": 6, "element_in": i, "element_out": 99}
                          for i in range(1, 6)]
        texte = bilan.render_texte(bilan.build(d))
        self.assertIn("Wildcard : 5 transferts", texte)
        self.assertNotIn("Transfert J1", texte)

    def test_html_et_texte_portent_le_meme_score(self):
        b = bilan.build(_donnees_bilan())
        self.assertIn("42 pts", bilan.render_html(b))
        self.assertIn("42 pts", bilan.render_texte(b))

    def test_sans_picks_blocage_explicite(self):
        with self.assertRaises(SystemExit):
            bilan.build(_donnees_bilan(picks=None))


if __name__ == "__main__":
    unittest.main()
