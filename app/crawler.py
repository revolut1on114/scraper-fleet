"""Тонка обгортка над Crawl4AI.

worker-html -> AsyncHTTPCrawlerStrategy: звичайний HTTP GET, без браузера (швидко, дешево).
worker-js   -> стандартна Playwright-стратегія Crawl4AI + wait_for: чекаємо, поки JS намалює DOM.

Обидва повертають однаковий FetchResult, тож решта pipeline не знає, як саме сторінку забрали.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, HTTPCrawlerConfig
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

from app.config import settings

log = logging.getLogger(__name__)

USER_AGENT = "scraper-fleet-homework/1.0 (educational crawler; polite, low volume)"


@dataclass
class FetchResult:
    url: str
    ok: bool
    fetched_at: str
    status_code: int | None = None
    html: str = ""
    markdown: str = ""
    title: str | None = None
    links: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _links(result: Any) -> list[str]:
    """Crawl4AI віддає {'internal': [{'href':..}], 'external': [...]} -> плоский список унікальних URL."""
    seen: dict[str, None] = {}
    for bucket in ("internal", "external"):
        for item in (getattr(result, "links", None) or {}).get(bucket, []) or []:
            href = item.get("href") if isinstance(item, dict) else None
            if href and href.startswith(("http://", "https://")):
                seen.setdefault(href.split("#")[0], None)
    return list(seen)


def _markdown(result: Any) -> str:
    md = getattr(result, "markdown", None)
    if md is None:
        return ""
    return getattr(md, "raw_markdown", None) or str(md)


def _to_fetch_result(url: str, result: Any, started: float) -> FetchResult:
    duration = int((time.perf_counter() - started) * 1000)
    status = getattr(result, "status_code", None)
    ok = bool(getattr(result, "success", False)) and (status is None or 200 <= status < 400)
    meta = getattr(result, "metadata", None) or {}
    return FetchResult(
        url=url,
        ok=ok,
        fetched_at=_now(),
        status_code=status,
        html=getattr(result, "html", "") or "",
        markdown=_markdown(result),
        title=(meta.get("title") or "").strip() or None,
        links=_links(result),
        error=None if ok else (getattr(result, "error_message", None) or f"HTTP {status}"),
        duration_ms=duration,
    )


async def fetch_html(urls: list[str]) -> list[FetchResult]:
    """worker-html: один HTTP-клієнт на пачку URL, послідовно з паузою (ввічливо до сайту)."""
    import asyncio

    strategy = AsyncHTTPCrawlerStrategy(browser_config=HTTPCrawlerConfig(headers={"User-Agent": USER_AGENT}))
    run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=settings.page_timeout_ms, verbose=False)
    out: list[FetchResult] = []
    async with AsyncWebCrawler(crawler_strategy=strategy, verbose=False) as crawler:
        for i, url in enumerate(urls):
            if i:
                await asyncio.sleep(settings.request_delay_ms / 1000)
            started = time.perf_counter()
            try:
                result = await crawler.arun(url=url, config=run_cfg)
                out.append(_to_fetch_result(url, result, started))
            except Exception as exc:  # мережа, таймаут, DNS...
                out.append(FetchResult(url=url, ok=False, fetched_at=_now(), error=repr(exc),
                                       duration_ms=int((time.perf_counter() - started) * 1000)))
    return out


async def fetch_js(url: str, wait_for: str) -> FetchResult:
    """worker-js: headless Chromium, чекаємо на селектор, що з'являється лише після JS."""
    browser_cfg = BrowserConfig(headless=True, user_agent=USER_AGENT, verbose=False)
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_for=wait_for,
        page_timeout=settings.page_timeout_ms,
        verbose=False,
    )
    started = time.perf_counter()
    try:
        async with AsyncWebCrawler(config=browser_cfg, verbose=False) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)
        return _to_fetch_result(url, result, started)
    except Exception as exc:
        return FetchResult(url=url, ok=False, fetched_at=_now(), error=repr(exc),
                           duration_ms=int((time.perf_counter() - started) * 1000))
