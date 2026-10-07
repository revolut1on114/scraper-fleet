"""Prometheus-метрики. Без запущеного HTTP-сервера лічильники просто живуть у пам'яті (basic-режим)."""

from __future__ import annotations

import logging

from prometheus_client import Counter, Gauge, Histogram, start_http_server

log = logging.getLogger(__name__)

PAGES = Counter(
    "scraper_pages_total",
    "Оброблені сторінки за результатом",
    ["worker", "source", "page_type", "status"],  # status: ok | fetch_error | validation_error | parse_error
)
FETCH_SECONDS = Histogram(
    "scraper_fetch_seconds",
    "Час завантаження сторінки",
    ["worker", "source"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
ITEMS = Counter("scraper_items_extracted_total", "Витягнуті записи (книжки/цитати)", ["source", "page_type"])
VALIDATION_ERRORS = Counter("scraper_validation_errors_total", "Порушення контракту даних", ["source", "page_type"])
LAST_SUCCESS = Gauge("scraper_last_success_timestamp_seconds", "Час останньої успішної сторінки", ["source", "page_type"])

_started = False


def serve(port: int) -> None:
    global _started
    if _started:
        return
    start_http_server(port)
    _started = True
    log.info("metrics server started", extra={"path": f":{port}/metrics"})
