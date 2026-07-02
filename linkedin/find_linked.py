import sqlite3
import time
import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException

# --- NASTAVENIA ---
# LinkedIn session cookie (li_at) sa načíta z .env – NIKDY ho necommituj do repa.
load_dotenv()
LI_AT_COOKIE = os.getenv("LI_AT_COOKIE")
if not LI_AT_COOKIE:
    raise SystemExit("Chýba LI_AT_COOKIE v .env (pozri .env.example).")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
DB_PATH = os.path.join(PARENT_DIR, 'profesia_jobs.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS jobs_linkedin 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     title TEXT, 
                     company TEXT, 
                     link TEXT UNIQUE, 
                     date_found DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()
    print(f'[INFO] Databáza pripravená na: {DB_PATH}')

def scrape_linkedin():
    chrome_options = Options()
    chrome_options.add_argument('--window-size=1600,1000')
    driver = webdriver.Chrome(options=chrome_options)
    
    keywords = ["python", "django", "aplikačný špecialista"]
    
    try:
        print("[INFO] Prihlasujem sa...")
        driver.get("https://www.linkedin.com")
        driver.add_cookie({'name': 'li_at', 'value': LI_AT_COOKIE, 'domain': '.www.linkedin.com'})
        driver.refresh()
        time.sleep(4)

        new_jobs_count = 0
        already_in_db_count = 0
        total_analyzed_count = 0
        
        # DYNAMICKÉ STRÁNKOVANIE - prechádza všetky dostupné stránky
        start_index = 0
        
        while True:
            print(f"\n[--- STRÁNKA: Štartovací index {start_index} ---]")
            
            search_url = f"https://www.linkedin.com/jobs/search/?currentJobId=4409567042&f_TPR=r86400&geoId=100289135&origin=JOB_SEARCH_PAGE_LOCATION_HISTORY&refresh=true&start={start_index}"
            driver.get(search_url)
            time.sleep(5)

            # Scrollovanie pre načítanie kariet na aktuálnej stránke
            body = driver.find_element(By.TAG_NAME, "body")
            for _ in range(5):
                body.send_keys(Keys.PAGE_DOWN)
                time.sleep(0.6)

            job_cards = driver.find_elements(By.CSS_SELECTOR, ".job-card-container, [data-job-id]")
            
            if not job_cards:
                print("[INFO] Žiadne ďalšie karty nenájdené. Končím stránkovanie.")
                break

            print(f"[INFO] Na tejto stránke nájdených {len(job_cards)} ponúk.")
            
            conn = sqlite3.connect(DB_PATH)
            
            for i, card in enumerate(job_cards, 1):
                total_analyzed_count += 1
                try:
                    title = card.find_element(By.CSS_SELECTOR, "a.job-card-list__title, .artdeco-entity-lockup__title").text.strip()
                    company = card.find_element(By.CSS_SELECTOR, ".job-card-container__primary-description, .artdeco-entity-lockup__subtitle").text.strip()
                    link = card.find_element(By.TAG_NAME, "a").get_attribute("href").split('?')[0]

                    print(f"[{total_analyzed_count}] Analyzujem: {title} | {company}", end="\r")

                    # Kontrola v DB
                    check = conn.execute('SELECT id FROM jobs_linkedin WHERE title = ? AND company = ?', (title, company)).fetchone()
                    if check: 
                        already_in_db_count += 1
                        continue

                    # Klik na detail
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                    card.click()
                    time.sleep(1.5)

                    # Získanie popisu
                    try:
                        desc_element = driver.find_element(By.ID, "job-details")
                        description_text = desc_element.text.lower()
                    except:
                        description_text = ""

                    full_text = (title + " " + description_text).lower()
                    if any(word.lower() in full_text for word in keywords):
                        cursor = conn.execute(
                            'INSERT OR IGNORE INTO jobs_linkedin (title, company, link) VALUES (?, ?, ?)', 
                            (title, company, link)
                        )
                        if cursor.rowcount > 0:
                            print(f'\n[MATCH & NEW] {title} | {company}')
                            new_jobs_count += 1
                    
                except Exception:
                    continue 

            conn.commit()
            conn.close()
            
            # Posun na ďalšiu stránku
            start_index += 25
            
            # LinkedIn obmedzuje výsledky na max ~1000 (index 975)
            if start_index >= 1000:
                print("[INFO] Dosiahnutý limit LinkedIn (1000 výsledkov). Končím.")
                break
            
            # Malá pauza medzi stránkami
            time.sleep(2)

        print(f"\n\n--- FINÁLNA ŠTATISTIKA ---")
        print(f"Celkovo analyzovaných pozícií: {total_analyzed_count}")
        print(f"Už existovalo v databáze: {already_in_db_count}")
        print(f"Novo pridaných do databázy: {new_jobs_count}")
        print(f"--------------------------")

    except Exception as e:
        print(f"\n[ERROR] Nastala chyba: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    init_db()
    scrape_linkedin()