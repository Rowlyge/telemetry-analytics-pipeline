"""
Интеграционные тесты для transform/load.py.
Требуют реального Postgres (пропускаются автоматически, если БД недоступна —
см. tests/conftest.py::db_conn).

Тесты используют изолированные, легко узнаваемые request_id/source_file
("test_integration_*"), и подчищают за собой все вставленные строки
в teardown — production/synthetic данные не затрагиваются.

Запуск:
    pytest tests/test_transform_integration.py -v -m integration
"""

import sys
import uuid
from pathlib import Path

import psycopg2.extras
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "transform"))
from load import insert_processed_batch, insert_quarantine_batch  # noqa: E402

pytestmark = pytest.mark.integration

TEST_SOURCE_FILE = "test_integration_marker"


def _insert_raw_row(conn, payload: dict) -> int:
    """Вставляет одну raw-строку и возвращает её ingest_id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.request_logs (source_file, payload) VALUES (%s, %s) RETURNING ingest_id;",
            (TEST_SOURCE_FILE, psycopg2.extras.Json(payload)),
        )
        ingest_id = cur.fetchone()[0]
    conn.commit()
    return ingest_id


@pytest.fixture
def cleanup_test_rows(db_conn):
    """Гарантирует очистку всех тестовых строк после теста, даже если он упал."""
    inserted_request_ids = []
    inserted_ingest_ids = []
    yield inserted_request_ids, inserted_ingest_ids

    with db_conn.cursor() as cur:
        if inserted_request_ids:
            cur.execute(
                "DELETE FROM processed.requests WHERE request_id = ANY(%s);",
                (inserted_request_ids,),
            )
        if inserted_ingest_ids:
            cur.execute(
                "DELETE FROM processed.quarantine WHERE ingest_id = ANY(%s);",
                (inserted_ingest_ids,),
            )
            cur.execute(
                "DELETE FROM raw.request_logs WHERE ingest_id = ANY(%s);",
                (inserted_ingest_ids,),
            )
    db_conn.commit()


def test_valid_record_inserted_into_processed(db_conn, cleanup_test_rows):
    inserted_request_ids, inserted_ingest_ids = cleanup_test_rows

    request_id = f"test-{uuid.uuid4().hex[:12]}"
    payload = {
        "timestamp": "2026-08-01T10:00:00.000Z",
        "request_id": request_id,
        "client_ip": "203.0.113.99",
        "method": "GET",
        "path": "/api/v1/test",
        "status_code": 200,
        "latency_ms": 12.5,
    }
    ingest_id = _insert_raw_row(db_conn, payload)
    inserted_ingest_ids.append(ingest_id)
    inserted_request_ids.append(request_id)

    row = (
        request_id, "2026-08-01T10:00:00.000Z", "203.0.113.99", "GET",
        "/api/v1/test", None, 200, 12.5, None, None, None, ingest_id,
    )
    insert_processed_batch(db_conn, [row])
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT status_code, is_error FROM processed.requests WHERE request_id = %s;", (request_id,))
        result = cur.fetchone()

    assert result is not None
    assert result[0] == 200
    assert result[1] is False


def test_duplicate_request_id_is_not_inserted_twice(db_conn, cleanup_test_rows):
    """Проверяет ON CONFLICT DO NOTHING — идемпотентность на уровне processed.requests."""
    inserted_request_ids, inserted_ingest_ids = cleanup_test_rows

    request_id = f"test-{uuid.uuid4().hex[:12]}"
    payload = {"request_id": request_id}  # содержимое неважно для этого теста
    ingest_id = _insert_raw_row(db_conn, payload)
    inserted_ingest_ids.append(ingest_id)
    inserted_request_ids.append(request_id)

    row = (
        request_id, "2026-08-01T10:00:00.000Z", "203.0.113.99", "GET",
        "/api/v1/test", None, 200, 12.5, None, None, None, ingest_id,
    )

    insert_processed_batch(db_conn, [row])
    insert_processed_batch(db_conn, [row])  # повторная вставка той же записи
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM processed.requests WHERE request_id = %s;", (request_id,))
        count = cur.fetchone()[0]

    assert count == 1


def test_invalid_record_goes_to_quarantine(db_conn, cleanup_test_rows):
    inserted_request_ids, inserted_ingest_ids = cleanup_test_rows

    payload = {"request_id": "broken", "status_code": "not-a-number"}
    ingest_id = _insert_raw_row(db_conn, payload)
    inserted_ingest_ids.append(ingest_id)

    insert_quarantine_batch(
        db_conn,
        [(ingest_id, "status_code must be an integer", psycopg2.extras.Json(payload))],
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT reason FROM processed.quarantine WHERE ingest_id = %s;", (ingest_id,))
        result = cur.fetchone()

    assert result is not None
    assert "status_code" in result[0]