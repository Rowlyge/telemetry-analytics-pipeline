-- Топ клиентских IP по объёму трафика (bytes sent + received) и по числу запросов.
DROP MATERIALIZED VIEW IF EXISTS curated.top_ip_by_traffic;

CREATE MATERIALIZED VIEW curated.top_ip_by_traffic AS
SELECT
    client_ip,
    count(*)                                       AS request_count,
    sum(bytes_sent + bytes_received)                AS total_bytes,
    round(avg(latency_ms)::numeric, 2)               AS avg_latency_ms,
    count(*) FILTER (WHERE is_error)                 AS error_count
FROM processed.requests
GROUP BY client_ip
ORDER BY total_bytes DESC
LIMIT 100;

CREATE UNIQUE INDEX IF NOT EXISTS idx_top_ip_by_traffic_ip
    ON curated.top_ip_by_traffic (client_ip);