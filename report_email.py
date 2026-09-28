"""E-mailový report o nových pracovných ponukách (Profesia.sk + LinkedIn).

Číta new_jobs.json (plnia ho py_search.py a linkedin_search.py), pošle súhrn e-mailom
a v GitHub Actions zapíše prehľad aj na stránku behu (Summary).

Premenné prostredia (na serveri GitHub Secrets, lokálne súbor .env):
  SMTP_USER   prihlasovací e-mail (Gmail)
  SMTP_PASS   Gmail App Password (nie bežné heslo)
  MAIL_TO     komu poslať report
  SMTP_HOST   default smtp.gmail.com      SMTP_PORT  default 587
  MAIL_FROM   default = SMTP_USER
  SEND_EMPTY  "1" = pošli mail aj keď nič nové (default ticho)
"""
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage

from common import NEW_JOBS_PATH

try:  # lokálne pohodlie: premenné z .env
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SOURCES = ["Profesia", "LinkedIn"]


def load_new_jobs():
    try:
        with open(NEW_JOBS_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def by_source(jobs):
    groups = {s: [] for s in SOURCES}
    for j in jobs:
        groups.setdefault(j.get("source", "Profesia"), []).append(j)
    return {s: js for s, js in groups.items() if js}


def counts_label(groups):
    return ", ".join(f"{s} {len(js)}" for s, js in groups.items())


def build_body(jobs):
    groups = by_source(jobs)
    lines = [f"Nové IT ponuky — {datetime.now():%d.%m.%Y %H:%M}",
             f"Spolu: {len(jobs)} ({counts_label(groups)})", ""]
    for source, items in groups.items():
        lines += [f"=== {source} ({len(items)}) ===", ""]
        for j in items:
            lines += [f"• {j['title']}  —  {j['employer']}",
                      f"  Plat: {j['salary']}   |   Kde: {j['location']}   |   Dátum: {j['date']}",
                      f"  {j['link']}", ""]
    return "\n".join(lines)


def write_github_summary(jobs):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    groups = by_source(jobs)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"## Nové IT ponuky: {len(jobs)}" + (f" ({counts_label(groups)})" if jobs else "") + "\n\n")
        for source, items in groups.items():
            f.write(f"### {source}\n\n| Pozícia | Firma | Plat | Dátum |\n|---|---|---|---|\n")
            for j in items:
                title = j["title"].replace("|", "/")
                f.write(f"| [{title}]({j['link']}) | {j['employer'].replace('|', '/')} "
                        f"| {j['salary'].replace('|', '/')} | {j['date']} |\n")
            f.write("\n")
        f.write("Všetky neoslovené ponuky sú v artefakte **ponuky** (súbor ponuky.txt) nižšie na tejto stránke.\n")


def main():
    jobs = load_new_jobs()
    write_github_summary(jobs)

    if not jobs and os.getenv("SEND_EMPTY", "0") != "1":
        print("Žiadne nové ponuky — e-mail sa neposiela.")
        return

    try:
        user = os.environ["SMTP_USER"]
        password = os.environ["SMTP_PASS"]
        mail_to = os.environ["MAIL_TO"]
    except KeyError as e:
        print(f"[ERROR] Chýba premenná prostredia {e} — nastav SMTP_USER, SMTP_PASS, MAIL_TO.")
        sys.exit(1)

    groups = by_source(jobs)
    msg = EmailMessage()
    msg["Subject"] = (f"JobScraper: {len(jobs)} nových IT ponúk ({counts_label(groups)})"
                      if jobs else "JobScraper: žiadne nové ponuky")
    msg["From"] = os.getenv("MAIL_FROM", user)
    msg["To"] = mail_to
    msg.set_content(build_body(jobs) if jobs else "Dnes žiadne nové ponuky.")

    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"),
                      int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(user, password)
        s.send_message(msg)
    print(f"E-mail odoslaný na {mail_to} ({len(jobs)} ponúk).")

    if os.path.exists(NEW_JOBS_PATH):
        os.remove(NEW_JOBS_PATH)  # ďalší report bude obsahovať len novšie ponuky


if __name__ == "__main__":
    main()
