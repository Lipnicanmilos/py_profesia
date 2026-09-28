"""Spoločné veci pre scrapery (Profesia.sk, LinkedIn): DB, HTTP, filtre, výstupy."""
import datetime
import json
import os
import re
import sqlite3
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "profesia_jobs.db")
NEW_JOBS_PATH = os.path.join(BASE_DIR, "new_jobs.json")
TXT_PATH = os.path.join(BASE_DIR, "ponuky.txt")

IN_CI = os.getenv("GITHUB_ACTIONS") == "true"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sk-SK,sk;q=0.9,cs;q=0.8,en;q=0.7",
}

# Kľúčové slová — hľadajú sa (bez ohľadu na veľkosť písmen) v názve alebo texte ponuky
KEYWORDS = [
    "python", "django", "fastapi", "flask",
    "backend", "back-end", "fullstack", "full-stack",
    "web developer", "webdeveloper", "web-developer", "webapp", "web-app",
    "devops", "sql",
    "aplikačný špecialista", "application specialist", "application support",
    "programátor", "programator", "programming",
    "software engineer", "vývojár", "vývojárka", "developer", "junior",
]

# Vyraďovacie slová — kontrolujú sa LEN v názve pozície a ako celé slová
# (v plnom texte by „internet", „interný", „financial services" vyradili aj IT ponuky)
BLACKLIST = [
    "financial", "accountant", "stáž", "intern", "internship",
    "marketing", "sales", "business developer",
]
_BLACKLIST_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in BLACKLIST) + r")\b", re.I)


def is_blacklisted(title):
    return bool(_BLACKLIST_RE.search(title))


def contains_keyword(text):
    text = text.lower()
    return any(k in text for k in KEYWORDS)


# --- DIAGNOSTIKA ---
def annotate(level, title, message):
    """V GitHub Actions anotácia (viditeľná na stránke behu), lokálne obyčajný výpis."""
    if IN_CI:
        print(f"::{level} title={title}::{message}")
    else:
        print(f"[{level.upper()}] {title}: {message}")


# --- HTTP ---
_session = requests.Session()
_session.headers.update(HEADERS)

# Ochrana proti botom: 202 = WAF challenge (Profesia za CloudFront), 999 = blok LinkedIn.
# Takú odpoveď neopakujeme — stránka dáva najavo, že automatický prístup z tejto IP nechce.
BLOCK_STATUSES = {202, 999}


def fetch(url, stats, retries=3):
    """GET s opakovaním pri 429/5xx a sieťových chybách. Vráti Response alebo None.

    Chyby sa počítajú do stats["http_errors"]; blokovanie nastaví stats["blocked"].
    """
    for attempt in range(1, retries + 1):
        try:
            r = _session.get(url, timeout=20)
        except requests.RequestException as e:
            status, final = type(e).__name__, False
        else:
            if r.status_code == 200:
                return r
            status = str(r.status_code)
            # blokovanie alebo neexistujúca stránka — opakovanie nepomôže
            final = r.status_code in BLOCK_STATUSES or r.status_code in (400, 404, 410)
            if r.status_code in BLOCK_STATUSES:
                stats["blocked"] = stats.get("blocked", 0) + 1
        errors = stats.setdefault("http_errors", {})
        errors[status] = errors.get(status, 0) + 1
        if final:
            return None
        if attempt < retries:
            time.sleep(3 * attempt ** 2)  # 3 s, 12 s
    return None


# --- DATABÁZA ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY,
        title TEXT,
        employer TEXT,
        location TEXT,
        salary TEXT,
        date TEXT,
        parsed_date TEXT,
        link TEXT UNIQUE,
        contacted INTEGER DEFAULT 0,
        answer_info TEXT DEFAULT '',
        source TEXT DEFAULT 'Profesia',
        found_at TEXT
    )""")
    # migrácia starších DB (pred pridaním LinkedIn do spoločnej tabuľky)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT 'Profesia'")
    if "found_at" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN found_at TEXT")
    conn.execute("UPDATE jobs SET source = 'Profesia' WHERE source IS NULL OR source = 'profesia'")
    # ponuky, ktoré už prešli filtrom a neprešli — aby sa detail nesťahoval každý deň znova
    conn.execute("""CREATE TABLE IF NOT EXISTS seen_links (
        link TEXT PRIMARY KEY,
        seen_at TEXT
    )""")
    conn.commit()
    return conn


def is_known(conn, link, title=None, employer=None):
    if conn.execute("SELECT 1 FROM jobs WHERE link = ?", (link,)).fetchone():
        return True
    if title and employer and conn.execute(
            "SELECT 1 FROM jobs WHERE title = ? AND employer = ?", (title, employer)).fetchone():
        return True
    return conn.execute("SELECT 1 FROM seen_links WHERE link = ?", (link,)).fetchone() is not None


def mark_rejected(conn, link):
    conn.execute("INSERT OR IGNORE INTO seen_links (link, seen_at) VALUES (?, ?)",
                 (link, _now()))


def add_job(conn, new_jobs, *, source, title, employer, location, salary, date, parsed_date, link):
    """Uloží ponuku; ak je nová, pridá ju do new_jobs (pre e-mail). Vráti True ak nová."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO jobs (title, employer, location, salary, date, parsed_date,"
        " link, source, found_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, employer, location, salary, date, parsed_date, link, source, _now()))
    if cur.rowcount > 0:
        new_jobs.append({"source": source, "title": title, "employer": employer,
                         "location": location, "salary": salary, "date": date, "link": link})
        return True
    return False


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# --- VÝSTUPY ---
def append_new_jobs(jobs):
    """Pridá nové ponuky do new_jobs.json (zoznam „nové od posledného reportu")."""
    existing = []
    if os.path.exists(NEW_JOBS_PATH):
        with open(NEW_JOBS_PATH, encoding="utf-8-sig") as f:
            existing = json.load(f)
    with open(NEW_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing + jobs, f, ensure_ascii=False, indent=2)


def export_txt(conn):
    """Všetky neoslovené ponuky (oba zdroje) do ponuky.txt, najnovšie hore."""
    rows = conn.execute(
        "SELECT source, title, employer, location, salary, date, link FROM jobs"
        " WHERE contacted = 0 ORDER BY found_at DESC, parsed_date DESC").fetchall()
    with open(TXT_PATH, "w", encoding="utf-8") as f:
        f.write(f"Neoslovené ponuky ({len(rows)}) — aktualizované "
                f"{datetime.datetime.now():%d.%m.%Y %H:%M}\n")
        f.write("-" * 50 + "\n\n")
        for source, title, employer, location, salary, date, link in rows:
            f.write(f"ZDROJ:   {source}\nPOZÍCIA: {title}\nFIRMA:   {employer}\n"
                    f"PLAT:    {salary}\nKDE:     {location}\nDÁTUM:   {date}\nLINK:    {link}\n")
            f.write("-" * 30 + "\n")
