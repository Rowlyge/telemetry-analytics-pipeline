-- =============================================================
-- Telemetry Analytics Pipeline — Initial schema
-- Raw -> Processed -> Curated layers
-- =============================================================

-- ---------------------------------------------------------------
-- Schemas
-- ---------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS processed;
CREATE SCHEMA IF NOT EXISTS curated;

-- ---------------------------------------------------------------
-- RAW layer
-- Append-only, stores the original JSON payload as-is.
-- Partitioned by day for easier retention / vacuum management.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.request_logs (
    ingest_id     BIGSERIAL,
    source_file   TEXT NOT NULL,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload       JSONB NOT NULL,
    PRIMARY KEY (ingest_id, ingested_at)
) PARTITION BY RANGE (ingested_at);

-- Default partition so inserts never fail even before a dated
-- partition is created (attach real partitions via a helper script
-- or pg_partman later).
CREATE TABLE IF NOT EXISTS raw.request_logs_default
    PARTITION OF raw.request_logs DEFAULT;

CREATE INDEX IF NOT EXISTS idx_raw_request_logs_ingested_at
    ON raw.request_logs (ingested_at);

-- ---------------------------------------------------------------
-- PROCESSED layer
-- Typed, cleaned, deduplicated data derived from raw.request_logs.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed.requests (
    request_id      TEXT PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL,
    client_ip       INET NOT NULL,
    method          TEXT NOT NULL,
    path            TEXT NOT NULL,
    host            TEXT,
    status_code     SMALLINT NOT NULL,
    latency_ms      NUMERIC(10, 2) NOT NULL,
    upstream        TEXT,
    bytes_sent      BIGINT,
    bytes_received  BIGINT,
    is_error        BOOLEAN GENERATED ALWAYS AS (status_code >= 400) STORED,
    ingest_id       BIGINT,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_processed_requests_ts
    ON processed.requests (ts);
CREATE INDEX IF NOT EXISTS idx_processed_requests_client_ip
    ON processed.requests (client_ip);
CREATE INDEX IF NOT EXISTS idx_processed_requests_path
    ON processed.requests (path);
CREATE INDEX IF NOT EXISTS idx_processed_requests_status
    ON processed.requests (status_code);

-- Quarantine table for rows that fail validation during transform.
CREATE TABLE IF NOT EXISTS processed.quarantine (
    quarantine_id   BIGSERIAL PRIMARY KEY,
    ingest_id       BIGINT,
    reason          TEXT NOT NULL,
    payload         JSONB NOT NULL,
    quarantined_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tracks the last raw.ingest_id processed by the transform step,
-- so the ETL can resume safely without reprocessing or skipping rows.
CREATE TABLE IF NOT EXISTS processed.watermark (
    source_name     TEXT PRIMARY KEY,
    last_ingest_id  BIGINT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO processed.watermark (source_name, last_ingest_id)
VALUES ('kuflow_default', 0)
ON CONFLICT (source_name) DO NOTHING;

-- ---------------------------------------------------------------
-- CURATED layer — analytical marts (created in separate files
-- under sql/marts/, this section left intentionally empty here).
-- ---------------------------------------------------------------