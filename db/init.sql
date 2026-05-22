-- Visa RAG schema. Run once against an empty Postgres 16 instance.
-- Assumes pgvector extension is available (use pgvector/pgvector:pg16 image).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for BM25-ish lexical search

CREATE SCHEMA IF NOT EXISTS visa;

-- A "document" is one logical source: e.g., USCIS Policy Manual Volume 2 Part F.
CREATE TABLE IF NOT EXISTS visa.documents (
    id              SERIAL PRIMARY KEY,
    source_url      TEXT NOT NULL,
    title           TEXT NOT NULL,
    publisher       TEXT NOT NULL,                  -- USCIS / SEVP / DOS / NAFSA / OISS
    tier            SMALLINT NOT NULL CHECK (tier IN (1, 2)),  -- 1=authoritative, 2=practitioner
    version_label   TEXT,
    downloaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sha256          TEXT NOT NULL,
    UNIQUE (source_url, sha256)
);

-- One row per chunk. The text + metadata is the "retrieval unit".
CREATE TABLE IF NOT EXISTS visa.chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES visa.documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    section_path    TEXT NOT NULL,
    page_start      INTEGER,
    page_end        INTEGER,
    text            TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    embedding       vector(768),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

-- HNSW index for dense vector (cosine) search.
-- NOTE: we deliberately use HNSW rather than IVFFlat. IVFFlat partitions
-- vectors into "lists" and probes only a few per query, so on a small corpus
-- most lists are empty and queries return too few — or zero — results.
-- HNSW has no such warm-up requirement and works well at any corpus size.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON visa.chunks USING hnsw (embedding vector_cosine_ops);

-- Trigram index for cheap lexical filtering.
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
    status          TEXT NOT NULL DEFAULT 'running',
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
