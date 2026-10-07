# Архітектура

## Basic

```mermaid
flowchart LR
    S[books.toscrape.com] -->|HTTP GET| W[worker-html<br/>app.run_basic]
    W -->|list page| P1[parsers.books.extract_list]
    P1 -->|14 detail URL| W
    W -->|detail pages| P2[parsers.books.extract_detail]
    P1 & P2 --> PL[pipeline.process<br/>validate · log]
    PL --> R[(data/raw/)]
    PL --> N[(data/normalized/)]
    PL --> SUM[data/run_summary.json]
```

Один контейнер, один прогін, без брокера. Логіку обробки сторінки (`pipeline.process`) повторно використовує advanced-рівень.

## Advanced

```mermaid
flowchart LR
    subgraph sched[Scheduler]
        B[beat<br/>Celery beat]
    end
    subgraph broker[Broker]
        Q1[[queue: html]]
        Q2[[queue: js]]
    end
    subgraph fleet[Workers]
        WH[worker-html<br/>Crawl4AI HTTP strategy<br/>без браузера]
        WJ[worker-js<br/>Crawl4AI + Chromium<br/>wait_for css:div.quote]
    end
    B -->|books.crawl_list кожні 30 хв| Q1
    B -->|quotes.crawl_js щогодини| Q2
    Q1 --> WH
    Q2 --> WJ
    WH -->|list page -> N × books.crawl_detail| Q1
    WJ -->|next page -> quotes.crawl_js| Q2
    WH --> S1[books.toscrape.com]
    WJ --> S2[quotes.toscrape.com/js]
    WH & WJ --> D[(data/raw + data/normalized)]
    WH & WJ -->|/metrics :9100| PR[Prometheus]
    PR --> G[Grafana]
```

## Потік однієї сторінки

```mermaid
sequenceDiagram
    participant T as Celery task
    participant C as crawler.fetch_*
    participant P as parser (CSS schema)
    participant V as validate_*
    participant S as storage
    participant M as metrics
    T->>C: URL
    C-->>T: FetchResult (html, markdown, links, status)
    alt fetch failed
        T->>M: pages_total{status=fetch_error}
        T-->>T: retry з backoff (до 3 разів)
    else ok
        T->>S: raw JSON
        T->>P: html
        P-->>T: structured data
        T->>V: data
        V-->>T: errors[]
        T->>S: normalized JSON (valid, validation_errors)
        T->>M: pages_total{status=ok|validation_error}, items, last_success
    end
```

## Рішення і чому

| Рішення | Причина |
|---|---|
| Дві черги `html` і `js` | браузерні задачі в 10–50 разів дорожчі; окрема черга не дає їм загальмувати дешевий HTML-збір і дозволяє масштабувати воркери незалежно |
| list і detail — окремі таски | збій однієї книжки не перезапускає весь каталог; retry точковий |
| Два Docker-таргети (`html`, `js`) | образ `worker-html` не тягне Chromium (~400 MB) |
| `-P solo` + один `/metrics` на контейнер | прості метрики без multiprocess-режиму prometheus_client; масштабування — через `--scale` |
| `task_acks_late` + `prefetch=1` | таск не губиться, якщо воркер упав посеред crawl |
| Невалідний запис зберігається з `valid=false` | зміна DOM видно в даних і метриках, а не мовчки зникає |
| Атомарний запис JSON (tmp + rename) | читач ніколи не бачить напівзаписаний файл |
