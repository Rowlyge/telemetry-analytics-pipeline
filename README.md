# Telemetry Analytics Pipeline

[![CI](https://github.com/Rowlyge/telemetry-analytics-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Rowlyge/telemetry-analytics-pipeline/actions/workflows/ci.yml)

Data consumer pipeline for [KuFlow](https://github.com/Rowlyge/proxy-kuflow) telemetry.
Python ETL + PostgreSQL data modeling + SQL analytics via window functions.

KuFlow is the **data producer** (Go, reverse/forward proxy + telemetry).
This project is the **data consumer**: it ingests raw request logs, cleans
and types them, builds analytical marts on top, and renders them as reports.

> **Note:** KuFlow does not yet emit structured telemetry events (only plain
> text startup/health-check logs). Until it does, this pipeline runs against
> synthetic JSONL data generated to match the target schema (see
> `scripts/generate_synthetic_logs.py`). Swapping in real KuFlow events later
> only requires changing the ingest source — the rest of the pipeline (schema,
> transform, marts) stays the same.

## Architecture

```
KuFlow (JSONL, synthetic for now)
        │
        ▼
┌────────────────┐   ingest/file_watcher.py
│  raw            │   append-only, JSONB payload as-is,
│  request_logs   │   partitioned DAILY by ingested_at,
│  ingest_manifest│   idempotent via ingest_manifest (per source file)
└───────┬────────┘
        │
        ▼
┌────────────────┐   transform/load.py
│  processed      │   pydantic-validated, typed, deduplicated
│  requests       │   invalid rows → processed.quarantine
│  quarantine     │   idempotent via processed.watermark
│  watermark      │
└───────┬────────┘
        │
        ▼
┌────────────────┐   scripts/refresh_marts.py
│  curated        │   materialized views, refreshed on demand
│  * marts        │
└───────┬────────┘
        │
        ▼
┌────────────────┐   reports/generate_report.py
│  HTML report    │   self-contained file: charts (matplotlib) + tables
└────────────────┘
```

**Raw → Processed → Curated**, each layer idempotent and independently
re-runnable without duplicating or losing data. Every stage is covered by
CI, which runs lint + the full test suite (unit + integration) against a
live Postgres service container on every push.

## Curated marts

| Mart | What it answers |
|---|---|
| `curated.top_ip_by_traffic` | Which client IPs generate the most traffic/errors |
| `curated.latency_percentiles` | p50 / p95 / p99 latency per endpoint |
| `curated.error_rate_by_endpoint` | Error rate (4xx/5xx split) per endpoint |
| `curated.traffic_windows_5m` | 5-minute traffic buckets with `LAG` deltas and rolling averages (window functions) |

## Reports

`reports/generate_report.py` produces a single self-contained HTML file
(charts embedded as base64 PNGs, no external dependencies) summarizing all
four curated marts — top IPs, latency percentiles, error rates, and the
traffic/latency trend over time.

## Stack
- **Python ETL** — ingest (file → raw), transform (pydantic validation → processed)
- **PostgreSQL** — raw / processed / curated schemas, daily-partitioned raw layer
- **SQL** — materialized views, `percentile_cont`, window functions (`LAG`, moving averages)
- **Testing** — pytest (unit tests for validation logic, integration tests against a real database)
- **CI/CD** — GitHub Actions (lint + full test suite on every push)
- **Reporting** — pandas + matplotlib, rendered as static HTML

## Project structure

```
telemetry-analytics-pipeline/
├── .github/workflows/
│   └── ci.yml                      # lint + tests on every push (live Postgres service)
├── ingest/
│   └── file_watcher.py             # JSONL → raw.request_logs (idempotent)
├── transform/
│   ├── models.py                   # pydantic schema for raw records
│   └── load.py                     # raw → processed.requests / quarantine
├── sql/
│   ├── schema/                     # DDL: raw, processed schemas + tables
│   └── marts/                      # curated materialized views
├── scripts/
│   ├── generate_synthetic_logs.py  # synthetic KuFlow-like JSONL data
│   ├── manage_partitions.py        # backfill + pre-create daily raw partitions
│   ├── refresh_marts.py            # (re)create / refresh curated marts
│   └── test_connection.py          # Postgres connectivity check
├── reports/
│   └── generate_report.py          # self-contained HTML report with charts
├── tests/
│   ├── test_models.py              # unit tests (no DB required)
│   ├── test_transform_integration.py  # integration tests (real Postgres)
│   └── conftest.py                 # shared fixtures, auto-skips DB tests if unreachable
├── logs/                           # JSONL input files (gitignored)
├── pytest.ini
├── .env.example
├── requirements.txt
└── README.md
```

## Setup

### 1. PostgreSQL (WSL Ubuntu)
```bash
sudo apt install -y postgresql postgresql-contrib
sudo service postgresql start
sudo -u postgres createuser --interactive --pwprompt kuflow_analytics
sudo -u postgres createdb -O kuflow_analytics telemetry
```

### 2. Python environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in real DB host/port/user/password
```

### 3. Apply schema
```bash
psql -h <host> -p <port> -U kuflow_analytics -d telemetry -f sql/schema/001_init.sql
psql -h <host> -p <port> -U kuflow_analytics -d telemetry -f sql/schema/002_ingest_manifest.sql
```

## Usage

```bash
# 1. Generate synthetic test data (until real KuFlow events are available)
python scripts/generate_synthetic_logs.py --count 5000 --out logs/sample_001.jsonl

# 2. Pre-create daily partitions for raw.request_logs (run periodically, e.g. weekly)
python scripts/manage_partitions.py --create-future 7

# 3. Ingest raw JSONL into raw.request_logs
python ingest/file_watcher.py

# 4. Validate & transform into processed.requests
python transform/load.py

# 5. Build / refresh curated marts
python scripts/refresh_marts.py           # (re)create marts
python scripts/refresh_marts.py --refresh # refresh data only

# 6. Generate an HTML report
python reports/generate_report.py
```

Each stage is idempotent — re-running any script picks up only new data
(already-ingested files and already-processed rows are skipped).

## Testing

```bash
pytest tests/test_models.py -v   # unit tests only, no DB required
pytest -m integration -v         # integration tests, requires a live Postgres
pytest -v                        # everything
```

The same suite runs automatically in CI on every push, against a disposable
Postgres service container — see `.github/workflows/ci.yml`.

## Status
✅ Raw → Processed → Curated pipeline working end-to-end on synthetic data
✅ Daily partitioning for the raw layer (backfill + future partition creation)
✅ Unit + integration test coverage
✅ CI (lint + tests) on every push
✅ HTML reporting layer
🚧 Switch from synthetic data to real KuFlow structured events — pending
   structured logging support on the KuFlow side

## Author

**Michail Sokun**
