"""
Transform: читает необработанные строки из raw.request_logs (по watermark),
валидирует через pydantic и загружает в processed.requests.
Невалидные строки уходят в processed.quarantine вместе с причиной.

Идемпотентность: watermark хранит последний обработанный ingest_id,
поэтому повторный запуск продолжает с того же места, не дублируя данные.

Запуск:
    python transform/load.py
"""

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))
from models import RawRequestRecord  # noqa: E402

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "telemetry"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))
WATERMARK_SOURCE = "kuflow_default"


def get_watermark(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_ingest_id FROM processed.watermark WHERE source_name = %s;",
            (WATERMARK_SOURCE,),
        )
        row = cur.fetchone()
        return row[0] if row else 0


def update_watermark(conn, last_ingest_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE processed.watermark
            SET last_ingest_id = %s, updated_at = now()
            WHERE source_name = %s;
            """,
            (last_ingest_id, WATERMARK_SOURCE),
        )


def fetch_unprocessed_batch(conn, after_ingest_id: int, limit: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ingest_id, payload
            FROM raw.request_logs
            WHERE ingest_id > %s
            ORDER BY ingest_id
            LIMIT %s;
            """,
            (after_ingest_id, limit),
        )
        return cur.fetchall()


def insert_processed_batch(conn, records: list) -> None:
    if not records:
        return
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO processed.requests (
                request_id, ts, client_ip, method, path, host,
                status_code, latency_ms, upstream,
                bytes_sent, bytes_received, ingest_id
            ) VALUES %s
            ON CONFLICT (request_id) DO NOTHING;
            """,
            records,
        )


def insert_quarantine_batch(conn, records: list) -> None:
    if not records:
        return
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO processed.quarantine (ingest_id, reason, payload)
            VALUES %s;
            """,
            records,
        )


def run() -> int:
    conn = psycopg2.connect(**DB_CONFIG)
    watermark = get_watermark(conn)
    print(f"Starting from ingest_id > {watermark}")

    total_valid = 0
    total_invalid = 0
    last_ingest_id = watermark

    while True:
        batch = fetch_unprocessed_batch(conn, last_ingest_id, BATCH_SIZE)
        if not batch:
            break

        valid_rows = []
        quarantine_rows = []

        for ingest_id, payload in batch:
            last_ingest_id = ingest_id
            try:
                record = RawRequestRecord.model_validate(payload)
            except ValidationError as e:
                quarantine_rows.append((ingest_id, str(e), psycopg2.extras.Json(payload)))
                total_invalid += 1
                continue

            valid_rows.append(
                (
                    record.request_id,
                    record.timestamp,
                    str(record.client_ip),
                    record.method,
                    record.path,
                    record.host,
                    record.status_code,
                    record.latency_ms,
                    record.upstream,
                    record.bytes_sent,
                    record.bytes_received,
                    ingest_id,
                )
            )
            total_valid += 1

        insert_processed_batch(conn, valid_rows)
        insert_quarantine_batch(conn, quarantine_rows)
        update_watermark(conn, last_ingest_id)
        conn.commit()

        print(f"  processed batch up to ingest_id={last_ingest_id} "
              f"(+{len(valid_rows)} valid, +{len(quarantine_rows)} quarantined)")

    conn.close()
    print(f"\nDone. {total_valid} valid, {total_invalid} quarantined. "
          f"Watermark now at {last_ingest_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(run())