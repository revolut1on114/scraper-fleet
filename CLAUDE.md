# CLAUDE.md

Навчальний scraping-pipeline на Crawl4AI. Мова коментарів і документації — українська.

## Що де

- `app/parsers/books.py` — books.toscrape.com, звичайний HTML. CSS-схеми `LIST_SCHEMA`, `DETAIL_SCHEMA`, `BREADCRUMB_SCHEMA`, `NEXT_PAGE_SCHEMA`; хелпери `parse_price/parse_rating/parse_stock`; `validate_list/validate_detail`.
- `app/parsers/quotes_js.py` — quotes.toscrape.com/js, контент лише після JS. `QUOTES_SCHEMA`, `WAIT_FOR`.
- `app/pipeline.py` — `PAGE_TYPES` + `process()`: extract → validate → raw/normalized JSON → метрики → лог. Єдине місце, де формується normalized-запис.
- `app/crawler.py` — `fetch_html` (Crawl4AI `AsyncHTTPCrawlerStrategy`, без браузера) і `fetch_js` (Playwright, `wait_for`).
- `app/tasks.py` — Celery: `books.crawl_list` → `books.crawl_detail` (черга `html`), `quotes.crawl_js` (черга `js`).
- `tests/fixtures/*.html` — збережені сторінки; `tests/test_parsers.py` — тести на них.

## Команди

```bash
pytest -q                                # завжди після зміни парсера
python -m app.check_parser --fixtures    # офлайн smoke-check, exit 1 при проблемах
python -m app.check_parser --no-js       # live-перевірка HTML-сайту
python -m app.check_parser               # live + JS (потрібен Chromium)
python -m app.run_basic                  # повний basic-прогін (15 сторінок)
docker compose --profile advanced up -d --build
```

## Правила

- Контракт normalized JSON не ламати: поля `url, title, fetched_at, source, content, links` обов'язкові. Нові поля — тільки всередину `data` або поруч, не перейменовуючи старі.
- Змінив логіку парсера — підніми `PARSER_VERSION` у `app/parsers/__init__.py`.
- Змінив селектор — онови або додай фікстуру в `tests/fixtures/` і тест, який падав би на старому DOM.
- Відсутнє поле — це `None` + помилка у `validate_*()`, а не виняток. Парсер не повинен падати на частково зміненій сторінці.
- Ввічливість до сайту: не зменшуй `REQUEST_DELAY_MS` нижче 200 і не прибирай `rate_limit` у тасках.
- `data/` — результати прогонів; не редагуй їх вручну і не використовуй як фікстури без копіювання в `tests/fixtures/`.

## Діагностика зламаного парсера

1. `python -m app.check_parser --no-js` — дивись `found` і `fill`: поле з `fill` < 1.0 вказує на селектор, що «поїхав».
2. Візьми свіжий HTML з `data/raw/<source>/<id>.json` (поле `html`) і порівняй структуру з `tests/fixtures/`.
3. Виправ селектор у схемі, збережи новий HTML як фікстуру, додай тест, прожени `pytest -q`.
