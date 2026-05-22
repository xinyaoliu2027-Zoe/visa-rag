"""Embed chunks and insert into pgvector.

Usage:
    python -m src.ingestion.embed_and_index \
        --jsonl data/processed/uscis_vol2_partf_ch5.jsonl \
        --prefix "Vol 2, Part F, Ch 5" \
        --source-url "https://www.uscis.gov/policy-manual/volume-2-part-f-chapter-5" \
        --title "USCIS Policy Manual: F-1 Students, Employment" \
        --publisher USCIS --tier 1
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src.ingestion.chunk import chunk, load_blocks

load_dotenv()


def get_model() -> SentenceTransformer:
    model_name = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
    print(f"Loading {model_name}...")
    return SentenceTransformer(model_name)


def embed_batch(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    # BGE expects L2-normalized embeddings for cosine similarity.
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--tier", type=int, required=True, choices=[1, 2])
    parser.add_argument("--source-pdf", type=Path,
                        help="Original PDF (for sha256). Defaults to None.")
    parser.add_argument("--version-label", default=None)
    args = parser.parse_args()

    blocks = load_blocks(args.jsonl)
    chunks = chunk(blocks, document_prefix=args.prefix)
    print(f"Embedding {len(chunks)} chunks")

    model = get_model()

    sha = file_sha256(args.source_pdf) if args.source_pdf else "unknown"

    db_url = os.environ["DATABASE_URL"]
    with psycopg.connect(db_url, autocommit=False) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # Upsert document row.
            cur.execute(
                """
                INSERT INTO visa.documents (source_url, title, publisher, tier, version_label, sha256)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_url, sha256) DO UPDATE SET title = EXCLUDED.title
                RETURNING id
                """,
                (args.source_url, args.title, args.publisher, args.tier, args.version_label, sha),
            )
            document_id = cur.fetchone()[0]

            # Open ingestion run.
            cur.execute(
                "INSERT INTO visa.ingestion_runs (document_id, status) VALUES (%s, 'running') RETURNING id",
                (document_id,),
            )
            run_id = cur.fetchone()[0]

            # Embed in batches of 32 to balance speed and memory.
            inserted = 0
            BATCH = 32
            for i in tqdm(range(0, len(chunks), BATCH), desc="embed+insert"):
                batch = chunks[i : i + BATCH]
                vecs = embed_batch(model, [c.text for c in batch])
                for c, v in zip(batch, vecs):
                    cur.execute(
                        """
                        INSERT INTO visa.chunks
                            (document_id, chunk_index, section_path, page_start, page_end,
                             text, token_count, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, chunk_index) DO NOTHING
                        """,
                        (
                            document_id,
                            c.chunk_index,
                            c.section_path,
                            c.page_start,
                            c.page_end,
                            c.text,
                            max(1, len(c.text) // 4),
                            v,
                        ),
                    )
                    inserted += 1

            cur.execute(
                "UPDATE visa.ingestion_runs SET status='completed', finished_at=NOW(), chunks_inserted=%s WHERE id=%s",
                (inserted, run_id),
            )
        conn.commit()

    print(f"Inserted {inserted} chunks for document_id={document_id}")


if __name__ == "__main__":
    main()
