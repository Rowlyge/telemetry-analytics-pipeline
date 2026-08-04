"""
Unit-тесты для transform/models.py — валидация сырых записей телеметрии.
Не требуют базы данных, гоняются мгновенно.

Запуск:
    pytest tests/test_models.py -v
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "transform"))
from models import RawRequestRecord  # noqa: E402


VALID_RECORD = {
    "timestamp": "2026-08-01T10:23:45.123Z",
    "request_id": "a1b2c3d4e5f6",
    "client_ip": "203.0.113.42",
    "method": "GET",
    "path": "/api/v1/users",
    "host": "api.example.com",
    "status_code": 200,
    "latency_ms": 42.7,
    "upstream": "backend-svc-01",
    "bytes_sent": 1024,
    "bytes_received": 256,
    "user_agent": "curl/8.1.0",
    "error": None,
}


def test_valid_record_parses_successfully():
    record = RawRequestRecord.model_validate(VALID_RECORD)
    assert record.request_id == "a1b2c3d4e5f6"
    assert str(record.client_ip) == "203.0.113.42"
    assert record.method == "GET"
    assert record.status_code == 200


def test_method_is_normalized_to_uppercase():
    data = {**VALID_RECORD, "method": "get"}
    record = RawRequestRecord.model_validate(data)
    assert record.method == "GET"


def test_optional_fields_can_be_missing():
    data = {k: v for k, v in VALID_RECORD.items() if k not in ("host", "upstream", "user_agent", "error")}
    record = RawRequestRecord.model_validate(data)
    assert record.host is None
    assert record.upstream is None


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("client_ip", "not-an-ip"),
        ("client_ip", "999.999.999.999"),
        ("client_ip", "2001:db8::1"),  # IPv6, модель ожидает IPv4Address
        ("method", "FETCH"),
        ("status_code", 99),          # ниже допустимого диапазона (100-599)
        ("status_code", 600),         # выше допустимого диапазона
        ("status_code", "not-a-number"),
        ("latency_ms", -5),           # латентность не может быть отрицательной
        ("timestamp", "not-a-date"),
        ("request_id", ""),           # пустой request_id недопустим
        ("path", ""),                 # пустой path недопустим
    ],
)
def test_invalid_field_raises_validation_error(field, bad_value):
    data = {**VALID_RECORD, field: bad_value}
    with pytest.raises(ValidationError):
        RawRequestRecord.model_validate(data)


@pytest.mark.parametrize("missing_field", ["timestamp", "request_id", "client_ip", "method", "path", "status_code", "latency_ms"])
def test_missing_required_field_raises_validation_error(missing_field):
    data = {k: v for k, v in VALID_RECORD.items() if k != missing_field}
    with pytest.raises(ValidationError):
        RawRequestRecord.model_validate(data)


def test_boundary_status_codes_are_accepted():
    for code in (100, 599):
        data = {**VALID_RECORD, "status_code": code}
        record = RawRequestRecord.model_validate(data)
        assert record.status_code == code


def test_zero_latency_is_accepted():
    data = {**VALID_RECORD, "latency_ms": 0}
    record = RawRequestRecord.model_validate(data)
    assert record.latency_ms == 0