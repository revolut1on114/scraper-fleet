# scraper-fleet

Маленький scraping-pipeline на **Crawl4AI + Docker Compose**, який виростає з одного `worker-html` (basic) до «флоту» з чергами, scheduler-ом і моніторингом (advanced).

| Рівень | Що всередині |
|---|---|
| **Basic** | 1 сайт ([books.toscrape.com](https://books.toscrape.com)), 15 сторінок, 1 `worker-html`, raw + normalized JSON, JSON-логи |
| **Advanced** | Celery: дві черги (`html`, `js`), list/detail-задачі, `worker-js` для [quotes.toscrape.com/js](https://quotes.toscrape.com/js/), Celery beat, structured extraction, Prometheus + Grafana, `CLAUDE.md`, prompt для Claude Code |

Обидва сайти — офіційні «пісочниці» для навчання скрейпінгу, тож збір із них легальний і нікому не шкодить.

---

## Basic: швидкий старт

Потрібні Docker і Docker Compose v2.

```bash
git clone <your-repo-url> scraper-fleet && cd scraper-fleet
docker compose --profile basic up --build
```

Що відбудеться:

1. `worker-html` відкриває головну сторінку каталогу (list page);
2. витягує посилання на книжки й обходить 14 detail-сторінок (разом 15);
3. на кожну сторінку пише два файли:
   - `data/raw/books.toscrape.com/<id>.json` — сирий HTML + метадані запиту;
   - `data/normalized/books.toscrape.com/<id>.json` — нормалізований запис;
4. наприкінці друкує підсумок і зберігає його в `data/run_summary.json`.

На Windows те саме подвійним кліком: `scripts\run-basic.bat` (є також `run-advanced.bat`, `test.bat`, `stop.bat`, `setup-venv.ps1`).

Без Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m app.run_basic
```

### Формат normalized JSON

Обов'язкові поля з завдання — `url`, `title`, `fetched_at`, `source`, `content` (Markdown від Crawl4AI), `links`. Решта — розширення для advanced.

```json
{
  "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
  "title": "A Light in the Attic",
  "fetched_at": "2026-10-07T08:30:26+00:00",
  "source": "books.toscrape.com",
  "content": "[Books to Scrape](https://books.toscrape.com/index.html) We love being scraped! ...",
  "links": ["https://books.toscrape.com/index.html", "..."],
  "page_type": "books_detail",
  "worker": "worker-html",
  "parser_version": "1.0.0",
  "valid": true,
  "validation_errors": [],
  "data": {
    "title": "A Light in the Attic",
    "price_gbp": 51.77,
    "in_stock": true,
    "stock_qty": 22,
    "rating": 3,
    "category": "Poetry",
    "upc": "a897fe39b1053632",
    "num_reviews": 0,
    "description": "It's hard to imagine a world without A Light in the Attic...",
    "image_url": "https://books.toscrape.com/media/cache/fe/72/....jpg"
  }
}
```

Raw-файл містить `url`, `fetched_at`, `source`, `worker`, `page_type`, `status_code`, `ok`, `error`, `duration_ms`, `html`.

### Логи

Кожен рядок — JSON, тож їх зручно фільтрувати:

```bash
docker compose logs scraper-basic | grep '"level": "WARNING"'
docker compose logs scraper-basic --no-log-prefix | grep '^{' | jq -r 'select(.status) | [.status, .url] | @tsv'
```

`LOG_FORMAT=text` перемикає на звичайний текст.

### Коли знадобився б worker-js

`worker-html` робить звичайний HTTP-запит і бачить лише той HTML, який повернув сервер. Цього достатньо для books.toscrape.com: усі дані вже є в розмітці.

Окремий `worker-js` (headless Chromium через Playwright) потрібен, коли контент з'являється в DOM **тільки після виконання JavaScript**:

- SPA на React/Vue/Angular, де сервер віддає порожній `<div id="root">`;
- дані вставляються скриптом із вбудованого JSON або підвантажуються через XHR/fetch;
- нескінченний скрол, кнопка «Показати ще», ліниве завантаження;
- контент за cookie-банером або після кліку.

Ознака: у браузері дані видно, а у «View Source» / `curl` — ні. Наприклад, у сирому HTML quotes.toscrape.com/js немає жодного `<div class="quote">` — цитати лежать у JS-масиві (див. `tests/fixtures/quotes_js_raw.html`). Браузер дорожчий у 10–50 разів за CPU/RAM і повільніший, тому його виносять в окремий воркер з окремою чергою, а простий HTML збирають дешевим `worker-html`. В advanced-рівні саме так і зроблено.

### Налаштування

Усі параметри — env-змінні (див. `.env.example`): `MAX_PAGES` (15), `LIST_PAGES` (1), `REQUEST_DELAY_MS` (500), `BOOKS_BASE_URL`, `LOG_LEVEL`, `LOG_FORMAT`. Скопіюйте `.env.example` у `.env`, щоб змінити.

---

## Advanced: «флот»

```bash
docker compose --profile advanced up -d --build
docker compose exec worker-html python -m app.enqueue all   # не чекати першого спрацювання beat
docker compose logs -f worker-html worker-js
```

| Сервіс | Роль |
|---|---|
| `redis` | брокер Celery |
| `worker-html` | черга `html`: `books.crawl_list` (list page) і `books.crawl_detail` (detail page), Crawl4AI HTTP-стратегія без браузера |
| `worker-js` | черга `js`: `quotes.crawl_js`, Crawl4AI + Chromium, `wait_for="css:div.quote"` |
| `beat` | scheduler: каталог кожні 30 хв, JS-сторінки кожну годину |
| `prometheus` | <http://localhost:9090> — збирає `/metrics` з воркерів |
| `grafana` | <http://localhost:3000> (admin / admin) — дашборд **Scraper fleet** |

Масштабування: `docker compose --profile advanced up -d --scale worker-html=3`. Prometheus знайде всі репліки через DNS.

### Structured extraction

CSS-схеми для `JsonCssExtractionStrategy` з Crawl4AI лежать у `app/parsers/`:

- `books.py` — list page (картки + пагінація) і detail page (ціна, наявність, рейтинг, UPC, категорія, опис, зображення), плюс приведення типів і `validate_*()`;
- `quotes_js.py` — цитати, автори, теги.

Якщо валідація не проходить, запис однаково зберігається з `"valid": false` і списком `validation_errors`, а метрика `scraper_validation_errors_total` зростає. Так зміна DOM видно одразу, а не через тиждень.

### Метрики

| Метрика | Що показує |
|---|---|
| `scraper_pages_total{worker,source,page_type,status}` | сторінки за статусом: `ok`, `fetch_error`, `parse_error`, `validation_error` |
| `scraper_fetch_seconds` | гістограма часу завантаження |
| `scraper_items_extracted_total` | кількість витягнутих книжок/цитат |
| `scraper_validation_errors_total` | порушення контракту даних |
| `scraper_last_success_timestamp_seconds` | коли востаннє була успішна сторінка |

Success rate = `sum(increase(scraper_pages_total{status="ok"}[1h])) / sum(increase(scraper_pages_total[1h]))`. Алерти — у `monitoring/alerts.yml`.

### Документація

- [docs/architecture.md](docs/architecture.md) — схема архітектури
- [docs/runbook.md](docs/runbook.md) — як перевірити, що парсер працює
- [docs/ai-workflow.md](docs/ai-workflow.md) — приклад AI-assisted workflow з Claude Code
- [CLAUDE.md](CLAUDE.md) — контекст проєкту для Claude Code
- [.claude/commands/check-parser.md](.claude/commands/check-parser.md) — prompt «перевір, чи не зламався парсер після зміни DOM»

---

## Тести

```bash
pytest -q                               # парсери на HTML-фікстурах, офлайн
python -m app.check_parser --fixtures   # те саме як smoke-check, з JSON-звітом
python -m app.check_parser --no-js      # live-перевірка books.toscrape.com
python -m app.check_parser              # live + JS-сторінка (потрібен Chromium)
```

У Docker: `docker compose --profile basic run --rm scraper-basic pytest -q`.

## Структура

```
app/
  config.py         налаштування з env
  logging_setup.py  JSON-логи
  crawler.py        Crawl4AI: fetch_html (HTTP) і fetch_js (Chromium)
  parsers/          CSS-схеми + типи + валідація
  pipeline.py       extract -> validate -> save raw/normalized -> metrics -> log
  storage.py        атомарний запис JSON
  metrics.py        Prometheus
  run_basic.py      BASIC: один прогін worker-html
  celery_app.py     ADVANCED: черги, beat schedule
  tasks.py          ADVANCED: list/detail/js таски
  enqueue.py        ручний запуск задач
  check_parser.py   smoke-check парсера
tests/              pytest + HTML-фікстури
monitoring/         Prometheus, алерти, Grafana provisioning + дашборд
data/raw/           сирі відповіді
data/normalized/    нормалізовані записи
docs/               архітектура, runbook, AI-workflow, скриншоти
scripts/            .bat/.ps1 для запуску на Windows
```

## Що здати (чеклист)

- [ ] `docker compose --profile basic up --build` — зробити скриншот у `docs/screenshots/basic-run.png`
- [ ] закомітити `data/raw/` і `data/normalized/` після реального прогону (це і є 2–3+ приклади JSON)
- [ ] advanced: скриншот Grafana у `docs/screenshots/grafana.png`
- [ ] запушити в GitHub
