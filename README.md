# py_profesia — Job Scraper (Profesia.sk + LinkedIn)

Automatizovaný **scraper IT pracovných ponúk** z **Profesia.sk** a **LinkedIn**. Každý deň
o **08:00** beží na serveri (**GitHub Actions**), vyfiltruje relevantné pozície podľa kľúčových
slov, odloží ich do databázy a pošle **e-mailový report len s novými ponukami**.

Vznikol ako osobný nástroj na hľadanie práce — namiesto ručného prechádzania portálov príde
každé ráno mail s tým, čo pribudlo.

## Čo to robí

| Funkcia | Popis |
|---------|-------|
| **Profesia.sk** | IT ponuky v Bratislavskom kraji od 2000 €/mes.; stránkovanie, detail ponuky pre plat a presný dátum |
| **LinkedIn** | Verejné vyhľadávanie ponúk (bez prihlásenia) v Bratislave za posledné 3 dni, viac kľúčových slov |
| **Filtrovanie** | Kľúčové slová v názve alebo texte ponuky + vyraďovacie slová v názve (stáž, sales, marketing…) |
| **Deduplikácia** | Každá ponuka sa nahlási len raz; odmietnuté ponuky sa pamätajú, aby sa ich detail nesťahoval znova |
| **Denný report** | E-mail o 08:00 zoskupený podľa zdroja; prehľad aj na stránke behu v GitHube |
| **Uložené ponuky** | `ponuky.txt` so všetkými neoslovenými ponukami — artefakt každého behu |
| **Lokálne použitie** | Otvorenie ponúk v prehliadači, označovanie oslovených firiem |

## Ako to beží na serveri

Workflow [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml) na GitHub Actions (zadarmo):

1. **Každý deň o 08:00** bratislavského času (GitHub cron beží v UTC, preto sú v ňom dva časy
   a krok `gate` vyberie ten správny podľa letného/zimného času; GitHub môže štart oneskoriť
   o pár minút).
2. Obnoví databázu ponúk z **cache** (dedup medzi dňami).
3. Spustí `py_search.py` (Profesia) a `linkedin_search.py` (LinkedIn).
4. Uloží `ponuky.txt` ako **artefakt** a pošle **e-mail** (`report_email.py`).

Spustiť sa dá aj ručne: **Actions → Scrape jobs → Run workflow**, a automaticky beží aj po
každom pushi zmeny scrapera.

### Kde nájdem ponuky
- **E-mail** — každé ráno nové ponuky (ak nejaké pribudli)
- **GitHub → Actions → posledný beh → Summary** — tabuľka nových ponúk s odkazmi
- **Artifacts → `ponuky`** na tej istej stránke — `ponuky.txt` so všetkými ponukami (30 dní)
- **Profesia** — kompletne cez jej vlastné e-mailové upozornenie (server Profesia blokuje, viď Poznámky)

### Nastavenie e-mailu (GitHub Secrets)
V repozitári **Settings → Secrets and variables → Actions** tri secrety:

| Secret | Hodnota |
|--------|---------|
| `SMTP_USER` | Gmail adresa, z ktorej sa posiela |
| `SMTP_PASS` | Gmail [App Password](https://myaccount.google.com/apppasswords) (16 znakov, bez medzier) |
| `MAIL_TO` | kam má report prísť |

## Databáza

SQLite `profesia_jobs.db` — tabuľka `jobs` (oba zdroje, stĺpec `source`, čas nájdenia
`found_at`, príznak `contacted`) a `seen_links` (ponuky, ktoré neprešli filtrom).

Na serveri sa DB prenáša medzi behmi cez **GitHub Actions cache** — nie je vo verejnom repe.
- **Prvý beh** (prázdna cache) pošle všetky aktuálne ponuky naraz, potom už len prírastky.
- Keby workflow 7+ dní nebežal, GitHub cache zmaže a ďalší beh začne od nuly.

## Lokálne použitie

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # Windows

.venv\Scripts\python py_search.py        # Profesia.sk → DB + ponuky.txt
.venv\Scripts\python linkedin_search.py  # LinkedIn → DB + ponuky.txt
.venv\Scripts\python py_search.py mark   # označ ponuku ako oslovenú
.venv\Scripts\python open_new_jobs.py    # otvor neoslovené ponuky v prehliadači
```

Na Windows stačí dvojklik na `start.bat` (oba scrapery) alebo `open_new_jobs.bat`.
Pre lokálne posielanie reportu skopíruj `.env.example` na `.env` a doplň SMTP údaje.

## Nastavenia

| Čo | Kde |
|----|-----|
| Kľúčové a vyraďovacie slová | `KEYWORDS`, `BLACKLIST` v [`common.py`](common.py) |
| Profesia — kraj, kategória, plat | `BASE_URL` v [`py_search.py`](py_search.py) |
| LinkedIn — hľadané výrazy, oblasť, obdobie | `SEARCH_KEYWORDS`, `GEO_ID`, `TIME_RANGE` v [`linkedin_search.py`](linkedin_search.py) |
| Čas denného behu | `cron` v [`scrape.yml`](.github/workflows/scrape.yml) |

Po zmene filtrov sa už odmietnuté ponuky znova nevyhodnocujú — ak ich chceš preveriť
nanovo, vymaž tabuľku `seen_links`.

## Štruktúra

```
py_profesia/
├── py_search.py          # scraper Profesia.sk (+ `mark` na označenie oslovených)
├── linkedin_search.py    # scraper LinkedIn (verejné vyhľadávanie)
├── common.py             # DB, HTTP s opakovaním, filtre, výstupy (ponuky.txt, new_jobs.json)
├── report_email.py       # e-mailový report + súhrn na stránke behu
├── open_new_jobs.py      # otvorí neoslovené ponuky v prehliadači a označí ich
├── start.bat / open_new_jobs.bat
├── .github/workflows/scrape.yml
├── requirements.txt
└── .env.example
```

## Poznámky

- **LinkedIn bez prihlásenia** — scraper nepoužíva `li_at` cookie ani Selenium; prihlásená
  session zo serverovej IP by riskovala zablokovanie LinkedIn účtu.
- **Diagnostika** — každý beh zapíše počty (strany, ponuky, chyby HTTP) ako anotácie na
  stránku behu; ak by portál server blokoval, je to vidno tam.
- **Profesia a server** — Profesia chráni web proti botom (AWS WAF za CloudFront): z IP adries
  GitHubu prejde len prvá strana a pár detailov, potom vracia HTTP 202 (challenge). Scraper sa
  vtedy slušne zastaví, neopakuje požiadavky a zapíše varovanie. Plný zoznam z Profesie funguje
  pri lokálnom spustení (bežná IP); LinkedIn funguje aj zo servera.
  **Úplný denný prehľad z Profesie** preto zabezpečuje jej oficiálne e-mailové upozornenie:
  na [stránke s filtrom](https://www.profesia.sk/praca/bratislavsky-kraj/informacne-technologie/?salary=2000&salary_period=m)
  tlačidlo **Posielať najnovšie ponuky** (správa upozornení: [profesia.sk/agent](https://www.profesia.sk/agent/)).
- **Tajomstvá** sú len v GitHub Secrets / lokálnom `.env` (mimo gitu).
- Scraping rešpektuje pauzy medzi požiadavkami. Použitie je na vlastnú zodpovednosť
  v súlade s podmienkami daných portálov.
- **História:** pôvodne bežal na AWS (Lambda + EventBridge + SES, dáta v DynamoDB);
  AWS účet bol v 09/2026 zrušený, preto presun na GitHub Actions.
