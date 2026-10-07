"""ADVANCED: Celery-«флот». Дві черги (html, js), два типи воркерів, beat як scheduler.

    celery -A app.celery_app worker -Q html -n worker-html@%h -P solo
    celery -A app.celery_app worker -Q js   -n worker-js@%h   -P solo
    celery -A app.celery_app beat
"""

from __future__ import annotations

from celery import Celery
from celery.signals import after_setup_logger, worker_init
from kombu import Queue

from app.config import settings

app = Celery("scraper_fleet", broker=settings.broker_url, backend=settings.result_backend, include=["app.tasks"])

app.conf.update(
    task_queues=(Queue("html"), Queue("js")),
    task_default_queue="html",
    task_routes={
        "books.*": {"queue": "html"},
        "quotes.*": {"queue": "js"},
    },
    task_acks_late=True,                # таск підтверджується після виконання -> не губиться при падінні воркера
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,       # повільні crawl-таски: по одному
    task_time_limit=180,
    task_soft_time_limit=150,
    result_expires=3600,
    timezone="Europe/Kyiv",
    broker_connection_retry_on_startup=True,
    # Scheduler (Celery beat)
    beat_schedule={
        "books-catalog": {
            "task": "books.crawl_list",
            "schedule": float(settings.books_interval_s),
            "options": {"queue": "html"},
        },
        "quotes-js": {
            "task": "quotes.crawl_js",
            "schedule": float(settings.quotes_interval_s),
            "options": {"queue": "js"},
        },
    },
)


@after_setup_logger.connect
def _json_logs(logger, *args, **kwargs):  # noqa: ARG001
    from app.logging_setup import setup_logging

    setup_logging()


@worker_init.connect
def _start_metrics(**_):
    # -P solo: один процес на контейнер -> один /metrics. Масштабування = більше контейнерів
    # (docker compose up --scale worker-html=3), Prometheus знайде їх через DNS.
    from app.metrics import serve

    serve(settings.metrics_port)
