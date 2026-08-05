-- =============================================================
-- Ingest manifest — tracks which source files have already been
-- loaded into raw.request_logs, so re-running the ingest script
-- never duplicates data.
-- =============================================================

CREATE TABLE IF NOT EXISTS raw.ingest_manifest (
    source_file   TEXT PRIMARY KEY,
    row_count     INTEGER NOT NULL,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);