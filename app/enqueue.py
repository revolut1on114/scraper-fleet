"""Ручний запуск задач, не чекаючи на beat.

    python -m app.enqueue books     # каталог + деталі (черга html)
    python -m app.enqueue quotes    # JS-сторінки (черга js)
    python -m app.enqueue all
"""

from __future__ import annotations

import sys

from app.tasks import crawl_js, crawl_list


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else "all"
    if what not in {"books", "quotes", "all"}:
        print(__doc__)
        return 2
    if what in {"books", "all"}:
        print("books.crawl_list ->", crawl_list.delay().id)
    if what in {"quotes", "all"}:
        print("quotes.crawl_js  ->", crawl_js.delay().id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
