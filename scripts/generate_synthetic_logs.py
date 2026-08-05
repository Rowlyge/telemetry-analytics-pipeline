"""
Генератор синтетических JSONL-логов, имитирующих телеметрию KuFlow.
Используется до тех пор, пока KuFlow не начнёт писать структурированные
события самостоятельно.

Запуск:
    python scripts/generate_synthetic_logs.py --count 5000 --out logs/sample_001.jsonl
"""

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

METHODS = ["GET", "GET", "GET", "POST", "PUT", "DELETE"]  # GET чаще, ближе к реальности
PATHS = [
    "/api/v1/users",
    "/api/v1/users/{id}",
    "/api/v1/orders",
    "/api/v1/orders/{id}",
    "/api/v1/products",
    "/health",
    "/metrics",
]
HOSTS = ["api.example.com", "api-internal.example.com"]
UPSTREAMS = ["backend-svc-01", "backend-svc-02", "backend-svc-03"]

# status_code -> относительный вес (большинство успешных, немного ошибок)
STATUS_WEIGHTS = {
    200: 70,
    201: 8,
    204: 5,
    400: 4,
    401: 2,
    404: 5,
    429: 2,
    500: 2,
    502: 1,
    503: 1,
}


def random_ip() -> str:
    # немного "горячих" IP, чтобы top_ip_by_traffic имел выраженных лидеров
    if random.random() < 0.3:
        return random.choice(["203.0.113.10", "203.0.113.42", "198.51.100.7"])
    return (
        f"{random.randint(1, 223)}.{random.randint(0, 255)}."
        f"{random.randint(0, 255)}.{random.randint(1, 254)}"
    )


def random_status() -> int:
    codes, weights = zip(*STATUS_WEIGHTS.items())
    return random.choices(codes, weights=weights, k=1)[0]


def random_latency(status: int) -> float:
    # ошибки 5xx обычно медленнее (таймауты, ретраи)
    if status >= 500:
        return round(random.uniform(500, 3000), 2)
    if status == 429:
        return round(random.uniform(1, 5), 2)
    return round(max(0.5, random.gauss(45, 30)), 2)


def generate_record(base_time: datetime, offset_seconds: float) -> dict:
    status = random_status()
    ts = base_time + timedelta(seconds=offset_seconds)
    return {
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{ts.microsecond // 1000:03d}Z",
        "request_id": uuid.uuid4().hex[:16],
        "client_ip": random_ip(),
        "method": random.choice(METHODS),
        "path": random.choice(PATHS),
        "host": random.choice(HOSTS),
        "status_code": status,
        "latency_ms": random_latency(status),
        "upstream": random.choice(UPSTREAMS),
        "bytes_sent": random.randint(200, 50_000),
        "bytes_received": random.randint(50, 5_000),
        "user_agent": "synthetic-load-generator/1.0",
        "error": None if status < 400 else f"upstream returned {status}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic KuFlow-like JSONL logs")
    parser.add_argument("--count", type=int, default=1000, help="Number of records to generate")
    parser.add_argument("--out", type=str, default="logs/sample.jsonl", help="Output file path")
    parser.add_argument(
        "--duration-minutes",
        type=int,
        default=60,
        help="Spread records over this many minutes ending now",
    )
    args = parser.parse_args()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=args.duration_minutes)
    total_seconds = args.duration_minutes * 60

    with open(args.out, "w") as f:
        for _ in range(args.count):
            offset = random.uniform(0, total_seconds)
            record = generate_record(start_time, offset)
            f.write(json.dumps(record) + "\n")

    print(f"✅ Generated {args.count} records -> {args.out}")


if __name__ == "__main__":
    main()