"""Простий logging: JSON-рядки в stdout (зручно для `docker compose logs` і grep/jq)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.config import settings

# Поля, які можна передати через logger.info("...", extra={...})
_EXTRA_FIELDS = ("url", "worker", "page_type", "status", "duration_ms", "items", "error", "path", "task_id")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str | None = None) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level or settings.log_level)

    # Приглушуємо балакучі бібліотеки
    for noisy in ("asyncio", "urllib3", "httpx", "aiohttp", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
