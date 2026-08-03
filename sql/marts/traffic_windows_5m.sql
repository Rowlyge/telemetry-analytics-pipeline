-- 5-минутные окна трафика: RPS, p95 latency, error count, и сравнение
-- с предыдущим окном через LAG (window function).
DROP MATERIALIZED VIEW IF EXISTS curated.traffic_windows_5m;

CREATE MATERIALIZED VIEW curated.traffic_windows_5m AS
WITH bucketed AS (
    SELECT
        date_trunc('hour', ts)
            + (floor(date_part('minute', ts) / 5) * interval '5 minute') AS window_start,
        latency_ms,
        is_error
    FROM processed.requests
),
aggregated AS (
    SELECT
        window_start,
        count(*)                                                          AS request_count,
        round((percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms))::numeric, 2) AS p95_ms,
        count(*) FILTER (WHERE is_error)                                   AS error_count
    FROM bucketed
    GROUP BY window_start
)
SELECT
    window_start,
    request_count,
    p95_ms,
    error_count,
    round(100.0 * error_count / NULLIF(request_count, 0), 2)               AS error_rate_pct,
    LAG(request_count) OVER (ORDER BY window_start)                        AS prev_request_count,
    request_count - LAG(request_count) OVER (ORDER BY window_start)        AS request_count_delta,
    round(
        AVG(request_count) OVER (
            ORDER BY window_start
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    )                                                                      AS request_count_3window_avg
FROM aggregated
ORDER BY window_start;

CREATE UNIQUE INDEX IF NOT EXISTS idx_traffic_windows_5m_window_start
    ON curated.traffic_windows_5m (window_start);