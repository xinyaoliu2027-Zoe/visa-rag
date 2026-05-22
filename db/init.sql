-- Visa RAG schema. Run once against an empty Postgres 16 instance.
-- Assumes pgvector extension is available (use pgvector/pgvector:pg16 image).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for BM25-ish lexical search

CREATE SCHEMA IF NOT EXISTS visa;

-- A "document" is one logical source: e.g., USCIS Policy Manual Volume 2 Part F.
-- Different chapters of the same manual = different documents (for cleaner citation).
CREATE TABLE IF NOT EXISTS visa.documents (
    id              SERIAL PRIMARY KEY,
    source_url      TEXT NOT NULL,
    title           TEXT NOT NULL,
    publisher       TEXT NOT NULL,                  -- USCIS / SEVP / DOS / NAFSA / OISS
    tier            SMALLINT NOT NULL CHECK (tier IN (1, 2)),  -- 1=authoritative, 2=practitioner
    version_label   TEXT,                           -- e.g. "as of 2026-03-15"
    downloaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sha256          TEXT NOT NULL,                  -- of the source file, for change detection
    UNIQUE (source_url, sha256)
);

-- One row per chunk. The text + metadata is the "retrieval unit".
CREATE TABLE IF NOT EXISTS visa.chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES visa.documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,               -- ordinal within the document
    section_path    TEXT NOT NULL,                  -- "Vol 2, Part F, Ch 5, §A.2"
    page_start      INTEGER,
    page_end        INTEGER,
    text            TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    embedding       vector(768),                    -- BGE-base-en-v1.5 dimensionality
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

-- IVFFlat for dense ANN. Tune lists ~ sqrt(rows). For ~5k chunks, lists=64 is fine.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_cos
    ON visa.chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 64);

-- Trigram for cheap lexical filter (acts as light BM25 surrogate).
CREATE INDEX IF NOT EXISTS idx_chunks_text_trgm
    ON visa.chunks USING gin (text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_section_path
    ON visa.chunks (section_path);

-- Audit trail. Every ingestion run logs what was processed.
CREATE TABLE IF NOT EXISTS visa.ingestion_runs (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    document_id     INTEGER REFERENCES visa.documents(id),
    chunks_inserted INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running', -- running | completed | failed
    notes           TEXT
);

-- View used by the app to retrieve chunk text + document context in one query.
CREATE OR REPLACE VIEW visa.v_chunks_with_source AS
SELECT
    c.id              AS chunk_id,
    c.text            AS text,
    c.section_path    AS section_path,
    c.page_start      AS page_start,
    c.page_end        AS page_end,
    c.embedding       AS embedding,
    d.id              AS document_id,
    d.title           AS document_title,
    d.publisher       AS publisher,
    d.tier            AS tier,
    d.source_url      AS source_url,
    d.version_label   AS version_label
FROM visa.chunks c
JOIN visa.documents d ON d.id = c.document_id;

-- Smoke test (uncomment after your first ingestion run):
-- SELECT publisher, COUNT(*) FROM visa.v_chunks_with_source GROUP BY publisher;
