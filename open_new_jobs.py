import sqlite3
import webbrowser
import time

from common import DB_PATH

# --- KONFIGURÁCIA ---
DB_NAME = DB_PATH
QUERY = "SELECT link FROM jobs WHERE contacted = 0"
# TU JE ZMENA: Používame 'WHERE link = ?', aby sme updatli iba ten jeden link, ktorý otvárame
UPDATE_QUERY = "UPDATE jobs SET contacted = 1 WHERE link = ?"

def open_links():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute(QUERY)
        rows = cursor.fetchall()

        if not rows:
            print("Žiadne nové pracovné ponuky na otvorenie.")
            return

        print(f"Nájdených ponúk: {len(rows)}")

        for row in rows:
            url = row[0]
            print(f"Otváram: {url}")
            
            # 1. Otvoríme v prehliadači
            webbrowser.open(url)
            
            # 2. Hneď ho v DB označíme ako vybavený (iba tento jeden konkrétny link)
            cursor.execute(UPDATE_QUERY, (url,))
            
            # 3. Commitneme zmenu hneď, aby sme mali istotu
            conn.commit()
            
            time.sleep(0.7) # Mierne dlhšia pauza pre stabilitu

        conn.close()
        print("\nHotovo! Všetky linky boli otvorené a označené v DB.")

    except Exception as e:
        print(f"Vyskytla sa chyba: {e}")

if __name__ == "__main__":
    open_links()