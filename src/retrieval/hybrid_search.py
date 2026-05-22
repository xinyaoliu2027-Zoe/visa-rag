"""Hybrid retrieval: combine dense (pgvector cosine) and lexical (pg_trgm) scores.

Approach is intentionally simple — Reciprocal Rank Fusion (RRF) of the two
ranked lists. For ~5k chunks this is more than enough; revisit when the corpus
grows beyond ~50k chunks (introduce real BM25 via Elasticsearch or Tantivy).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv()


@dataclass
class Hit:
    chunk_id: int
    text: str
    section_path: str
    publisher: str
    tier: int
    source_url: str
    page_start: int | None
    page_end: int | None
    score: float  # fused score, higher = better


_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(
            os.environ.get("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
        )
    return _model


def dense_search(conn, query_vec, k: int) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, text, section_path, publisher, tier, source_url,
                   page_start, page_end,
                   1 - (embedding <=> %s::vector) AS cosine_sim
            FROM visa.v_chunks_with_source
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vec, query_vec, k),
        )
        return cur.fetchall()


def lexical_search(conn, query: str, k: int) -> list[tuple]:
    """Trigram similarity as a cheap BM25-ish surrogate."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id, text, section_path, publisher, tier, source_url,
                   page_start, page_end,
                   similarity(text, %s) AS lex_score
            FROM visa.v_chunks_with_source
            WHERE text %% %s
            ORDER BY similarity(text, %s) DESC
            LIMIT %s
            """,
            (query, query, query, k),
        )
        return cur.fetchall()


def reciprocal_rank_fusion(
    dense: list[tuple],
    lexical: list[tuple],
    *,
    k_constant: int = 60,
) -> list[Hit]:
    """RRF: score = sum over rankers of 1 / (k + rank). Tier-1 sources get a small boost."""
    by_id: dict[int, dict] = {}
    for rank, row in enumerate(dense):
        chunk_id = row[0]
        by_id.setdefault(chunk_id, {"row": row, "score": 0.0})
        by_id[chunk_id]["score"] += 1.0 / (k_constant + rank + 1)
    for rank, row in enumerate(lexical):
        chunk_id = row[0]
        by_id.setdefault(chunk_id, {"row": row, "score": 0.0})
        by_id[chunk_id]["score"] += 1.0 / (k_constant + rank + 1)

    hits: list[Hit] = []
    for entry in by_id.values():
        row = entry["row"]
        score = entry["score"]
        # Mild boost for Tier-1 (authoritative) sources.
        tier_boost = 0.005 if row[4] == 1 else 0.0
        hits.append(Hit(
            chunk_id=row[0],
            text=row[1],
            section_path=row[2],
            publisher=row[3],
            tier=row[4],
            source_url=row[5],
            page_start=row[6],
            page_end=row[7],
            score=score + tier_boost,
        ))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def hybrid_search(query: str, top_k: int = 20) -> list[Hit]:
    model = get_model()
    query_vec = model.encode([query], normalize_embeddings=True)[0].tolist()

    db_url = os.environ["DATABASE_URL"]
    with psycopg.connect(db_url) as conn:
        register_vector(conn)
        dense = dense_search(conn, query_vec, top_k)
        lexical = lexical_search(conn, query, top_k)

    return reciprocal_rank_fusion(dense, lexical)[:top_k]


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "How long is post-completion OPT?"
    hits = hybrid_search(q, top_k=5)
    for h in hits:
        print(f"  [{h.tier}] {h.section_path}  score={h.score:.4f}")
        print(f"      {h.text[:120]}...")
