"""Scraper IT ponúk z Profesia.sk (Bratislavský kraj, plat od 2000 €).

  python py_search.py        — stiahne nové ponuky do DB + ponuky.txt + new_jobs.json
  python py_search.py mark   — interaktívne označí ponuku ako oslovenú
"""
import datetime
import re
import sys
import time

from bs4 import BeautifulSoup

from common import (add_job, annotate, append_new_jobs, contains_keyword, export_txt,
                    fetch, get_db, is_blacklisted, is_known, mark_rejected)

# --- NASTAVENIA ---
BASE_URL = ("https://www.profesia.sk/praca/bratislavsky-kraj/informacne-technologie/"
            "?salary=2000&salary_period=m")
MAX_PAGES = 80          # poistka proti nekonečnému stránkovaniu
PAGE_PAUSE = 1.0        # s medzi stranami zoznamu
DETAIL_PAUSE = 0.8      # s medzi detailmi ponúk


def get_job_details(link, stats):
    """Stiahne detail inzerátu. Vráti (text, plat, dátum) alebo None pri chybe."""
    stats["detail_fetches"] += 1
    response = fetch(link, stats)
    if response is None:
        stats["detail_failed"] += 1
        return None

    soup = BeautifulSoup(response.content, "html.parser")
    full_text = soup.get_text()

    salary = None
    for tag in soup.find_all(["span", "div", "li", "strong"], string=re.compile(r"EUR|mzdy|plat", re.I)):
        text = tag.get_text().strip()
        if "EUR" in text and any(ch.isdigit() for ch in text):
            salary = text if len(text) < 100 else text[:97] + "..."
            break

    published = None
    m = re.search(r"Dátum zverejnenia:\s*([\d\.]+)", full_text)
    if m:
        published = m.group(1)

    return full_text, salary, published


def parse_date(date_str):
    """Textový dátum z Profesie („pred 3 dňami", „4.2.2026", „včera") → datetime."""
    now = datetime.datetime.now()
    ds = date_str.lower().strip()
    try:
        if re.match(r"\d+\.\d+\.\d+", ds):
            return datetime.datetime.strptime(ds, "%d.%m.%Y")
        if "dňami" in ds or "dňom" in ds:
            return now - datetime.timedelta(days=int("".join(filter(str.isdigit, ds))))
        if "týždňami" in ds or "týždňom" in ds:
            return now - datetime.timedelta(weeks=int("".join(filter(str.isdigit, ds))))
        if "včera" in ds:
            return now - datetime.timedelta(days=1)
    except ValueError:
        pass
    return now


