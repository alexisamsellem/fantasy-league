# -*- coding: utf-8 -*-
"""Tests du mail de la semaine — hors ligne, aucun envoi.

Le mail est ce qu'Alexis lit vraiment. Le rapport Markdown est la preuve ; le
mail est la décision. Deux choses doivent donc tenir absolument :

  1. HTML et texte portent la MÊME décision. Un client qui n'affiche que le
     texte ne doit pas recevoir une autre équipe ;
  2. le mail décrit l'effectif d'APRÈS le transfert recommandé, jamais celui
     d'avant — c'est l'anomalie A6, et elle se rejouerait ici sans test.
"""

import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fpl_advisor import mail, weekly                              # noqa: E402
from fpl_advisor.advise import build_recommendation               # noqa: E402
from fpl_advisor.demo import build_parsed                         # noqa: E402
from fpl_advisor.optimization import weekly as opt_weekly         # noqa: E402


def _rec():
    if not hasattr(_rec, "cache"):
        _rec.cache = build_recommendation(build_parsed())
    return _rec.cache


def _rec_avec_transfert():
    """Un `rec` où le transfert est recommandé — la démo dit « conserver »."""
    if hasattr(_rec_avec_transfert, "cache"):
        return _rec_avec_transfert.cache
    parsed = build_parsed()
    rec = dict(build_recommendation(parsed))
    contract = weekly.build_contract(parsed)
    ids, bank = weekly.read_squad(parsed)
    rows = contract.rows_for("central")
    # On rend un joueur du marché irrésistible : l'échange devient évident, et
    # l'entrant DOIT prendre une place dans le onze. Il faut le choisir
    # ACHETABLE — même poste qu'un joueur détenu, et dans le budget — sinon
    # `transfer_scan` l'écarte et la fixture n'exerce rien.
    detenus = {r["id"]: r for r in rows if r["id"] in set(ids)}
    plafond = {}
    for r in detenus.values():
        et = r["element_type"]
        plafond[et] = max(plafond.get(et, 0), r["now_cost"] + bank)
    # ...et d'un club non saturé : la démo aligne déjà trois joueurs de
    # certains clubs, et la limite FPL de 3 par club écarterait l'entrant.
    clubs = {}
    for r in detenus.values():
        clubs[r["team"]] = clubs.get(r["team"], 0) + 1
    achetables = [r for r in rows if r["id"] not in detenus
                  and r["now_cost"] <= plafond.get(r["element_type"], 0)
                  and clubs.get(r["team"], 0) < 3]
    assert achetables, "aucun joueur achetable dans la démo"
    cible = max(achetables, key=lambda r: r["eps"][contract.gw])
    gonfle = [dict(r, eps={g: v * 4 for g, v in r["eps"].items()})
              if r["id"] == cible["id"] else r for r in rows]
    d = opt_weekly.weekly_decision(gonfle, ids, bank, list(contract.horizon))
    assert d["decision"] == "transférer", "fixture inopérante"
    ap = d["apres_transfert"]
    par_id = {r["id"]: r for r in d["squad"] + [ap["in"]]}
    display = {r["id"]: r for r in contract.display_rows(
        list(par_id), contract.gw)}
    rec.update({
        "xi": [display[p["id"]] for p in d["xi"]],
        "bench": [display[p["id"]] for p in d["bench"]],
        "transfer": dict(d["transfer"], candidates=[
            dict(c, out=display[c["out"]["id"]], in_=display[c["in"]["id"]],
                 **{"in": display[c["in"]["id"]]})
            for c in d["transfer"]["candidates"]]),
        "apres_transfert": dict(
            ap, xi=[display[p["id"]] for p in ap["xi"]],
            bench=[display[p["id"]] for p in ap["bench"]],
            out=display[ap["out"]["id"]], **{"in": display[ap["in"]["id"]]},
            armband=dict(ap["armband"],
                         captain=display[ap["armband"]["captain"]["id"]],
                         vice=display[ap["armband"]["vice"]["id"]]),
            xi_in=[display[i] for i in ap["xi_in"]],
            xi_out=[display[i] for i in ap["xi_out"]]),
    })
    _rec_avec_transfert.cache = rec
    return rec


class SujetTests(unittest.TestCase):
    def test_le_sujet_porte_la_decision_pas_le_numero_de_journee(self):
        """Un sujet « FPL GW2 » n'apprend rien dans une liste de mails."""
        s = mail.sujet(_rec_avec_transfert())
        c = _rec_avec_transfert()["transfer"]["candidates"][0]
        self.assertIn(c["out"]["web_name"], s)
        self.assertIn(c["in"]["web_name"], s)
        self.assertIn(_rec_avec_transfert()["armband"]["captain"]["web_name"], s)

    def test_sans_transfert_le_sujet_le_dit(self):
        self.assertIn("on garde tout", mail.sujet(_rec()))

    def test_le_compte_a_rebours_reste_lisible_partout(self):
        self.assertEqual(mail._quand(None), "deadline inconnue")
        self.assertEqual(mail._quand(-3), "deadline passée")
        self.assertIn("min", mail._quand(0.5))
        self.assertIn("h", mail._quand(24))
        self.assertIn("jours", mail._quand(96))


