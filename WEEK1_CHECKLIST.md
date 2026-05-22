# Week 1 Checklist — Visa RAG Project

> Goal of week 1: by end of Sunday, you should have (a) all official source PDFs downloaded and parseable, (b) a running Postgres + pgvector instance with the schema applied, (c) one document fully parsed and chunked into the database, and (d) a smoke test confirming you can retrieve chunks by keyword. **No LLM calls yet** — keep the loop tight.

---

## Day 1 (Mon) — Environment & accounts

- [ ] Install Docker Desktop (or OrbStack on macOS — faster)
- [ ] Create AWS account billing alert ($20 threshold) before doing anything else
- [ ] Sign up for Anthropic API ($5 free credit; you'll only use it later)
- [ ] Sign up for Cohere API (free trial gives 1000 reranker calls/month — plenty)
- [ ] Copy `.env.example` → `.env` and fill in `ANTHROPIC_API_KEY` (Cohere optional for now)
- [ ] `docker compose build` — this is the slow step (~5 min first time, downloads the embedding model)
- [ ] `docker compose up -d`
- [ ] `curl http://localhost:8000/health` → should return `{"status":"ok"}`

**Embedding decision:** start with `BAAI/bge-base-en-v1.5` running inside the container (free, baked into the image at build time). Switch to OpenAI `text-embedding-3-large` only if local quality is poor on regulatory text. Notes go in `eval/embedding_comparison.md` later.

---

## Day 2 (Tue) — Database

- [ ] Postgres is already running thanks to compose; verify: `docker compose ps` shows both services as healthy
- [ ] Connect: `docker compose exec postgres psql -U postgres -d postgres`
- [ ] Verify pgvector loaded: `SELECT * FROM pg_extension WHERE extname='vector';` returns a row
- [ ] Verify tables: `\dt visa.*` shows `documents`, `chunks`, `ingestion_runs`
- [ ] If init.sql didn't run (e.g., you previously had an old volume), force re-init: `docker compose down -v && docker compose up -d`
- [ ] Bonus: install pgAdmin or DBeaver and connect to `localhost:5432` for visual inspection

---

## Day 3 (Wed) — Data acquisition (the long day)

Download all sources to `data/raw/`. **Make a `data/sources.md` log file with URL + date + version for every file.** This audit trail matters for citation accuracy.

### Tier 1 — Authoritative (must-have)

- [ ] **USCIS Policy Manual, Volume 2, Part F** — Students (F-1, M-1)
  - https://www.uscis.gov/policy-manual/volume-2-part-f
  - Download each chapter as PDF using browser print-to-PDF
- [ ] **8 CFR §214.2(f)** — Federal regulation governing F-1 status
  - https://www.ecfr.gov/current/title-8/chapter-I/subchapter-B/part-214/section-214.2#p-214.2(f)
  - eCFR has a download button
- [ ] **SEVP Policy Guidance documents** (consolidated PDF)
  - https://www.ice.gov/sevis/schools (look for "Policy Guidance" links)
- [ ] **Form I-765 instructions** (current edition)
  - https://www.uscis.gov/i-765 → "Instructions for Form I-765 (PDF)"
- [ ] **STEM OPT Hub** — collect all linked PDFs from
  - https://studyinthestates.dhs.gov/stem-opt-hub

### Tier 2 — Practitioner / institutional (community knowledge)

- [ ] **Northwestern OISS** F-1 / OPT pages (save HTML → markdown)
- [ ] **NAFSA public advisor resources** (only the public-access portions)
- [ ] **Federal Register search**: keywords "F-1 student" + "OPT" — last 24 months
  - https://www.federalregister.gov/

### Verify ingestion-readiness

- [ ] Open three random PDFs and confirm they're text-extractable (not scanned images). If any are image-based, you'll need OCR (Tesseract).
- [ ] Spot-check: open USCIS Policy Manual Vol 2 Part F Chapter 5 (Employment) and confirm section numbering is visible — your chunker will key off these.

---

## Day 4 (Thu) — Parsing pipeline

The skeleton in `src/ingestion/parse_pdf.py` already implements `parse()` with section-heading propagation. Today is about running it and validating the output.

- [ ] Drop your PDFs into `./data/raw/` on the host (mounted into the container at `/app/data/raw/`)
- [ ] Run parsing inside the container:
      `docker compose exec app python -m src.ingestion.parse_pdf data/raw/uscis_vol2_partf_ch5.pdf --output data/processed/uscis_vol2_partf_ch5.jsonl`
- [ ] Inspect output: does it preserve section structure ("A. Eligibility", "B. Employment Authorization")? If not, tweak the strategy/regex in `parse_pdf.py`
- [ ] If parsing comes out as garbage, the PDF is image-based — see "When you get stuck" below

**Common gotcha:** Unstructured may not pick up USCIS's hierarchical section labels. If so, post-process: detect lines matching `^[A-Z]\.\s` as section starts and propagate the heading to subsequent blocks.

---

## Day 5 (Fri) — Section-aware chunking

- [ ] In `src/ingestion/chunk.py`: implement `chunk(blocks) -> List[Chunk]` where each Chunk has:
  - `text` (target 400–600 tokens, hard cap 800)
  - `section_path` (e.g., "Vol 2, Part F, Ch 5, §A.2")
  - `source_url`
  - `page_range`
- [ ] Rule: **never break mid-section unless the section exceeds the cap.** For oversized sections, split on paragraph boundaries with 50-token overlap.
- [ ] Run on chapter 5; expect roughly 40–80 chunks
- [ ] Eyeball 5 random chunks: does each one make sense as a standalone passage? Does `section_path` look correct?

---

## Day 6 (Sat) — Embed and index

`src/ingestion/embed_and_index.py` is already wired up. Today: run it and verify the database state.

- [ ] Run inside the container:
      `docker compose exec app python -m src.ingestion.embed_and_index --jsonl data/processed/uscis_vol2_partf_ch5.jsonl --prefix "Vol 2, Part F, Ch 5" --source-url "https://www.uscis.gov/policy-manual/volume-2-part-f-chapter-5" --title "USCIS Policy Manual: F-1 Students, Employment" --publisher USCIS --tier 1`
- [ ] Verify count in DB matches chunk count: `docker compose exec postgres psql -U postgres -d postgres -c "SELECT COUNT(*) FROM visa.chunks;"`
- [ ] Lexical smoke test: `... -c "SELECT section_path FROM visa.chunks WHERE text ILIKE '%practical training%' LIMIT 5;"`
- [ ] Vector smoke test: `docker compose exec app python -m src.retrieval.hybrid_search "How long is post-completion OPT?"` — top-3 results should mention 12 months

---

## Day 7 (Sun) — Documentation + review

- [ ] Update `data/sources.md` with everything you downloaded and where it came from
- [ ] Take a screenshot of your pgAdmin showing the populated `chunks` table → save as `docs/week1_evidence.png`
- [ ] Write a 1-paragraph reflection in `JOURNAL.md` answering: what surprised you? what's the biggest unknown going into week 2?
- [ ] Bonus: if there's time, parse one more chapter so you have ~100 chunks total

---

## Definition of done (Week 1)

You can finish week 1 with confidence if all three are true:

1. `SELECT COUNT(*) FROM visa.chunks` returns ≥ 40
2. A cosine-similarity query against the embedded chunks returns plausibly relevant results for at least 3 hand-picked queries
3. `data/sources.md` documents every PDF's URL, date downloaded, and version

If any of the three is failing by end of Sunday, **don't push forward into week 2** — fix it first. Week 2 builds on this foundation and silent bugs here will haunt you.

---

## When you get stuck

| Symptom | First thing to try |
|---|---|
| PDF parses as garbage / scrambled text | The PDF is image-based or has unusual encoding — try Unstructured with `strategy="hi_res"`, or fall back to LlamaParse |
| pgvector can't be installed | Use the `pgvector/pgvector:pg16` Docker image instead of native install |
| Embedding model OOM on your laptop | Switch to `bge-small-en-v1.5` (lower quality but runs anywhere) |
| Chunks ignore section hierarchy | Your parser lost the heading metadata — post-process the JSONL to propagate section labels manually |
| Cosine similarity returns nonsense | Confirm you normalize embeddings before insert AND before query (BGE expects L2-normalized vectors) |

Don't burn more than 90 minutes on one of these — post in r/LocalLLaMA or ask Claude / ChatGPT with the actual error message.
