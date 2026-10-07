"""Парсер quotes.toscrape.com/js/ — контент з'являється ЛИШЕ після виконання JavaScript (worker-js).

У сирому HTML цієї сторінки немає жодного <div class="quote">: цитати лежать у JS-масиві
й вставляються в DOM скриптом. Тому worker-html тут поверне 0 елементів, а worker-js
(Crawl4AI + Playwright, wait_for="css:div.quote") — повний список.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from crawl4ai import JsonCssExtractionStrategy

SOURCE = "quotes.toscrape.com"

# Чекати, поки JS намалює цитати (Crawl4AI wait_for)
WAIT_FOR = "css:div.quote"

QUOTES_SCHEMA: dict[str, Any] = {
    "name": "Quotes",
    "baseSelector": "div.quote",
    "fields": [
        {"name": "text", "selector": "span.text", "type": "text"},
        {"name": "author", "selector": "small.author", "type": "text"},
        {"name": "tags", "selector": "div.tags a.tag", "type": "list", "fields": [{"name": "tag", "type": "text"}]},
    ],
}

PAGER_SCHEMA: dict[str, Any] = {
    "name": "Pager",
    "baseSelector": "ul.pager",
    "fields": [{"name": "next", "selector": "li.next a", "type": "attribute", "attribute": "href"}],
}

_QUOTE_MARKS = "“”\"'"


def extract_quotes(html: str, url: str) -> dict[str, Any]:
    rows = JsonCssExtractionStrategy(QUOTES_SCHEMA).extract(url, html)
    quotes = []
    for r in rows:
        text = " ".join((r.get("text") or "").split()).strip(_QUOTE_MARKS)
        quotes.append(
            {
                "text": text or None,
                "author": (r.get("author") or "").strip() or None,
                "tags": [t["tag"].strip() for t in r.get("tags", []) if t.get("tag")],
            }
        )
    pager = JsonCssExtractionStrategy(PAGER_SCHEMA).extract(url, html)
    next_href = pager[0].get("next") if pager else None
    return {"quotes": quotes, "next_url": urljoin(url, next_href) if next_href else None}


def validate_quotes(data: dict[str, Any]) -> list[str]:
    errors = []
    if not data.get("quotes"):
        # Найчастіша причина — сторінку забрали без JS-рендерингу.
        errors.append("empty:quotes (JS not rendered?)")
    for i, q in enumerate(data.get("quotes", [])):
        if not q.get("text"):
            errors.append(f"missing:quotes[{i}].text")
        if not q.get("author"):
            errors.append(f"missing:quotes[{i}].author")
    return errors


def page_number(url: str) -> int:
    m = re.search(r"/page/(\d+)/?", url)
    return int(m.group(1)) if m else 1
