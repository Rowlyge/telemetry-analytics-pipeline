"""
Применяет все SQL-файлы из sql/marts/ (создаёт/пересоздаёт materialized views)
и/или рефрешит их данные.

Запуск:
    python scripts/refresh_marts.py           # применить DDL всех витрин
    python scripts/refresh_marts.py --refresh # только REFRESH данных существующих витрин
"""

import argparse
import os
from pathlib import Path

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

MARTS_DIR = Path(__file__).parent.parent / "sql" / "marts"

MART_NAMES = [
    "top_ip_by_traffic",
    "latency_percentiles",
    "error_rate_by_endpoint",
    "traffic_windows_5m",
]


def apply_ddl(conn) -> None:
    for name in MART_NAMES:
        filepath = MARTS_DIR / f"{name}.sql"
        print(f"Applying {filepath.name} ...")
        with open(filepath, "r") as f:
            sql = f.read()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("✅ All marts (re)created.")


def refresh_views(conn) -> None:
    for name in MART_NAMES:
        print(f"Refreshing curated.{name} ...")
        with conn.cursor() as cur:
            cur.execute(f"REFRESH MATERIALIZED VIEW curated.{name};")
        conn.commit()
    print("✅ All marts refreshed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Only refresh data in existing views (skip DDL recreation)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    if args.refresh:
        refresh_views(conn)
    else:
        apply_ddl(conn)
    conn.close()


if __name__ == "__main__":
    main()