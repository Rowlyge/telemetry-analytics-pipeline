-- Error rate по каждому эндпоинту: доля запросов со статусом >= 400.
DROP MATERIALIZED VIEW IF EXISTS curated.error_rate_by_endpoint;

CREATE MATERIALIZED VIEW curated.error_rate_by_endpoint AS
SELECT
    path,
    count(*)                                              AS total_count,
    count(*) FILTER (WHERE is_error)                       AS error_count,
    count(*) FILTER (WHERE status_code >= 500)              AS server_error_count,
    count(*) FILTER (WHERE status_code >= 400 AND status_code < 500) AS client_error_count,
    round(
        100.0 * count(*) FILTER (WHERE is_error) / NULLIF(count(*), 0),
        2
    )                                                       AS error_rate_pct
FROM processed.requests
GROUP BY path
ORDER BY error_rate_pct DESC NULLS LAST;

CREATE UNIQUE INDEX IF NOT EXISTS idx_error_rate_by_endpoint_path
    ON curated.error_rate_by_endpoint (path);