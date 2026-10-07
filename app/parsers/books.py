"""Парсер books.toscrape.com — звичайний HTML (worker-html).

Дві задачі:
  * list page   — сторінка каталогу: картки книжок + посилання на наступну сторінку;
  * detail page — сторінка книжки: structured extraction (ціна, наявність, рейтинг, UPC...).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from crawl4ai import JsonCssExtractionStrategy

SOURCE = "books.toscrape.com"

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

# ---------------------------------------------------------------- CSS-схеми

LIST_SCHEMA: dict[str, Any] = {
    "name": "BookCards",
    "baseSelector": "article.product_pod",
    "fields": [
        {"name": "title", "selector": "h3 a", "type": "attribute", "attribute": "title"},
        {"name": "href", "selector": "h3 a", "type": "attribute", "attribute": "href"},
        {"name": "price", "selector": "p.price_color", "type": "text"},
        {"name": "rating_class", "selector": "p.star-rating", "type": "attribute", "attribute": "class"},
        {"name": "availability", "selector": "p.instock.availability", "type": "text"},
    ],
}

NEXT_PAGE_SCHEMA: dict[str, Any] = {
    "name": "Pager",
    "baseSelector": "ul.pager",
    "fields": [
        {"name": "next", "selector": "li.next a", "type": "attribute", "attribute": "href"},
        {"name": "current", "selector": "li.current", "type": "text"},
    ],
}

DETAIL_SCHEMA: dict[str, Any] = {
    "name": "BookDetail",
    "baseSelector": "article.product_page",
    "fields": [
        {"name": "title", "selector": "div.product_main h1", "type": "text"},
        {"name": "price", "selector": "div.product_main p.price_color", "type": "text"},
        {"name": "availability", "selector": "div.product_main p.availability", "type": "text"},
        {"name": "rating_class", "selector": "div.product_main p.star-rating", "type": "attribute", "attribute": "class"},
        {"name": "description", "selector": "#product_description + p", "type": "text"},
        {"name": "image", "selector": "#product_gallery img", "type": "attribute", "attribute": "src"},
        {
            "name": "info",
            "selector": "table.table-striped tr",
            "type": "list",
            "fields": [
                {"name": "key", "selector": "th", "type": "text"},
                {"name": "value", "selector": "td", "type": "text"},
            ],
        },
    ],
}

# Breadcrumb окремо: категорія — передостанній пункт.
BREADCRUMB_SCHEMA: dict[str, Any] = {
    "name": "Breadcrumb",
    "baseSelector": "ul.breadcrumb li",
    "fields": [{"name": "text", "selector": "a", "type": "text"}],
}

# ------------------------------------------------------------- хелпери типів


def parse_price(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_rating(class_attr: Any) -> int | None:
    """class="star-rating Three" -> 3. BeautifulSoup може повернути class як список."""
    if not class_attr:
        return None
    words = class_attr.split() if isinstance(class_attr, str) else [str(w) for w in class_attr]
    for word in words:
        if word in RATING_WORDS:
            return RATING_WORDS[word]
    return None


def parse_stock(text: str | None) -> tuple[bool | None, int | None]:
    """'In stock (22 available)' -> (True, 22)."""
    if not text:
        return None, None
    text = " ".join(text.split())
    in_stock = text.lower().startswith("in stock")
    m = re.search(r"\((\d+)\s+available\)", text)
    return in_stock, (int(m.group(1)) if m else None)


def _clean(text: str | None) -> str | None:
    return " ".join(text.split()) if text else None


# ------------------------------------------------------------------ extract


def extract_list(html: str, url: str) -> dict[str, Any]:
    """List page -> {'books': [...], 'next_url': str|None}."""
    cards = JsonCssExtractionStrategy(LIST_SCHEMA).extract(url, html)
    books = []
    for c in cards:
        in_stock, _ = parse_stock(c.get("availability"))
        books.append(
            {
                "title": _clean(c.get("title")),
                "url": urljoin(url, c["href"]) if c.get("href") else None,
                "price_gbp": parse_price(c.get("price")),
                "rating": parse_rating(c.get("rating_class")),
                "in_stock": in_stock,
            }
        )
    pager = JsonCssExtractionStrategy(NEXT_PAGE_SCHEMA).extract(url, html)
    next_href = pager[0].get("next") if pager else None
    return {
        "books": books,
        "next_url": urljoin(url, next_href) if next_href else None,
        "page_label": _clean(pager[0].get("current")) if pager else None,
    }


def extract_detail(html: str, url: str) -> dict[str, Any]:
    """Detail page -> плоский dict з типізованими полями."""
    rows = JsonCssExtractionStrategy(DETAIL_SCHEMA).extract(url, html)
    raw = rows[0] if rows else {}
    info = {_clean(r.get("key")): _clean(r.get("value")) for r in raw.get("info", []) if r.get("key")}

    crumbs = [_clean(c.get("text")) for c in JsonCssExtractionStrategy(BREADCRUMB_SCHEMA).extract(url, html)]
    crumbs = [c for c in crumbs if c]
    category = crumbs[-1] if len(crumbs) >= 3 else None  # Home > Books > <Category> > (title без <a>)

    in_stock, qty = parse_stock(raw.get("availability"))
    return {
        "title": _clean(raw.get("title")),
        "price_gbp": parse_price(raw.get("price")),
        "in_stock": in_stock,
        "stock_qty": qty,
        "rating": parse_rating(raw.get("rating_class")),
        "category": category,
        "upc": info.get("UPC"),
        "product_type": info.get("Product Type"),
        "num_reviews": int(info["Number of reviews"]) if (info.get("Number of reviews") or "").isdigit() else None,
        "description": _clean(raw.get("description")),
        "image_url": urljoin(url, raw["image"]) if raw.get("image") else None,
    }


# ---------------------------------------------------------------- validate

DETAIL_REQUIRED = ("title", "price_gbp", "upc", "rating", "in_stock")


def validate_detail(data: dict[str, Any]) -> list[str]:
    errors = [f"missing:{f}" for f in DETAIL_REQUIRED if data.get(f) in (None, "")]
    if data.get("upc") and not re.fullmatch(r"[0-9a-f]{16}", data["upc"]):
        errors.append("bad_format:upc")
    if data.get("rating") is not None and not 1 <= data["rating"] <= 5:
        errors.append("out_of_range:rating")
    if data.get("price_gbp") is not None and data["price_gbp"] <= 0:
        errors.append("out_of_range:price_gbp")
    return errors


def validate_list(data: dict[str, Any]) -> list[str]:
    errors = []
    if not data.get("books"):
        errors.append("empty:books")
    for i, b in enumerate(data.get("books", [])):
        for f in ("title", "url", "price_gbp"):
            if b.get(f) in (None, ""):
                errors.append(f"missing:books[{i}].{f}")
    return errors


def is_detail_url(url: str) -> bool:
    return "/catalogue/" in url and url.endswith("/index.html") and "/category/" not in url
