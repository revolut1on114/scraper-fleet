# Один Dockerfile, два образи (multi-stage targets):
#   html — worker-html, beat, basic-run: тільки Python + Crawl4AI (HTTP-стратегія, без браузера)
#   js   — worker-js: те саме + Chromium для Playwright (рендеринг JavaScript)

FROM python:3.12-slim AS html

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY app ./app
COPY tests ./tests

# Не запускаємо від root
RUN useradd --create-home --uid 1000 scraper \
    && mkdir -p /app/data/raw /app/data/normalized \
    && chown -R scraper:scraper /app
USER scraper

CMD ["python", "-m", "app.run_basic"]


FROM html AS js

USER root
# Chromium + системні залежності для Playwright (ставимо в загальний шлях, доступний користувачу scraper)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium \
    && chmod -R a+rx /ms-playwright \
    && rm -rf /var/lib/apt/lists/*
USER scraper
