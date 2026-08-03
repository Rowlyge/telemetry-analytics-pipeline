# Telemetry Analytics Pipeline

Data consumer pipeline for [KuFlow](https://github.com/Rowlyge/proxy-kuflow) telemetry.
Python ETL + PostgreSQL data modeling + SQL analytics via window functions.

KuFlow is the **data producer** (Go, reverse/forward proxy + telemetry).
This project is the **data consumer**: it ingests raw request logs, cleans
and types them, and builds analytical marts on top.

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
┌───────────────┐   ingest/file_watcher.py
│  raw           │   append-only, JSONB payload as-is,
│  request_logs  │   partitioned by date, idempotent via ingest_manifest
└───────┬───────┘
        │
        ▼
┌───────────────┐   transform/load.py
│  processed     │   pydantic-validated, typed, deduplicated
│  requests      │   invalid rows → processed.quarantine
│  quarantine    │   idempotent via processed.watermark
│  watermark     │
└───────┬───────┘
        │
        ▼
┌───────────────┐   scripts/refresh_marts.py
│  curated       │   materialized views, refreshed on demand
│  * marts       │
└───────────────┘
```

**Raw → Processed → Curated**, each layer idempotent and independently
re-runnable without duplicating or losing data.

## Curated marts

| Mart | What it answers |
|---|---|
| `curated.top_ip_by_traffic` | Which client IPs generate the most traffic/errors |
| `curated.latency_percentiles` | p50 / p95 / p99 latency per endpoint |
| `curated.error_rate_by_endpoint` | Error rate (4xx/5xx split) per endpoint |
| `curated.traffic_windows_5m` | 5-minute traffic buckets with `LAG` deltas and rolling averages (window functions) |

## Stack
- **Python ETL** — ingest (file → raw), transform (pydantic validation → processed)
- **PostgreSQL** — raw / processed / curated schemas, partitioned raw layer
- **SQL** — materialized views, `percentile_cont`, window functions (`LAG`, moving averages)

## Project structure

```
telemetry-analytics-pipeline/
├── ingest/
│   └── file_watcher.py        # JSONL → raw.request_logs (idempotent)
├── transform/
│   ├── models.py               # pydantic schema for raw records
│   └── load.py                 # raw → processed.requests / quarantine
├── sql/
│   ├── schema/                 # DDL: raw, processed schemas + tables
│   └── marts/                  # curated materialized views
├── scripts/
│   ├── generate_synthetic_logs.py  # synthetic KuFlow-like JSONL data
│   ├── refresh_marts.py            # (re)create / refresh curated marts
│   └── test_connection.py          # Postgres connectivity check
├── logs/                       # JSONL input files (gitignored)
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

# 2. Ingest raw JSONL into raw.request_logs
python ingest/file_watcher.py

# 3. Validate & transform into processed.requests
python transform/load.py

# 4. Build / refresh curated marts
python scripts/refresh_marts.py           # (re)create marts
python scripts/refresh_marts.py --refresh # refresh data only
```

Each stage is idempotent — re-running any script picks up only new data
(already-ingested files and already-processed rows are skipped).

## Status
✅ Raw → Processed → Curated pipeline working end-to-end on synthetic data
🚧 Reporting layer (dashboard / exports) — not yet started
🚧 Switch from synthetic data to real KuFlow structured events — pending
   structured logging support on the KuFlow side