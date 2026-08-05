"""
Ingest: читает JSONL-файлы из LOG_DIR и загружает их as-is в raw.request_logs.

Идемпотентность обеспечивается таблицей raw.ingest_manifest — файл,
который уже был загружен (есть в манифесте), повторно не читается.

Запуск:
    python ingest/file_watcher.py
"""

import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "telemetry"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

LOG_DIR = Path(os.getenv("KUFLOW_LOG_DIR", "./logs"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))


def get_already_ingested_files(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT source_file FROM raw.ingest_manifest;")
        return {row[0] for row in cur.fetchall()}


def ingest_file(conn, filepath: Path) -> int:
    """Читает JSONL построчно и вставляет в raw.request_logs батчами."""
    rows = []
    total_inserted = 0
    skipped_invalid = 0

    with open(filepath, "r") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  ⚠️  {filepath.name}:{line_num} invalid JSON, skipping ({e})")
                skipped_invalid += 1
                continue

            rows.append((filepath.name, psycopg2.extras.Json(payload)))

            if len(rows) >= BATCH_SIZE:
                total_inserted += _flush_batch(conn, rows)
                rows = []

    if rows:
        total_inserted += _flush_batch(conn, rows)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.ingest_manifest (source_file, row_count)
            VALUES (%s, %s)
            ON CONFLICT (source_file) DO NOTHING;
            """,
            (filepath.name, total_inserted),
        )
    conn.commit()

    if skipped_invalid:
        print(f"  ⚠️  {skipped_invalid} invalid lines skipped in {filepath.name}")

    return total_inserted


def _flush_batch(conn, rows: list) -> int:
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO raw.request_logs (source_file, payload) VALUES %s",
            rows,
        )
    conn.commit()
    return len(rows)


def main() -> int:
    if not LOG_DIR.exists():
        print(f"❌ Log directory not found: {LOG_DIR}")
        return 1

    jsonl_files = sorted(LOG_DIR.glob("*.jsonl"))
    if not jsonl_files:
        print(f"No .jsonl files found in {LOG_DIR}")
        return 0

    conn = psycopg2.connect(**DB_CONFIG)
    already_ingested = get_already_ingested_files(conn)

    total_files = 0
    total_rows = 0

    for filepath in jsonl_files:
        if filepath.name in already_ingested:
            print(f"⏭️  {filepath.name} already ingested, skipping")
            continue

        print(f"📥 Ingesting {filepath.name} ...")
        inserted = ingest_file(conn, filepath)
        print(f"   ✅ {inserted} rows inserted")
        total_files += 1
        total_rows += inserted

    conn.close()

    print(f"\nDone. {total_files} file(s) ingested, {total_rows} row(s) total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())