def scrape_profesia():
    stats = {"pages": 0, "rows": 0, "known": 0, "blacklisted": 0, "no_keyword": 0,
             "detail_fetches": 0, "detail_failed": 0, "new": 0}
    new_jobs = []

    with get_db() as conn:
        print("Sťahujem aktuálne ponuky z profesia.sk...")

        for page in range(1, MAX_PAGES + 1):
            print(f"\n--- Strana {page} ---")
            response = fetch(f"{BASE_URL}&page_num={page}", stats)
            if response is None:
                reason = ("ochrana proti botom, HTTP 202" if stats.get("blocked")
                          else f"chyby HTTP: {stats.get('http_errors')}")
                annotate("warning", "Profesia", f"Stranu {page} sa nepodarilo načítať ({reason})")
                break

            soup = BeautifulSoup(response.content, "html.parser")
            page_text = soup.get_text()
            if "Nenašli sme žiadne ponuky" in page_text or "nepodarilo nájsť žiadne ponuky" in page_text:
                print("Koniec výsledkov.")
                break

            jobs = soup.find_all("li", class_="list-row")
            if not jobs:
                if page == 1:
                    annotate("warning", "Profesia",
                             f"Strana 1 neobsahuje žiadne ponuky (HTTP 200, {len(response.content)} B) "
                             "— zmenené HTML alebo blokovanie servera")
                print("Žiadne ďalšie ponuky. Končím.")
                break
            stats["pages"] += 1

            for job in jobs:
                try:
                    title_el = job.find("span", class_="title")
                    link_el = job.find("a")
                    if not title_el or not link_el:
                        continue
                    stats["rows"] += 1
                    title = title_el.text.strip()
                    link = "https://www.profesia.sk" + link_el["href"].split("?")[0]

                    if is_blacklisted(title):
                        stats["blacklisted"] += 1
                        continue

                    employer_el = job.find("span", class_="employer")
                    employer = employer_el.text.strip() if employer_el else "N/A"

                    # duplicita (alebo už raz odmietnutá) → detail sa nesťahuje
                    if is_known(conn, link, title, employer):
                        stats["known"] += 1
                        continue

                    salary = "Neuvedený"
                    salary_el = job.find("span", class_="label-info")
                    if salary_el and "EUR" in salary_el.get_text():
                        salary = salary_el.get_text().strip()

                    date_text = "Dnes"
                    date_el = job.find("span", class_="post-date")
                    if date_el:
                        date_text = date_el.get_text().strip()

                    found_kw = contains_keyword(title)

                    # detail: keď kľúčové slovo nie je v názve, alebo chýba plat / presný dátum
                    if not found_kw or salary == "Neuvedený" or "dňami" in date_text.lower():
                        details = get_job_details(link, stats)
                        time.sleep(DETAIL_PAUSE)
                        if details is None:
                            if not found_kw:
                                if stats.get("blocked"):
                                    break  # Profesia blokuje — ďalšie požiadavky nemajú zmysel
                                continue  # nevieme rozhodnúť — skúsi sa zajtra znova
                        else:
                            full_text, detail_salary, detail_date = details
                            if salary == "Neuvedený" and detail_salary:
                                salary = detail_salary
                            if detail_date:
                                date_text = detail_date
                            if not found_kw:
                                found_kw = contains_keyword(full_text)

                    if not found_kw:
                        stats["no_keyword"] += 1
                        mark_rejected(conn, link)
                        continue

                    loc_el = job.find("span", class_="job-location")
                    location = loc_el.text.strip() if loc_el else "N/A"

                    if add_job(conn, new_jobs, source="Profesia", title=title, employer=employer,
                               location=location, salary=salary, date=date_text,
                               parsed_date=parse_date(date_text).isoformat(), link=link):
                        stats["new"] += 1
                        print(f"   [+] {title} | {employer} | {salary} | {date_text}")
                    if stats.get("blocked"):
                        break

                except Exception as e:
                    print(f"   [!] Chyba pri spracovaní inzerátu: {e}")

            conn.commit()
            if stats.get("blocked"):
                annotate("warning", "Profesia",
                         "Profesia blokuje tento server (ochrana proti botom, HTTP 202) — "
                         "beh zastavený, spracovaná len časť ponúk")
                break
            time.sleep(PAGE_PAUSE)

        export_txt(conn)

    append_new_jobs(new_jobs)
    summary = ", ".join(f"{k}={v}" for k, v in stats.items())
    print(f"\nHotovo: {summary}")
    annotate("notice", "Profesia", summary)
    if stats["detail_failed"]:
        annotate("warning", "Profesia",
                 f"{stats['detail_failed']} detailov ponúk sa nepodarilo stiahnuť — skúsia sa pri ďalšom behu")


def mark_contacted():
    with get_db() as conn:
        jobs = conn.execute("SELECT id, title, employer, source FROM jobs WHERE contacted = 0"
                            " ORDER BY found_at DESC, parsed_date DESC").fetchall()
        if not jobs:
            print("V zozname nie sú žiadne neoslovené ponuky.")
            return

        print("\n--- ZOZNAM NEOSLOVENÝCH PONÚK ---")
        for i, (_, title, employer, source) in enumerate(jobs, 1):
            print(f"{i}: [{source}] {title} [{employer}]")

        choice = input("\nZadaj číslo ponuky, ktorú si oslovil (alebo 0 pre koniec): ").strip()
        if choice.isdigit() and 0 < int(choice) <= len(jobs):
            note = input("Poznámka (napr. poslané CV): ").strip()
            conn.execute("UPDATE jobs SET contacted = 1, answer_info = ? WHERE id = ?",
                         (note, jobs[int(choice) - 1][0]))
            print("Označené ako vybavené.")
        elif choice != "0":
            print("Neplatné číslo.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "mark":
        mark_contacted()
    else:
        scrape_profesia()
