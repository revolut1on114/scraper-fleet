"""Збереження raw і normalized JSON у data/raw/<source>/ і data/normalized/<source>/."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings

log = logging.getLogger(__name__)


def page_id(url: str) -> str:
    """Стабільний, читабельний id сторінки: slug зі шляху + 8 символів хешу URL.

    https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html
      -> catalogue-a-light-in-the-attic_1000-3d6f1a2b
    """
    path = urlparse(url).path
    path = re.sub(r"(index\.html?|/)$", "", path)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", path).strip("-")[:80] or "root"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # атомарна заміна: читач ніколи не побачить напівзаписаний файл
    return path


def save_raw(record: dict[str, Any], data_dir: Path | None = None) -> Path:
    base = (data_dir or settings.data_dir) / "raw" / record["source"]
    path = _write_json_atomic(base / f"{page_id(record['url'])}.json", record)
    log.debug("raw saved", extra={"path": str(path), "url": record["url"]})
    return path


def save_normalized(record: dict[str, Any], data_dir: Path | None = None) -> Path:
    base = (data_dir or settings.data_dir) / "normalized" / record["source"]
    path = _write_json_atomic(base / f"{page_id(record['url'])}.json", record)
    log.debug("normalized saved", extra={"path": str(path), "url": record["url"]})
    return path
