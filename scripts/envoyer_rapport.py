#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Envoie un rapport Markdown par e-mail. Bibliothèque standard uniquement.

Pourquoi pas une action GitHub toute faite : ce script transporte l'effectif
d'un manager et un mot de passe d'application. Une dépendance tierce dans ce
chemin-là ajoute un maillon que personne n'audite. `smtplib` est dans Python.

    python3 scripts/envoyer_rapport.py --sujet "GW2" \
        --corps data/reports/GW2-recommandation-*.md \
        --piece-jointe data/reports/GW2-audit-*.md

Identifiants lus dans l'environnement, jamais en argument (les arguments se
retrouvent dans les journaux de CI) :

    SMTP_HOTE        défaut smtp.gmail.com
    SMTP_PORT        défaut 587 (STARTTLS)
    SMTP_UTILISATEUR adresse d'envoi
    SMTP_MOTDEPASSE  mot de passe d'application, jamais le mot de passe du compte
    MAIL_DESTINATAIRE  défaut : SMTP_UTILISATEUR

Sort en code 0 si l'envoi réussit, 1 sinon, avec un diagnostic lisible. Il ne
lève jamais le contenu du rapport dans la sortie : ce sont des données
personnelles, et les journaux de CI se relisent.
"""

import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

MAX_CORPS = 900_000        # garde-fou : un corps de mail n'est pas un dépôt


def _env(cle, defaut=None, requis=False):
    v = (os.environ.get(cle) or "").strip() or defaut
    if requis and not v:
        raise SystemExit(f"Variable d'environnement {cle} absente ou vide.")
    return v


def construire(sujet, corps_md, pieces, expediteur, destinataire):
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = expediteur
    msg["To"] = destinataire
    msg.set_content(corps_md[:MAX_CORPS] or "(rapport vide)")
    for chemin in pieces:
        p = Path(chemin)
        if not p.exists():
            continue
        msg.add_attachment(p.read_bytes(), maintype="text", subtype="markdown",
                           filename=p.name)
    return msg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sujet", required=True)
    ap.add_argument("--corps", help="fichier Markdown mis dans le corps du mail")
    ap.add_argument("--texte", help="corps littéral, si aucun fichier")
    ap.add_argument("--piece-jointe", action="append", default=[],
                    help="fichier à joindre (répétable)")
    args = ap.parse_args(argv)

    utilisateur = _env("SMTP_UTILISATEUR", requis=True)
    motdepasse = _env("SMTP_MOTDEPASSE", requis=True)
    destinataire = _env("MAIL_DESTINATAIRE", utilisateur)
    hote = _env("SMTP_HOTE", "smtp.gmail.com")
    port = int(_env("SMTP_PORT", "587"))

    corps = args.texte or ""
    if args.corps:
        p = Path(args.corps)
        if not p.exists():
            raise SystemExit(f"Corps introuvable : {p}")
        corps = p.read_text(encoding="utf-8")

    msg = construire(args.sujet, corps, args.piece_jointe, utilisateur, destinataire)
    contexte = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(hote, port, context=contexte, timeout=60) as s:
                s.login(utilisateur, motdepasse)
                s.send_message(msg)
        else:
            with smtplib.SMTP(hote, port, timeout=60) as s:
                s.starttls(context=contexte)
                s.login(utilisateur, motdepasse)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise SystemExit(
            f"Authentification refusée par {hote}. Sur Gmail, il faut un MOT DE "
            "PASSE D'APPLICATION (Compte Google → Sécurité → Validation en deux "
            "étapes → Mots de passe des applications), pas le mot de passe du "
            "compte.")
    except (smtplib.SMTPException, OSError) as e:
        raise SystemExit(f"Envoi impossible via {hote}:{port} — {e}")

    # Ni le sujet complet, ni le corps : les journaux de CI se relisent.
    print(f"Mail envoyé à {destinataire[:3]}…@… "
          f"({len(args.piece_jointe)} pièce(s) jointe(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
