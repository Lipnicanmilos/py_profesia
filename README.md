# py_profesia — Job Scraper

Automatizovaný **scraper pracovných ponúk** z **Profesia.sk** a **LinkedIn**, ktorý filtruje
pozície podľa kľúčových slov (Python, Django, FastAPI, backend, …), ukladá ich do databázy,
označuje už oslovené firmy a vie voliteľne synchronizovať dáta do **AWS DynamoDB** a spúšťať
sa denne cez **AWS Lambda + EventBridge** s reportom cez **SES**.

Vznikol ako osobný nástroj na hľadanie práce — namiesto ručného prechádzania portálov beží
skript, ktorý každý deň vytiahne len relevantné nové ponuky a otvorí ich v prehliadači.

## Čo to robí

| Funkcia | Popis |
|---------|-------|
| **Scraping Profesia.sk** | Prechádza výsledky (stránkovanie), sťahuje detail ponuky pre plat a presný dátum |
| **Filtrovanie** | Whitelist kľúčových slov + blacklist (financie, marketing, stáže…) na titule aj plnom texte |
| **Scraping LinkedIn** | Prihlásenie cez `li_at` cookie, Selenium, prechod výsledkov a filtrovanie podľa keywords |
| **Deduplikácia** | Ponuky sa ukladajú s unikátnym linkom, duplikáty sa preskočia ešte pred stiahnutím detailu |
| **Sledovanie oslovených** | Príznak `contacted` + poznámka; interaktívne označovanie z CLI |
| **Otváranie ponúk** | `open_new_jobs.py` otvorí neoslovené linky v prehliadači a rovno ich označí |
| **Export** | TXT prehľad neoslovených ponúk; voliteľný JSON export z DynamoDB |
| **Cloud (voliteľné)** | Prehliadanie/synchronizácia DynamoDB tabuľky, denné spúšťanie cez Lambda + EventBridge + SES |

## Použité knižnice

| Oblasť | Knižnice |
|--------|----------|
| **HTTP / parsing** | requests, beautifulsoup4 |
| **Browser automation** | selenium (LinkedIn) |
| **Databáza** | sqlite3 (lokálne), boto3 (AWS DynamoDB) |
| **Konfigurácia** | python-dotenv |

## Stromová štruktúra

```
py_profesia/
├── py_search.py         # hlavný scraper Profesia.sk (scrape + mark contacted + TXT export)
├── open_new_jobs.py     # otvorí neoslovené ponuky v prehliadači a označí ich v DB
├── view_dynamodb.py     # CLI na prehliadanie/hľadanie/export DynamoDB tabuľky
├── linkedin/
│   └── find_linked.py   # LinkedIn scraper (Selenium, prihlásenie cez li_at cookie)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Inštalácia

```bash
python -m venv .venv
source .venv/Scripts/activate         # Windows (Git Bash)
# source .venv/bin/activate           # Linux / macOS

pip install -r requirements.txt

cp .env.example .env
# doplň LI_AT_COOKIE (potrebné len pre LinkedIn scraper)
```

## Použitie

```bash
# Profesia.sk – stiahne nové ponuky do profesia_jobs.db + vygeneruje profesia_ponuky.txt
python py_search.py

# Označ ponuku ako oslovenú (interaktívne)
python py_search.py mark

# Otvor všetky neoslovené ponuky v prehliadači (a označ ich)
python open_new_jobs.py

# LinkedIn scraper (vyžaduje LI_AT_COOKIE v .env)
python linkedin/find_linked.py

# Prehliadanie DynamoDB (ak používaš AWS backend)
python view_dynamodb.py all 100
python view_dynamodb.py search python
```

## Poznámky

- **Tajomstvá:** LinkedIn `li_at` cookie sa načítava z `.env` (mimo gitu). AWS prístup ide cez
  štandardné boto3 credentials (`~/.aws/credentials` / IAM rola) — v kóde nie sú žiadne kľúče.
- **Dáta:** databáza `profesia_jobs.db` a výstupné `.txt`/`.json` sú v `.gitignore`.
- Scraping rešpektuje mierne pauzy medzi požiadavkami; hodnoty (URL, kľúčové slová, plat)
  sa dajú upraviť v konštantách na začiatku `py_search.py`.
- Použitie scraperov je na vlastnú zodpovednosť v súlade s podmienkami daných portálov.
