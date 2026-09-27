import requests
from bs4 import BeautifulSoup
import datetime
import sqlite3
import sys
import time
import re
import json

# --- NASTAVENIA ---
DB_PATH = 'profesia_jobs.db'
BASE_URL = "https://www.profesia.sk/praca/bratislavsky-kraj/informacne-technologie/?salary=2000&salary_period=m"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
KEYWORDS = ['python', 'PYTHON', 'django', 'DJANGO', 'fastapi', 'FASTAPI', 'flask', 'Flask', 'webdeveloper', 'WEBDEVELOPER',  'web developer', 'WEB DEVELOPER', 'WEB-DEVELOPER', 'devops', 'DevOps', 'aplikačný špecialista', 'Application Specialist', 'SQL', 'sql', 'webapp', 'WEBAPP', 'web-app', 'WEB-APP','backend', 'BACKEND', 'fullstack', 'FULLSTACK', 'full-stack', 'FULL-STACK', 'programátor', 'programator', 'programming', 'PROGRAMMING', 'software engineer', 'SOFTWARE ENGINEER', 'vývojár', 'vývojárka', 'vývojár/ka', 'vývojárka/vývojár', 'developer', 'DEVELOPER', 'Junior', 'JUNIOR', 'junior']
BLACKLIST = ['financial', 'accountant', 'stáž', 'intern', 'marketing', 'sales']

