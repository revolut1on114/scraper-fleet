"""Celery-таски.

books.crawl_list   (черга html) — list page каталогу -> ставить books.crawl_detail на кожну книжку
books.crawl_detail (черга html) — detail page книжки -> structured extraction
quotes.crawl_js    (черга js)   — JS-сторінка цитат (Playwright) -> наступна сторінка окремим таском
"""

from __future__ import annotations

import asyncio
import logging

from app.celery_app import app
from app.config import settings
from app.crawler import fetch_html, fetch_js
from app.parsers import quotes_js
from app.pipeline import process

log = logging.getLogger(__name__)


class TransientFetchError(Exception):
    """Мережевий збій — варто повторити."""


@app.task(name="books.crawl_list", bind=True, autoretry_for=(TransientFetchError,),
          retry_backoff=True, retry_backoff_max=300, max_retries=3)
def crawl_list(self, url: str | None = None, pages_left: int | None = None, detail_budget: int | None = None):
    url = url or settings.books_base_url
    pages_left = settings.list_pages if pages_left is None else pages_left
    detail_budget = max(0, settings.max_pages - 1) if detail_budget is None else detail_budget

    [fetch] = asyncio.run(fetch_html([url]))
    out = process(fetch, "books_list", "worker-html")
    if out.status == "fetch_error":
        raise TransientFetchError(out.errors[0] if out.errors else url)

    detail_urls = [b["url"] for b in out.data.get("books", []) if b.get("url")][:detail_budget]
    for i, detail_url in enumerate(detail_urls):
        # countdown розносить запити в часі — ввічливо до сайту навіть при кількох воркерах
        crawl_detail.apply_async(args=[detail_url], countdown=i * settings.request_delay_ms / 1000)

    next_url = out.data.get("next_url")
    remaining_budget = detail_budget - len(detail_urls)
    if next_url and pages_left > 1 and remaining_budget > 0:
        crawl_list.apply_async(kwargs={"url": next_url, "pages_left": pages_left - 1, "detail_budget": remaining_budget},
                               countdown=2)
    log.info("list processed", extra={"url": url, "items": len(detail_urls), "status": out.status,
                                      "task_id": self.request.id})
    return {"url": url, "status": out.status, "queued_details": len(detail_urls)}


@app.task(name="books.crawl_detail", bind=True, autoretry_for=(TransientFetchError,),
          retry_backoff=True, retry_backoff_max=300, max_retries=3, rate_limit="30/m")
def crawl_detail(self, url: str):
    [fetch] = asyncio.run(fetch_html([url]))
    out = process(fetch, "books_detail", "worker-html")
    if out.status == "fetch_error":
        raise TransientFetchError(out.errors[0] if out.errors else url)
    return {"url": url, "status": out.status, "errors": out.errors}


@app.task(name="quotes.crawl_js", bind=True, autoretry_for=(TransientFetchError,),
          retry_backoff=True, retry_backoff_max=300, max_retries=2)
def crawl_js(self, url: str | None = None, pages_left: int | None = None):
    url = url or settings.quotes_js_url
    pages_left = settings.js_pages if pages_left is None else pages_left

    fetch = asyncio.run(fetch_js(url, wait_for=quotes_js.WAIT_FOR))
    out = process(fetch, "quotes_js", "worker-js")
    if out.status == "fetch_error":
        raise TransientFetchError(out.errors[0] if out.errors else url)

    next_url = out.data.get("next_url")
    if next_url and pages_left > 1:
        crawl_js.apply_async(kwargs={"url": next_url, "pages_left": pages_left - 1}, countdown=2)
    return {"url": url, "status": out.status, "quotes": len(out.data.get("quotes", []))}
