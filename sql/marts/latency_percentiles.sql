-- p95 / p99 латентности по каждому эндпоинту (path), плюс общий срез по всей системе.
DROP MATERIALIZED VIEW IF EXISTS curated.latency_percentiles;

CREATE MATERIALIZED VIEW curated.latency_percentiles AS
SELECT
    path,
    count(*)                                                          AS request_count,
    round(avg(latency_ms)::numeric, 2)                                 AS avg_ms,
    round((percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms))::numeric, 2) AS p50_ms,
    round((percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms))::numeric, 2) AS p95_ms,
    round((percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms))::numeric, 2) AS p99_ms,
    round(max(latency_ms)::numeric, 2)                                 AS max_ms
FROM processed.requests
GROUP BY path
ORDER BY p99_ms DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_latency_percentiles_path
    ON curated.latency_percentiles (path);