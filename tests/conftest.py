"""
Общие fixtures для тестов. Интеграционные тесты, помеченные @pytest.mark.integration,
требуют реального подключения к Postgres (переменные из .env) и автоматически
skip'аются, если БД недоступна — так unit-тесты (test_models.py) всегда можно
гонять без окружения, а интеграционные — когда Postgres поднят.
"""

import os
import sys
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "transform"))

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "telemetry"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}


@pytest.fixture(scope="session")
def db_conn():
    try:
        conn = psycopg2.connect(**DB_CONFIG, connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"Postgres not reachable, skipping integration tests: {e}")
    yield conn
    conn.close()


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires a live Postgres connection")