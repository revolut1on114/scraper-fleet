"""Спільний крок обробки сторінки: extract -> validate -> raw/normalized JSON -> метрики -> лог.

Однаковий для basic-скрипта і для Celery-тасків, тож логіка не дублюється.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app import metrics, storage
from app.crawler import FetchResult
from app.parsers import PARSER_VERSION, books, quotes_js

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageType:
    source: str
    extract: Callable[[str, str], dict[str, Any]]
    validate: Callable[[dict[str, Any]], list[str]]
    count_items: Callable[[dict[str, Any]], int]


PAGE_TYPES: dict[str, PageType] = {
    "books_list": PageType(books.SOURCE, books.extract_list, books.validate_list, lambda d: len(d.get("books", []))),
    "books_detail": PageType(books.SOURCE, books.extract_detail, books.validate_detail, lambda d: 1 if d.get("title") else 0),
    "quotes_js": PageType(quotes_js.SOURCE, quotes_js.extract_quotes, quotes_js.validate_quotes, lambda d: len(d.get("quotes", []))),
}


@dataclass
class Outcome:
    url: str
    status: str  # ok | fetch_error | parse_error | validation_error
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    normalized_path: str | None = None


def build_raw(fetch: FetchResult, source: str, worker: str, page_type: str) -> dict[str, Any]:
    return {
        "url": fetch.url,
        "fetched_at": fetch.fetched_at,
        "source": source,
        "worker": worker,
        "page_type": page_type,
        "status_code": fetch.status_code,
        "ok": fetch.ok,
        "error": fetch.error,
        "duration_ms": fetch.duration_ms,
        "html": fetch.html,
    }


def build_normalized(
    fetch: FetchResult, source: str, worker: str, page_type: str, data: dict[str, Any], errors: list[str]
) -> dict[str, Any]:
    # Обов'язкові поля з ДЗ: url, title, fetched_at, source, content, links
    return {
        "url": fetch.url,
        "title": data.get("title") or fetch.title,
        "fetched_at": fetch.fetched_at,
        "source": source,
        "content": fetch.markdown,
        "links": fetch.links,
        # Розширення (advanced): тип сторінки, structured extraction, якість
        "page_type": page_type,
        "worker": worker,
        "parser_version": PARSER_VERSION,
        "valid": not errors,
        "validation_errors": errors,
        "data": data,
    }


def process(fetch: FetchResult, page_type: str, worker: str) -> Outcome:
    pt = PAGE_TYPES[page_type]
    labels = {"worker": worker, "source": pt.source, "page_type": page_type}
    metrics.FETCH_SECONDS.labels(worker=worker, source=pt.source).observe(fetch.duration_ms / 1000)

    if not fetch.ok:
        metrics.PAGES.labels(**labels, status="fetch_error").inc()
        log.warning("fetch failed", extra={**labels, "url": fetch.url, "status": "fetch_error",
                                           "error": fetch.error, "duration_ms": fetch.duration_ms})
        return Outcome(fetch.url, "fetch_error", errors=[fetch.error or "unknown"])

    storage.save_raw(build_raw(fetch, pt.source, worker, page_type))

    try:
        data = pt.extract(fetch.html, fetch.url)
    except Exception as exc:  # зламаний DOM / несподівана структура
        metrics.PAGES.labels(**labels, status="parse_error").inc()
        log.exception("parse failed", extra={**labels, "url": fetch.url, "status": "parse_error", "error": repr(exc)})
        return Outcome(fetch.url, "parse_error", errors=[repr(exc)])

    errors = pt.validate(data)
    record = build_normalized(fetch, pt.source, worker, page_type, data, errors)
    path = storage.save_normalized(record)

    items = pt.count_items(data)
    metrics.ITEMS.labels(source=pt.source, page_type=page_type).inc(items)
    status = "validation_error" if errors else "ok"
    metrics.PAGES.labels(**labels, status=status).inc()
    if errors:
        metrics.VALIDATION_ERRORS.labels(source=pt.source, page_type=page_type).inc(len(errors))
        log.warning("validation failed", extra={**labels, "url": fetch.url, "status": status,
                                                "error": ";".join(errors[:5]), "items": items})
    else:
        metrics.LAST_SUCCESS.labels(source=pt.source, page_type=page_type).set_to_current_time()
        log.info("page ok", extra={**labels, "url": fetch.url, "status": status, "items": items,
                                   "duration_ms": fetch.duration_ms, "path": str(path)})
    return Outcome(fetch.url, status, data=data, errors=errors, normalized_path=str(path))
