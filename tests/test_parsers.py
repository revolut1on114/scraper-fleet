"""Тести парсерів на збережених HTML-фікстурах (офлайн, без браузера)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.crawler import FetchResult
from app.parsers import books, quotes_js
from app.pipeline import build_normalized
from app.storage import page_id

FX = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/"
DETAIL_URL = BASE + "catalogue/a-light-in-the-attic_1000/index.html"


def read(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- books: list

def test_list_extracts_cards_and_absolute_urls():
    data = books.extract_list(read("book_list.html"), BASE + "index.html")
    assert len(data["books"]) == 3
    first = data["books"][0]
    assert first == {
        "title": "A Light in the Attic",  # повна назва з атрибута title, а не обрізаний текст
        "url": DETAIL_URL,
        "price_gbp": 51.77,
        "rating": 3,
        "in_stock": True,
    }
    assert data["next_url"] == BASE + "catalogue/page-2.html"
    assert books.validate_list(data) == []


# -------------------------------------------------------------- books: detail

def test_detail_structured_extraction():
    data = books.extract_detail(read("book_detail.html"), DETAIL_URL)
    assert data["title"] == "A Light in the Attic"
    assert data["price_gbp"] == 51.77
    assert data["in_stock"] is True and data["stock_qty"] == 22
    assert data["rating"] == 3
    assert data["category"] == "Poetry"
    assert data["upc"] == "a897fe39b1053632"
    assert data["num_reviews"] == 0
    assert data["description"].startswith("It's hard to imagine")
    assert data["image_url"] == BASE + "media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg"
    assert books.validate_detail(data) == []


def test_detail_dom_change_is_detected():
    """Імітуємо зміну DOM: перейменували клас ціни -> валідація має це зловити."""
    broken = read("book_detail.html").replace('class="price_color"', 'class="price-now"')
    data = books.extract_detail(broken, DETAIL_URL)
    assert data["price_gbp"] is None
    assert "missing:price_gbp" in books.validate_detail(data)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("£51.77", 51.77), ("Â£13.99", 13.99), ("", None), (None, None)],
)
def test_parse_price(text, expected):
    assert books.parse_price(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("In stock (22 available)", (True, 22)), ("\n  In stock \n", (True, None)), ("Out of stock", (False, None))],
)
def test_parse_stock(text, expected):
    assert books.parse_stock(text) == expected


def test_parse_rating_accepts_str_and_list():
    assert books.parse_rating("star-rating Four") == 4
    assert books.parse_rating(["star-rating", "Two"]) == 2
    assert books.parse_rating("star-rating") is None


# ------------------------------------------------------------------ quotes JS

def test_quotes_rendered_dom():
    data = quotes_js.extract_quotes(read("quotes_js_rendered.html"), "https://quotes.toscrape.com/js/")
    assert len(data["quotes"]) == 3
    assert data["quotes"][0]["author"] == "Albert Einstein"
    assert data["quotes"][0]["tags"] == ["change", "deep-thoughts", "thinking", "world"]
    assert not data["quotes"][0]["text"].startswith("“")  # лапки зняті
    assert data["next_url"] == "https://quotes.toscrape.com/js/page/2/"
    assert quotes_js.validate_quotes(data) == []


def test_quotes_raw_html_has_nothing_without_js():
    """Головний аргумент за worker-js: без рендерингу цитат у DOM немає."""
    data = quotes_js.extract_quotes(read("quotes_js_raw.html"), "https://quotes.toscrape.com/js/")
    assert data["quotes"] == []
    assert quotes_js.validate_quotes(data) == ["empty:quotes (JS not rendered?)"]


# ------------------------------------------------------- normalized contract

def test_normalized_record_has_required_fields():
    fetch = FetchResult(url=DETAIL_URL, ok=True, fetched_at="2026-10-07T08:00:00+00:00", status_code=200,
                        html=read("book_detail.html"), markdown="# A Light in the Attic", title="page title",
                        links=[BASE + "index.html"])
    data = books.extract_detail(fetch.html, fetch.url)
    rec = build_normalized(fetch, books.SOURCE, "worker-html", "books_detail", data, [])
    for key in ("url", "title", "fetched_at", "source", "content", "links"):
        assert key in rec
    assert rec["title"] == "A Light in the Attic"  # з structured data, а не з <title>
    assert rec["valid"] is True
    json.dumps(rec)  # серіалізується


def test_page_id_is_stable_and_readable():
    pid = page_id(DETAIL_URL)
    assert pid.startswith("catalogue-a-light-in-the-attic_1000-")
    assert pid == page_id(DETAIL_URL)
    assert page_id(BASE).startswith("root-")
