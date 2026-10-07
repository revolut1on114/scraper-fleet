# Runbook: як перевірити, що парсер працює

## 1. Швидка перевірка (1 хвилина)

```bash
python -m app.check_parser --no-js
# або в Docker:
docker compose --profile advanced exec worker-html python -m app.check_parser --no-js
docker compose --profile advanced exec worker-js   python -m app.check_parser
```

Що дивитися у звіті:

| Поле | Норма | Якщо ні |
|---|---|---|
| `"ok"` | `true` | є проблема, дивись далі |
| `found` для `books_list` | 20 | 0 = змінився `article.product_pod` або сайт недоступний |
| `found` для `quotes_js` | 10 | 0 = JS не відрендерився (таймаут, `wait_for`) або змінився `div.quote` |
| `fill.<поле>` | 1.0 | < 1.0 = селектор цього поля «поїхав» |
| `errors` | `[]` | `fetch:...` = мережа/сайт; `missing:...` = селектор |

Exit code: `0` — усе гаразд, `1` — проблеми. Тому команду можна ставити в cron або CI.

## 2. Офлайн-регресія

```bash
pytest -q
python -m app.check_parser --fixtures
```

Якщо падає офлайн, проблема в коді, а не на сайті.

## 3. Перевірка результатів прогону

```bash
cat data/run_summary.json                          # basic: success_rate, failed_urls
ls data/normalized/books.toscrape.com | wc -l      # очікується 15
grep -l '"valid": false' data/normalized/*/*.json  # невалідні записи
```

## 4. Перевірка флоту (advanced)

```bash
docker compose --profile advanced ps                         # усі сервіси Up / healthy
docker compose exec worker-html celery -A app.celery_app inspect ping
docker compose exec worker-html celery -A app.celery_app inspect active_queues
docker compose exec redis redis-cli llen html                # довжина черги
docker compose logs --since 30m worker-html | grep '"level": "WARNING"'
curl -s localhost:9090/api/v1/query --data-urlencode \
  'query=sum(increase(scraper_pages_total{status="ok"}[1h]))/sum(increase(scraper_pages_total[1h]))'
```

Grafana → дашборд **Scraper fleet**: success rate ≥ 95%, «Від останнього успіху» менше за інтервал beat.

## 5. Типові поломки

| Симптом | Ймовірна причина | Дія |
|---|---|---|
| `fetch_error`, `HTTP 429/503` | сайт обмежує частоту | збільшити `REQUEST_DELAY_MS`, зменшити кількість реплік |
| `fetch_error` з `Timeout` у `worker-js` | `wait_for` не дочекався селектора | перевірити селектор у браузері; збільшити `PAGE_TIMEOUT_MS` |
| `validation_error: missing:<поле>` на всіх сторінках | змінився DOM | запустити `/check-parser` у Claude Code (див. `docs/ai-workflow.md`) |
| `validation_error` на поодиноких сторінках | на сайті справді немає поля | послабити правило у `validate_*()`, якщо це нормальна ситуація |
| `empty:quotes (JS not rendered?)` | сторінку забрали без JS | переконатися, що таск іде в чергу `js`, а не `html` |
| Chromium падає (`Target crashed`) | мало `/dev/shm` | `shm_size: 1gb` у compose (вже є) |
| `Permission denied` у `data/` | bind-mount належить іншому UID | `sudo chown -R 1000:1000 data` |
| Немає нових файлів, логи порожні | beat не працює або черга застрягла | `docker compose logs beat`; `python -m app.enqueue all` |

## 6. Ручний повторний прогін

```bash
docker compose --profile basic up --build              # basic
docker compose exec worker-html python -m app.enqueue books
docker compose exec worker-html python -m app.enqueue quotes
```
