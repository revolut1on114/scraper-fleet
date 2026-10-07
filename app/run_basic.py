"""BASIC: один worker-html, один прогін, 10–15 сторінок books.toscrape.com.

    python -m app.run_basic            # локально
    docker compose --profile basic up  # у Docker

Алгоритм: list page(s) -> зібрати посилання на книжки -> detail pages -> raw + normalized JSON.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone

from app.config import settings
from app.crawler import fetch_html
from app.logging_setup import setup_logging
from app.pipeline import process

log = logging.getLogger("run_basic")
WORKER = "worker-html"


async def main() -> int:
    started = datetime.now(timezone.utc)
    log.info("basic run started", extra={"worker": WORKER, "url": settings.books_base_url})
    outcomes = []

    # 1) List pages
    detail_urls: list[str] = []
    list_url: str | None = settings.books_base_url
    for _ in range(max(1, settings.list_pages)):
        if not list_url:
            break
        [fetch] = await fetch_html([list_url])
        out = process(fetch, "books_list", WORKER)
        outcomes.append(out)
        detail_urls += [b["url"] for b in out.data.get("books", []) if b.get("url")]
        list_url = out.data.get("next_url")

    # 2) Detail pages — у межах загального ліміту сторінок
    budget = max(0, settings.max_pages - len(outcomes))
    detail_urls = list(dict.fromkeys(detail_urls))[:budget]
    log.info("detail pages queued", extra={"worker": WORKER, "items": len(detail_urls)})
    for fetch in await fetch_html(detail_urls):
        outcomes.append(process(fetch, "books_detail", WORKER))

    # 3) Підсумок
    by_status = Counter(o.status for o in outcomes)
    total = len(outcomes)
    summary = {
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "worker": WORKER,
        "pages_total": total,
        "by_status": dict(by_status),
        "success_rate": round(by_status["ok"] / total, 3) if total else 0.0,
        "failed_urls": [o.url for o in outcomes if o.status != "ok"],
    }
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("basic run finished", extra={"worker": WORKER, "items": total, "status": json.dumps(summary["by_status"])})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if by_status["ok"] else 1


if __name__ == "__main__":
    setup_logging()
    sys.exit(asyncio.run(main()))
