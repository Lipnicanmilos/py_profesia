"""E-mailový report o nových pracovných ponukách z Profesia.sk.

Číta `new_jobs.json` (vytvorí ho py_search.py) a pošle súhrn e-mailom.
Kredenciály sa berú z premenných prostredia (na serveri = GitHub Secrets):

  SMTP_HOST   default smtp.gmail.com
  SMTP_PORT   default 587
  SMTP_USER   prihlasovací e-mail (napr. tvoj gmail)
  SMTP_PASS   app password (Gmail App Password, NIE bežné heslo)
  MAIL_TO     komu poslať report
  MAIL_FROM   default = SMTP_USER
  SEND_EMPTY  "1" = pošli mail aj keď nič nové (default "0" = ticho)

Spustenie: python report_email.py
"""
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage

NEW_JOBS = "new_jobs.json"


def load_new_jobs():
    try:
        with open(NEW_JOBS, encoding="utf-8-sig") as f:  # utf-8-sig: znesie aj BOM
            return json.load(f)
    except FileNotFoundError:
        return []


def build_body(jobs):
    lines = [
        f"Nové IT ponuky z Profesia.sk — {datetime.now():%d.%m.%Y %H:%M}",
        f"Počet nových: {len(jobs)}",
        "=" * 50,
        "",
    ]
    for j in jobs:
        lines += [
            f"• {j['title']}  —  {j['employer']}",
            f"  Plat: {j['salary']}   |   Kde: {j['location']}   |   Dátum: {j['date']}",
            f"  {j['link']}",
            "",
        ]
    return "\n".join(lines)


def main():
    jobs = load_new_jobs()
    send_empty = os.getenv("SEND_EMPTY", "0") == "1"

    if not jobs and not send_empty:
        print("Žiadne nové ponuky — e-mail sa neposiela.")
        return

    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    try:
        user = os.environ["SMTP_USER"]
        password = os.environ["SMTP_PASS"]
        mail_to = os.environ["MAIL_TO"]
    except KeyError as e:
        print(f"[ERROR] Chýba premenná prostredia {e} — nastav SMTP_USER, SMTP_PASS, MAIL_TO.")
        sys.exit(1)
    mail_from = os.getenv("MAIL_FROM", user)

    subject = (f"JobScraper: {len(jobs)} nových IT ponúk"
               if jobs else "JobScraper: žiadne nové ponuky")
    body = build_body(jobs) if jobs else "Dnes žiadne nové ponuky."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(user, password)
        s.send_message(msg)
    print(f"E-mail odoslaný na {mail_to} ({len(jobs)} ponúk).")


if __name__ == "__main__":
    main()
