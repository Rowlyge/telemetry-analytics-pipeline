# Telemetry Analytics Pipeline

Data consumer pipeline for [KuFlow](https://github.com/Rowlyge/proxy-kuflow) telemetry.
Python ETL + PostgreSQL data modeling + SQL analytics via window functions.

## Architecture

Raw (JSONL from KuFlow) → Processed (Python ETL, cleaned & typed) → Curated (SQL marts)

## Stack
- Python ETL (ingest, validation, transform)
- PostgreSQL (raw / processed / curated schemas)
- SQL analytical views (window functions, percentiles)

## Setup
\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # заполнить реальными значениями
\`\`\`

## Status
🚧 In development
