"""
Pydantic-модель, описывающая ожидаемую структуру одной записи телеметрии
(будь то синтетические данные или, в будущем, реальные события KuFlow).
"""

from datetime import datetime
from ipaddress import IPv4Address

from pydantic import BaseModel, Field, field_validator


class RawRequestRecord(BaseModel):
    timestamp: datetime
    request_id: str = Field(min_length=1)
    client_ip: IPv4Address
    method: str
    path: str = Field(min_length=1)
    host: str | None = None
    status_code: int = Field(ge=100, le=599)
    latency_ms: float = Field(ge=0)
    upstream: str | None = None
    bytes_sent: int | None = Field(default=None, ge=0)
    bytes_received: int | None = Field(default=None, ge=0)
    user_agent: str | None = None
    error: str | None = None

    @field_validator("method")
    @classmethod
    def method_must_be_known(cls, v: str) -> str:
        allowed = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        if v.upper() not in allowed:
            raise ValueError(f"unknown HTTP method: {v}")
        return v.upper()