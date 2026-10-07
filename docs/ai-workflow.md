# AI-assisted workflow: «парсер зламався після зміни DOM»

## Навіщо

Найчастіша поломка скрейпера — сайт змінив розмітку. Код не падає, але поле тихо стає `null`. Тут цей сценарій закритий трьома шарами:

1. **Виявлення** — `validate_*()` + метрика `scraper_validation_errors_total` + алерт `ScraperValidationErrors`.
2. **Діагностика** — `python -m app.check_parser` показує, яке саме поле зламалося (`fill` < 1.0).
3. **Виправлення** — Claude Code з prompt-ом `.claude/commands/check-parser.md` і контекстом із `CLAUDE.md`.

## Prompt

Збережений як slash-команда в `.claude/commands/check-parser.md`. Запуск у корені репо:

```
claude
> /check-parser books
```

Або одноразово, без інтерактиву:

```bash
claude -p "/check-parser books"
```

## Приклад: що відбувається

Сценарій відтворено локально: на тестовій копії сайту клас ціни на detail-сторінці перейменовано з `price_color` на `price-now`.

**1. Grafana / алерт.** Success rate по `books_detail` падає, ростуть `validation_error`.

**2. Claude Code запускає перевірку** (крок 1 prompt-а) і отримує:

```json
{
  "check": "books_detail",
  "found": 1,
  "fill": { "price_gbp": 0.0, "title": 1.0, "upc": 1.0, "rating": 1.0, "...": 1.0 },
  "errors": ["missing:price_gbp"]
}
```

Висновок: сторінка завантажилась, усе інше парситься, зламана лише ціна.

**3. Діагностика.** Claude відкриває свіжий `data/raw/books.toscrape.com/<id>.json` і порівнює з `tests/fixtures/book_detail.html`:

```diff
- <p class="price_color">£51.77</p>
+ <p class="price-now">£51.77</p>
```

**4. Мінімальне виправлення** в `app/parsers/books.py`. CSS-список селекторів підтримує обидві версії розмітки:

```diff
- {"name": "price", "selector": "div.product_main p.price_color", "type": "text"},
+ {"name": "price", "selector": "div.product_main p.price_color, div.product_main p.price-now", "type": "text"},
```

**5. Регресійний тест.** Новий HTML зберігається як `tests/fixtures/book_detail_v2.html`, додається тест:

```python
def test_detail_price_after_class_rename():
    data = books.extract_detail(read("book_detail_v2.html"), DETAIL_URL)
    assert data["price_gbp"] == 51.77
```

**6. Перевірка:** `pytest -q` і `python -m app.check_parser --fixtures` зелені, `PARSER_VERSION` 1.0.0 → 1.0.1.

**7. Людина** переглядає diff і комітить. Prompt явно забороняє Claude комітити самостійно.

## Чому це працює

- `CLAUDE.md` дає Claude карту проєкту й правила: не ламати контракт JSON, завжди додавати фікстуру, піднімати версію парсера.
- `check_parser` повертає машиночитаний JSON і exit code, тож агент перевіряє себе тими ж інструментами, що й людина.
- Raw HTML зберігається завжди, тож «як виглядала сторінка, коли зламалося» вже лежить на диску.

## Варіанти розвитку

- Запускати `python -m app.check_parser --no-js` за розкладом у CI, а при `exit 1` — `claude -p "/check-parser all"` і відкривати PR.
- Subagent `parser-doctor` (`.claude/agents/`) з доступом лише до `app/parsers/`, `tests/` і `data/raw/`.
