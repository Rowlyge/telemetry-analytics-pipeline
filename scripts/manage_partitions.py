"""
Управление дневными партициями raw.request_logs.

Два режима:
  --backfill        Переносит данные, накопившиеся в raw.request_logs_default,
                     в правильные датированные партиции (по одной на каждый
                     день, встреченный в default). ingest_id сохраняется
                     (копируется как есть, не перегенерируется), так что
                     processed.requests.ingest_id остаётся валидным.

  --create-future N  Заранее создаёт пустые партиции на N дней вперёд
                     (включая сегодня), чтобы новые ingest'ы сразу попадали
                     в нужную партицию, а не в default.

Оба режима идемпотентны — партиция, которая уже существует, пропускается.

Запуск:
    python scripts/manage_partitions.py --backfill
    python scripts/manage_partitions.py --create-future 7
"""

import argparse
import os
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "telemetry"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


def partition_name(d: date) -> str:
    return f"request_logs_{d.strftime('%Y_%m_%d')}"


def partition_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM pg_catalog.pg_tables
            WHERE schemaname = 'raw' AND tablename = %s;
            """,
            (table_name,),
        )
        return cur.fetchone() is not None


def create_future_partitions(conn, days_ahead: int) -> None:
    today = date.today()
    for offset in range(days_ahead):
        day = today + timedelta(days=offset)
        next_day = day + timedelta(days=1)
        table_name = partition_name(day)

        if partition_exists(conn, table_name):
            print(f"⏭️  raw.{table_name} already exists, skipping")
            continue

        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE raw.{table_name}
                    PARTITION OF raw.request_logs
                    FOR VALUES FROM (%s) TO (%s);
                """,
                (day.isoformat(), next_day.isoformat()),
            )
        conn.commit()
        print(f"✅ Created raw.{table_name} for {day.isoformat()}")


def get_dates_in_default(conn) -> list[date]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT date_trunc('day', ingested_at)::date
            FROM raw.request_logs_default
            ORDER BY 1;
            """
        )
        return [row[0] for row in cur.fetchall()]


def backfill_day(conn, day: date) -> int:
    next_day = day + timedelta(days=1)
    table_name = partition_name(day)

    if partition_exists(conn, table_name):
        print(f"⏭️  raw.{table_name} already exists, skipping backfill for {day}")
        return 0

    with conn.cursor() as cur:
        # Отдельная таблица с точно такой же структурой/индексами, что у default.
        cur.execute(
            f"""
            CREATE TABLE raw.{table_name}
                (LIKE raw.request_logs_default INCLUDING ALL);
            """
        )

        cur.execute(
            f"""
            INSERT INTO raw.{table_name}
            SELECT * FROM raw.request_logs_default
            WHERE ingested_at >= %s AND ingested_at < %s;
            """,
            (day.isoformat(), next_day.isoformat()),
        )
        moved = cur.rowcount

        cur.execute(
            """
            DELETE FROM raw.request_logs_default
            WHERE ingested_at >= %s AND ingested_at < %s;
            """,
            (day.isoformat(), next_day.isoformat()),
        )

        cur.execute(
            f"""
            ALTER TABLE raw.request_logs
                ATTACH PARTITION raw.{table_name}
                FOR VALUES FROM (%s) TO (%s);
            """,
            (day.isoformat(), next_day.isoformat()),
        )

    conn.commit()
    print(f"✅ Backfilled raw.{table_name}: {moved} row(s) moved from default")
    return moved


def backfill(conn) -> None:
    dates = get_dates_in_default(conn)
    if not dates:
        print("No data in raw.request_logs_default — nothing to backfill.")
        return

    print(f"Found data for {len(dates)} day(s) in default partition: "
          f"{', '.join(d.isoformat() for d in dates)}")

    total_moved = 0
    for day in dates:
        total_moved += backfill_day(conn, day)

    print(f"\nDone. {total_moved} row(s) backfilled into dated partitions.")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backfill", action="store_true", help="Move existing default-partition data into dated partitions")
    group.add_argument("--create-future", type=int, metavar="N", help="Create N days of future partitions starting today")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)

    if args.backfill:
        backfill(conn)
    elif args.create_future:
        create_future_partitions(conn, args.create_future)

    conn.close()


if __name__ == "__main__":
    main()