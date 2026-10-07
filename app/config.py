"""Налаштування з env-змінних (одне місце, без магії)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Сайти
    books_base_url: str = os.getenv("BOOKS_BASE_URL", "https://books.toscrape.com/")
    quotes_js_url: str = os.getenv("QUOTES_JS_URL", "https://quotes.toscrape.com/js/")

    # Ліміти
    max_pages: int = _int("MAX_PAGES", 15)          # загальний ліміт сторінок за один прогін basic
    list_pages: int = _int("LIST_PAGES", 1)         # скільки list-сторінок каталогу обходити
    js_pages: int = _int("JS_PAGES", 2)             # скільки JS-сторінок quotes обходити
    request_delay_ms: int = _int("REQUEST_DELAY_MS", 500)  # ввічлива пауза між запитами
    page_timeout_ms: int = _int("PAGE_TIMEOUT_MS", 30000)

    # Зберігання
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))

    # Celery / scheduler
    broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
    books_interval_s: int = _int("BOOKS_INTERVAL_SECONDS", 1800)
    quotes_interval_s: int = _int("QUOTES_INTERVAL_SECONDS", 3600)

    # Метрики
    metrics_port: int = _int("METRICS_PORT", 9100)

    # Логи
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = os.getenv("LOG_FORMAT", "json")  # json | text

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def normalized_dir(self) -> Path:
        return self.data_dir / "normalized"


settings = Settings()