class DecisionEnTeteTests(unittest.TestCase):
    def test_trois_decisions_transfert_en_premier(self):
        lignes = mail.decisions(_rec_avec_transfert())
        self.assertEqual([t for t, _, _ in lignes],
                         ["Transfert", "Capitaine", "Formation"])

    def test_la_formation_annoncee_est_celle_d_apres_le_transfert(self):
        """Régression A6 : annoncer la formation d'avant serait faux."""
        rec = _rec_avec_transfert()
        _, forme, _ = mail.decisions(rec)[2]
        ap = rec["apres_transfert"]
        d, m, f = (sum(1 for p in ap["xi"] if p["element_type"] == t)
                   for t in (2, 3, 4))
        self.assertEqual(forme, f"{d}-{m}-{f}")


class ChaineDeCausaliteTests(unittest.TestCase):
    def test_la_chaine_explique_chaque_decision(self):
        chaine = mail.chaine(_rec_avec_transfert())
        self.assertGreaterEqual(len(chaine), 4)
        for titre, pourquoi in chaine:
            self.assertTrue(titre.strip(), "un maillon sans titre")
            self.assertTrue(pourquoi.strip(), f"« {titre} » sans justification")

    def test_le_gain_est_dit_mesure_sur_le_onze(self):
        """La correction A2 doit être visible par le lecteur, pas seulement
        appliquée dans le code."""
        textes = " ".join(p for _, p in mail.chaine(_rec_avec_transfert()))
        self.assertIn("MEILLEUR ONZE", textes)

    def test_conserver_dit_pourquoi_on_ne_transfere_pas(self):
        textes = " ".join(t + p for t, p in mail.chaine(_rec()))
        self.assertIn("seuil", textes)

    def test_le_brassard_explique_la_regle_du_vice(self):
        textes = " ".join(p for _, p in mail.chaine(_rec()))
        self.assertIn("aucune minute", textes)


class DeuxFormesUneSeuleDecisionTests(unittest.TestCase):
    """L'invariant qui compte : texte et HTML ne peuvent pas diverger."""

    def _noms_du_onze(self, rec):
        ap = rec.get("apres_transfert") or rec
        return [p["web_name"] for p in ap["xi"]]

    def test_le_onze_est_le_meme_dans_les_deux_formes(self):
        rec = _rec_avec_transfert()
        html, texte = mail.render_html(rec), mail.render_texte(rec)
        for nom in self._noms_du_onze(rec):
            self.assertIn(nom, texte)
            self.assertIn(nom, html)

    def test_le_joueur_vendu_n_apparait_dans_aucune_des_deux(self):
        rec = _rec_avec_transfert()
        sortant = rec["apres_transfert"]["out"]["web_name"]
        ap = rec["apres_transfert"]
        encore_la = {p["web_name"] for p in ap["xi"] + ap["bench"]}
        self.assertNotIn(sortant, encore_la)

    def test_le_capitaine_est_le_meme_dans_les_deux_formes(self):
        rec = _rec_avec_transfert()
        cap = (rec["apres_transfert"]["armband"]["captain"]["web_name"])
        self.assertIn(cap, mail.render_texte(rec))
        self.assertIn(cap, mail.render_html(rec))


class RenduTests(unittest.TestCase):
    def test_le_html_est_autonome_et_inoffensif(self):
        html = mail.render_html(_rec())
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("http://", html)
        self.assertNotIn("<img", html.lower())

    def test_le_html_echappe_les_noms(self):
        rec = dict(_rec())
        rec["leagues"] = [dict(rec["leagues"][0], name="<script>x</script>")]
        html = mail.render_html(rec)
        self.assertNotIn("<script>x", html)
        self.assertIn("&lt;script&gt;x", html)

    def test_le_texte_ne_laisse_pas_de_balisage_brut(self):
        texte = mail.render_texte(_rec())
        self.assertNotIn("**", texte)
        self.assertNotIn("<", texte)

    def test_le_mail_tient_dans_un_ecran_ou_deux(self):
        """Le rapport complet fait 12 000 caractères. Le mail doit être
        radicalement plus court, sinon il ne sert à rien."""
        self.assertLess(len(mail.render_texte(_rec())), 3500)

    def test_le_verdict_change_la_couleur_et_le_mot(self):
        rec = dict(_rec())
        for etat, mot in (("accepté", "feu vert"), ("bloqué", "ne pas jouer")):
            rec["verdict"] = type(rec["verdict"])(
                state=etat, checks=list(rec["verdict"].checks),
                summary="", kind="décision")
            self.assertIn(mot, mail.render_html(rec))

    def test_les_nombres_sont_a_la_francaise(self):
        html = mail.render_html(_rec_avec_transfert())
        corps = re.sub(r"<[^>]+>", " ", html)
        self.assertNotRegex(corps, r"\d+\.\d+\s*pts")


class AlertesEtLiguesTests(unittest.TestCase):
    def test_il_y_a_toujours_au_moins_une_ligne_d_alerte(self):
        self.assertTrue(mail.alertes(_rec()))

    def test_une_ligue_rend_rang_ecart_et_lecture(self):
        for l in mail.ligues(_rec()):
            for cle in ("nom", "rang", "ecart", "voisin", "lecture"):
                self.assertTrue(l[cle], f"{cle} vide")


if __name__ == "__main__":
    unittest.main()
