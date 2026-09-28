"""Scraper IT ponúk z LinkedIn — verejné vyhľadávanie pracovných ponúk (bez prihlásenia).

Nepoužíva Selenium ani li_at cookie: prihlásená session zo serverovej IP by riskovala
zablokovanie LinkedIn účtu. Verejný endpoint vracia tie isté karty ponúk ako web.

  python linkedin_search.py
"""
import os
import time
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from common import (add_job, annotate, append_new_jobs, export_txt, fetch, get_db,
                    is_blacklisted, is_known)

# --- NASTAVENIA ---
SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
GEO_ID = "100289135"        # Bratislava (rovnaká oblasť ako pôvodné vyhľadávanie)
SEARCH_KEYWORDS = ["python", "django", "fastapi", "backend",
                   "aplikačný špecialista", "application support"]
# obdobie zverejnenia: r86400 = 24 h, r259200 = 3 dni, r604800 = týždeň.
# 3 dni kryjú aj vynechaný deň; duplicity odfiltruje databáza.
TIME_RANGE = os.getenv("LINKEDIN_TIME_RANGE", "r259200")
MAX_PAGES_PER_KEYWORD = 5   # 10 ponúk na stranu
PAUSE = 2.0


def scrape_linkedin():
    stats = {"searches": 0, "cards": 0, "known": 0, "blacklisted": 0, "new": 0}
    new_jobs = []

    with get_db() as conn:
        for keyword in SEARCH_KEYWORDS:
            print(f"\n--- LinkedIn: „{keyword}“ ---")
            start = 0
            for _ in range(MAX_PAGES_PER_KEYWORD):
                url = SEARCH_URL + "?" + urlencode({"keywords": keyword, "geoId": GEO_ID,
                                                    "f_TPR": TIME_RANGE, "start": start})
                response = fetch(url, stats)
                time.sleep(PAUSE)
                if response is None:
                    annotate("warning", "LinkedIn",
                             f"Vyhľadávanie „{keyword}“ (start={start}) zlyhalo "
                             f"(chyby HTTP: {stats.get('http_errors')})")
                    break
                stats["searches"] += 1

                cards = BeautifulSoup(response.content, "html.parser").select("div.base-card")
                if not cards:
                    break

                for card in cards:
                    stats["cards"] += 1
                    title_el = card.select_one("h3.base-search-card__title")
                    urn = card.get("data-entity-urn", "")
                    if not title_el or not urn.startswith("urn:li:jobPosting:"):
                        continue
                    title = title_el.get_text(strip=True)
                    link = f"https://www.linkedin.com/jobs/view/{urn.rsplit(':', 1)[1]}"

                    if is_blacklisted(title):
                        stats["blacklisted"] += 1
                        continue

                    company_el = card.select_one("h4.base-search-card__subtitle")
                    employer = company_el.get_text(strip=True) if company_el else "N/A"
                    if is_known(conn, link, title, employer):
                        stats["known"] += 1
                        continue

                    loc_el = card.select_one("span.job-search-card__location")
                    salary_el = card.select_one("span.job-search-card__salary-info")
                    time_el = card.select_one("time")
                    posted = time_el.get("datetime", "") if time_el else ""

                    if add_job(conn, new_jobs, source="LinkedIn", title=title, employer=employer,
                               location=loc_el.get_text(strip=True) if loc_el else "N/A",
                               salary=salary_el.get_text(" ", strip=True) if salary_el else "Neuvedený",
                               date=posted or "?", parsed_date=posted, link=link):
                        stats["new"] += 1
                        print(f"   [+] {title} | {employer} | {posted}")

                conn.commit()
                start += len(cards)

        export_txt(conn)

    append_new_jobs(new_jobs)
    summary = ", ".join(f"{k}={v}" for k, v in stats.items())
    print(f"\nHotovo: {summary}")
    annotate("notice", "LinkedIn", summary)


if __name__ == "__main__":
    scrape_linkedin()
