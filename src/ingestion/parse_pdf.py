"""PDF parsing using pypdf. Lightweight, pure-Python, no system dependencies.

We extract text page by page, then group lines into blocks. A line that looks
like a section heading (e.g. "A. Eligibility") starts a new section, and that
heading is propagated onto the blocks that follow it — so the chunker can build
citation paths later.

Run from project root:
    python -m src.ingestion.parse_pdf data/raw/uscis_f1_employment.pdf \
        --output data/processed/uscis_f1_employment.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader

# USCIS Policy Manual section labels look like "A.", "B.", "1.", "(a)".
SECTION_HEADING_RE = re.compile(r"^(?:[A-Z]\.|\d+\.|\([a-z]\))\s+\S")
MAX_HEADING_LEN = 120


@dataclass
class Block:
    text: str
    page_number: int | None
    section_heading: str | None  # propagated forward from the last heading seen
    block_type: str               # "Title" | "NarrativeText"


def _is_heading(line: str) -> bool:
    """A short line that matches the section-label pattern is treated as a heading."""
    return bool(SECTION_HEADING_RE.match(line)) and len(line) < MAX_HEADING_LEN


def _make_block(lines: list[str], page_no: int, heading: str | None) -> Block:
    return Block(
        text="\n".join(lines).strip(),
        page_number=page_no,
        section_heading=heading,
        block_type="NarrativeText",
    )


def parse(pdf_path: Path) -> list[Block]:
    """Parse a PDF into ordered blocks with section context attached.

    Strategy: walk the text linearly. Blank lines end a paragraph block;
    heading-looking lines update the 'current section' and are recorded as
    their own Title block. Every non-heading block carries the most recent
    heading so downstream chunking can cite it.
    """
    reader = PdfReader(str(pdf_path))
    blocks: list[Block] = []
    current_heading: str | None = None

    for page_index, page in enumerate(reader.pages):
        page_no = page_index + 1
        text = page.extract_text() or ""
        buffer: list[str] = []  # lines accumulating into the current block

        for raw_line in text.splitlines():
            line = raw_line.strip()

            # Blank line -> finish the current paragraph block.
            if not line:
                if buffer:
                    blocks.append(_make_block(buffer, page_no, current_heading))
                    buffer = []
                continue

            # Heading line -> flush previous text, then record the heading.
            if _is_heading(line):
                if buffer:
                    blocks.append(_make_block(buffer, page_no, current_heading))
                    buffer = []
                current_heading = line
                blocks.append(Block(
                    text=line,
                    page_number=page_no,
                    section_heading=current_heading,
                    block_type="Title",
                ))
                continue

            buffer.append(line)

        if buffer:
            blocks.append(_make_block(buffer, page_no, current_heading))

    # Drop any empty blocks that odd PDF spacing can produce.
    return [b for b in blocks if b.text]


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
    print(f"Parsed {len(blocks)} blocks -> {args.output}")

    # Quick sanity: show the first few section headings detected.
    seen: set[str] = set()
    for b in blocks:
        if b.section_heading and b.section_heading not in seen:
            seen.add(b.section_heading)
            print(f"  heading: {b.section_heading[:80]}")
            if len(seen) >= 5:
                break
    if not seen:
        print("  (no section headings detected — chunking will still work, "
              "but citations will be coarse)")


if __name__ == "__main__":
    main()
