"""Smoke-check парсера: «чи не зламався він після зміни DOM?»

    python -m app.check_parser              # live: 1 list + 1 detail (HTML) + 1 JS-сторінка
    python -m app.check_parser --no-js      # без браузера
    python -m app.check_parser --fixtures   # офлайн, на збережених фікстурах (tests/fixtures)

Exit code 0 — усе гаразд, 1 — є проблеми (зручно для CI / cron / Claude Code).
Для кожної сторінки друкує: скільки елементів знайдено, заповненість полів, помилки валідації.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.config import settings
from app.parsers import books, quotes_js

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _fill_ratio(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Частка непорожніх значень по кожному полю: різке падіння = селектор «поїхав»."""
    if not rows:
        return {}
    keys = sorted({k for r in rows for k in r})
    return {k: round(sum(r.get(k) not in (None, "", []) for r in rows) / len(rows), 2) for k in keys}


def check_list(html: str, url: str) -> dict[str, Any]:
    data = books.extract_list(html, url)
    return {"check": "books_list", "url": url, "found": len(data["books"]), "fill": _fill_ratio(data["books"]),
            "next_url": data["next_url"], "errors": books.validate_list(data), "_data": data}


def check_detail(html: str, url: str) -> dict[str, Any]:
    data = books.extract_detail(html, url)
    return {"check": "books_detail", "url": url, "found": 1 if data.get("title") else 0, "fill": _fill_ratio([data]),
            "errors": books.validate_detail(data)}


def check_quotes(html: str, url: str) -> dict[str, Any]:
    data = quotes_js.extract_quotes(html, url)
    return {"check": "quotes_js", "url": url, "found": len(data["quotes"]), "fill": _fill_ratio(data["quotes"]),
            "errors": quotes_js.validate_quotes(data)}


def run_fixtures() -> list[dict[str, Any]]:
    base = "https://books.toscrape.com/"
    return [
        check_list((FIXTURES / "book_list.html").read_text(encoding="utf-8"), base + "index.html"),
        check_detail((FIXTURES / "book_detail.html").read_text(encoding="utf-8"),
                     base + "catalogue/a-light-in-the-attic_1000/index.html"),
        check_quotes((FIXTURES / "quotes_js_rendered.html").read_text(encoding="utf-8"), settings.quotes_js_url),
    ]


async def run_live(with_js: bool) -> list[dict[str, Any]]:
    from app.crawler import fetch_html, fetch_js

    report: list[dict[str, Any]] = []
    [lst] = await fetch_html([settings.books_base_url])
    if not lst.ok:
        return [{"check": "books_list", "url": lst.url, "found": 0, "errors": [f"fetch:{lst.error}"]}]
    lr = check_list(lst.html, lst.url)
    report.append(lr)

    first = next((b["url"] for b in lr["_data"]["books"] if b.get("url")), None)
    if first:
        [det] = await fetch_html([first])
        report.append(check_detail(det.html, det.url) if det.ok
                      else {"check": "books_detail", "url": first, "found": 0, "errors": [f"fetch:{det.error}"]})

    if with_js:
        js = await fetch_js(settings.quotes_js_url, wait_for=quotes_js.WAIT_FOR)
        report.append(check_quotes(js.html, js.url) if js.ok
                      else {"check": "quotes_js", "url": js.url, "found": 0, "errors": [f"fetch:{js.error}"]})
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures", action="store_true", help="офлайн-перевірка на tests/fixtures")
    ap.add_argument("--no-js", action="store_true", help="не запускати браузер (без worker-js)")
    args = ap.parse_args()

    report = run_fixtures() if args.fixtures else asyncio.run(run_live(with_js=not args.no_js))
    for r in report:
        r.pop("_data", None)
    failed = [r for r in report if r.get("errors") or not r.get("found")]

    print(json.dumps({"mode": "fixtures" if args.fixtures else "live", "ok": not failed, "checks": report},
                     ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
