"""Section-aware chunking.

Goals:
  1. Never break across sections unless a section exceeds the cap.
  2. Carry section_path metadata so the LLM can cite it.
  3. Keep chunks in the 400-600 token sweet spot; hard cap at 800.

A "section_path" is the canonical citation: e.g. "Vol 2, Part F, Ch 5, §A.2".
You'll need to encode the document hierarchy as a prefix when calling chunk().
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# Rough heuristic: 1 token ≈ 4 chars for English. Use real tokenizer in prod.
CHARS_PER_TOKEN = 4
TARGET_TOKENS = 500
HARD_CAP_TOKENS = 800
OVERLAP_TOKENS = 50


@dataclass
class Chunk:
    text: str
    section_path: str
    page_start: int | None
    page_end: int | None
    chunk_index: int  # ordinal within the document


def _estimate_tokens(s: str) -> int:
    return max(1, len(s) // CHARS_PER_TOKEN)


def _split_oversized(text: str, target: int, overlap: int) -> list[str]:
    """Split a too-long section on paragraph boundaries with overlap."""
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    buf: list[str] = []
    buf_tokens = 0

    for para in paragraphs:
        p_tokens = _estimate_tokens(para)
        if buf_tokens + p_tokens > target and buf:
            chunks.append("\n\n".join(buf))
            # Carry the tail for overlap.
            tail = buf[-1] if buf else ""
            buf = [tail] if _estimate_tokens(tail) <= overlap else []
            buf_tokens = _estimate_tokens(buf[0]) if buf else 0
        buf.append(para)
        buf_tokens += p_tokens

    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def chunk(
    blocks: list[dict],
    *,
    document_prefix: str,
) -> list[Chunk]:
    """Group blocks by section_heading, then size-control.

    `blocks` is a list of dicts matching parse_pdf.Block JSON shape.
    `document_prefix` is prepended to each section_path, e.g. "Vol 2, Part F, Ch 5".
    """
    # Group by section_heading (None heading → "Preamble").
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for b in blocks:
        key = b.get("section_heading") or "Preamble"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(b)

    chunks: list[Chunk] = []
    idx = 0
    for heading in order:
        group = groups[heading]
        text = "\n\n".join(b["text"] for b in group)
        pages = [b["page_number"] for b in group if b.get("page_number") is not None]
        page_start = min(pages) if pages else None
        page_end = max(pages) if pages else None

        section_path = f"{document_prefix}, §{heading}" if heading != "Preamble" else f"{document_prefix}, Preamble"

        if _estimate_tokens(text) <= HARD_CAP_TOKENS:
            chunks.append(Chunk(
                text=text,
                section_path=section_path,
                page_start=page_start,
                page_end=page_end,
                chunk_index=idx,
            ))
            idx += 1
        else:
            for piece in _split_oversized(text, TARGET_TOKENS, OVERLAP_TOKENS):
                chunks.append(Chunk(
                    text=piece,
                    section_path=section_path,
                    page_start=page_start,
                    page_end=page_end,
                    chunk_index=idx,
                ))
                idx += 1

    return chunks


def load_blocks(jsonl_path: Path) -> list[dict]:
    with jsonl_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--prefix", required=True, help='e.g. "Vol 2, Part F, Ch 5"')
    args = parser.parse_args()

    blocks = load_blocks(args.jsonl)
    chunks = chunk(blocks, document_prefix=args.prefix)
    print(f"Produced {len(chunks)} chunks")
    for c in chunks[:3]:
        print(f"  [{c.chunk_index}] {c.section_path}  ({_estimate_tokens(c.text)} tok)")
        print(f"      {c.text[:120]}...")
