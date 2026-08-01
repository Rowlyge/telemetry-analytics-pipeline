"""
Проверка подключения к Postgres.
Запуск: python scripts/test_connection.py
"""

import os
import sys

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


def main() -> int:
    print(f"Connecting to {DB_CONFIG['user']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']} ...")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as e:
        print("❌ Connection failed.")
        print(f"   {e}")
        return 1

    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            print("✅ Connected successfully.")
            print(f"   Postgres version: {version}")

            cur.execute("SELECT current_database(), current_user;")
            db, user = cur.fetchone()
            print(f"   Database: {db} | User: {user}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())