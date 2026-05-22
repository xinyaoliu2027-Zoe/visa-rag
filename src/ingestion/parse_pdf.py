"""PDF parsing using Unstructured. Preserves section headings so chunking can
key off them later.

Run from project root:
    python -m src.ingestion.parse_pdf data/raw/uscis_vol2_partf_ch5.pdf \
        --output data/processed/uscis_vol2_partf_ch5.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from unstructured.partition.pdf import partition_pdf

# USCIS Policy Manual section labels look like "A.", "B.", "1.", "(a)".
# This regex matches the start of a structural heading line.
SECTION_HEADING_RE = re.compile(r"^\s*(?:[A-Z]\.|\d+\.|\([a-z]\))\s+\S")


@dataclass
class Block:
    text: str
    page_number: int | None
    section_heading: str | None  # propagated forward from the last heading we saw
    block_type: str               # "Title" | "NarrativeText" | "ListItem" | ...


def parse(pdf_path: Path) -> list[Block]:
    """Parse a PDF into ordered blocks with section context attached.

    The trick: Unstructured returns elements without remembering which heading
    they fall under, so we walk linearly and propagate the most recent heading
    onto each non-heading block.
    """
    elements = partition_pdf(
        filename=str(pdf_path),
        strategy="hi_res",          # better for structured docs; slower
        infer_table_structure=False, # we don't need tables for policy text
    )

    blocks: list[Block] = []
    current_heading: str | None = None

    for el in elements:
        el_type = el.category if hasattr(el, "category") else type(el).__name__
        text = (el.text or "").strip()
        if not text:
            continue

        # Update heading state.
        if el_type == "Title" or SECTION_HEADING_RE.match(text):
            current_heading = text

        page = getattr(el.metadata, "page_number", None) if hasattr(el, "metadata") else None

        blocks.append(
            Block(
                text=text,
                page_number=page,
                section_heading=current_heading,
                block_type=el_type,
            )
        )

    return blocks


def write_jsonl(blocks: list[Block], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for b in blocks:
            f.write(json.dumps(asdict(b), ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    blocks = parse(args.pdf)
    write_jsonl(blocks, args.output)
    print(f"Parsed {len(blocks)} blocks → {args.output}")

    # Quick sanity: show first 3 headings encountered.
    seen: set[str] = set()
    for b in blocks:
        if b.section_heading and b.section_heading not in seen:
            seen.add(b.section_heading)
            print(f"  heading: {b.section_heading[:80]}")
            if len(seen) >= 5:
                break


if __name__ == "__main__":
    main()