# --- DATABÁZA ---
def init_db(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY,
        title TEXT,
        employer TEXT,
        location TEXT,
        salary TEXT,
        date TEXT,
        parsed_date TEXT,
        link TEXT UNIQUE,
        contacted INTEGER DEFAULT 0,
        answer_info TEXT DEFAULT ''
    )''')
    conn.commit()

# --- POMOCNÉ FUNKCIE ---
def get_job_details(link):
    """Stiahne detail inzerátu a extrahuje plat aj presný dátum zverejnenia."""
    try:
        response = requests.get(link, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        full_text = soup.get_text()

        # Extrakcia platu
        extracted_salary = None
        for tag in soup.find_all(['span', 'div', 'li', 'strong'], string=re.compile(r'EUR|mzdy|plat', re.I)):
            text = tag.get_text().strip()
            if 'EUR' in text and any(ch.isdigit() for ch in text):
                extracted_salary = text if len(text) < 100 else text[:97] + "..."
                break

        # Extrakcia presného dátumu (napr. "Dátum zverejnenia: 4.2.2026")
        published_date = None
        date_match = re.search(r'Dátum zverejnenia:\s*([\d\.]+)', full_text)
        if date_match:
            published_date = date_match.group(1)

        return full_text.lower(), extracted_salary, published_date

    except Exception as e:
        print(f"[WARN] get_job_details zlyhalo ({link}): {e}")
        return "", None, None


def parse_date(date_str):
    """Konvertuje textový dátum na datetime objekt."""
    now = datetime.datetime.now()
    ds = date_str.lower().strip()
    try:
        if re.match(r'\d+\.\d+\.\d+', ds):
            return datetime.datetime.strptime(ds, '%d.%m.%Y')
        if 'dňami' in ds or 'dňom' in ds:
            days = int(''.join(filter(str.isdigit, ds)))
            return now - datetime.timedelta(days=days)
        if 'týždňami' in ds or 'týždňom' in ds:
            weeks = int(''.join(filter(str.isdigit, ds)))
            return now - datetime.timedelta(weeks=weeks)
        if 'včera' in ds:
            return now - datetime.timedelta(days=1)
        return now
    except Exception:
        return now


def is_blacklisted(text):
    """Vráti True ak text obsahuje blacklist slovo."""
    return any(b in text for b in BLACKLIST)


def contains_keyword(text):
    """Vráti True ak text obsahuje aspoň jedno kľúčové slovo."""
    return any(k in text for k in KEYWORDS)


# --- HLAVNÝ SCRAPER ---
def scrape_profesia():
    with sqlite3.connect(DB_PATH) as conn:
        init_db(conn)
        c = conn.cursor()

        print("Sťahujem aktuálne ponuky z profesia.sk...")

        page = 1
        new_jobs_count = 0
        new_jobs = []

        while True:
            print(f"\n--- Spracovávam stranu {page} ---")
            url = f"{BASE_URL}&page_num={page}"

            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                response.raise_for_status()
            except Exception as e:
                print(f"[ERROR] Nepodarilo sa načítať stranu {page}: {e}")
                break

            soup = BeautifulSoup(response.content, 'html.parser')
            page_text = soup.get_text()

            if "Nenašli sme žiadne ponuky" in page_text or "nepodarilo nájsť žiadne ponuky" in page_text:
                print("Dosiahnutý koniec reálnych výsledkov.")
                break

            jobs = soup.find_all('li', class_='list-row')
            if not jobs:
                print("Žiadne ďalšie ponuky. Končím.")
                break

            for job in jobs:
                try:
                    title_el = job.find('span', class_='title')
                    if not title_el:
                        continue
                    title = title_el.text.strip()
                    title_lower = title.lower()

                    # Blacklist check na titule
                    if is_blacklisted(title_lower):
                        continue

                    link_el = job.find('a')
                    if not link_el:
                        continue
                    link = "https://www.profesia.sk" + link_el['href'].split('?')[0]

                    employer_el = job.find('span', class_='employer')
                    employer = employer_el.text.strip() if employer_el else "N/A"

                    # Kontrola duplicity pred stiahnutím detailu
                    c.execute("SELECT id FROM jobs WHERE link = ? OR (title = ? AND employer = ?)", (link, title, employer))
                    if c.fetchone():
                        continue

                    # Základné údaje zo zoznamu
                    salary = "Neuvedený"
                    salary_el = job.find('span', class_='label-info')
                    if salary_el and 'EUR' in salary_el.get_text():
                        salary = salary_el.get_text().strip()

                    date_text = "Dnes"
                    date_el = job.find('span', class_='post-date')
                    if date_el:
                        date_text = date_el.get_text().strip()

                    found_kw = contains_keyword(title_lower)

                    # Stiahni detail ak nemáme keyword, plat, alebo relatívny dátum
                    needs_detail = not found_kw or salary == "Neuvedený" or "dňami" in date_text.lower()
                    full_text = ""

                    if needs_detail:
                        full_text, detail_salary, detail_date = get_job_details(link)

                        if salary == "Neuvedený" and detail_salary:
                            salary = detail_salary

                        if detail_date:
                            date_text = detail_date

                        if not found_kw:
                            # Blacklist check aj na plnom texte
                            if is_blacklisted(full_text):
                                continue
                            found_kw = contains_keyword(full_text)

                        time.sleep(0.6)

                    if not found_kw:
                        continue

                    loc_el = job.find('span', class_='job-location')
                    location = loc_el.text.strip() if loc_el else "N/A"

                    parsed_date = parse_date(date_text).isoformat()

                    c.execute(
                        "INSERT OR IGNORE INTO jobs (title, employer, location, salary, date, parsed_date, link) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (title, employer, location, salary, date_text, parsed_date, link)
                    )
                    if c.rowcount > 0:
                        new_jobs_count += 1
                        new_jobs.append({"title": title, "employer": employer,
                                         "location": location, "salary": salary,
                                         "date": date_text, "link": link})
                        print(f"   [+] Pridané: {title} | {employer} | Plat: {salary} | Dátum: {date_text}")

                except Exception as e:
                    print(f"   [!] Chyba pri spracovaní inzerátu: {e}")
                    continue

            conn.commit()
            page += 1
            time.sleep(0.5)

        print(f"\nHotovo. Celkovo pridaných {new_jobs_count} nových pozícií.")

        # Export do TXT
        c.execute("SELECT title, employer, location, salary, date, link FROM jobs WHERE contacted = 0 ORDER BY parsed_date DESC")
        with open("profesia_ponuky.txt", 'w', encoding='utf-8') as f:
            f.write(f"Zoznam neoslovených ponúk (Aktualizované: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')})\n")
            f.write("-" * 50 + "\n\n")
            for j in c.fetchall():
                f.write(f"POZÍCIA: {j[0]}\nFIRMA:   {j[1]}\nPLAT:    {j[3]}\nKDE:     {j[2]}\nDÁTUM:   {j[4]}\nLINK:    {j[5]}\n")
                f.write("-" * 30 + "\n")

        print("Export do profesia_ponuky.txt hotový.")

        # Zoznam novo pridaných ponúk (tento beh) pre e-mailový report na serveri
        with open("new_jobs.json", "w", encoding="utf-8") as f:
            json.dump(new_jobs, f, ensure_ascii=False, indent=2)


# --- OZNAČENIE OSLOVENEJ PONUKY ---
def mark_contacted():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, employer FROM jobs WHERE contacted = 0 ORDER BY parsed_date DESC")
        jobs = c.fetchall()

        if not jobs:
            print("V zozname nie sú žiadne neoslovené ponuky.")
            return

        print("\n--- ZOZNAM NEOSLOVENÝCH PONÚK ---")
        for i, (job_id, title, employer) in enumerate(jobs, 1):
            print(f"{i}: {title} [{employer}]")

        try:
            choice = input("\nZadaj číslo ponuky, ktorú si oslovil (alebo 0 pre koniec): ").strip()
            if choice.isdigit() and int(choice) > 0:
                idx = int(choice) - 1
                if idx < len(jobs):
                    note = input("Poznámka (napr. poslané CV): ").strip()
                    c.execute("UPDATE jobs SET contacted = 1, answer_info = ? WHERE id = ?", (note, jobs[idx][0]))
                    conn.commit()
                    print("Označené ako vybavené.")
                else:
                    print("Neplatné číslo.")
        except Exception as e:
            print(f"Chyba: {e}")


# --- VSTUPNÝ BOD ---
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'mark':
        mark_contacted()
    else:
        scrape_profesia()