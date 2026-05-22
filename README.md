# Visa RAG — Informational Assistant for F-1 / OPT / STEM OPT

> **Not legal advice.** Informational only. Always verify with your school's DSO and consult a licensed immigration attorney for legal decisions.

A retrieval-augmented assistant for international students navigating F-1, OPT, and STEM OPT regulations. The system answers questions only when it can cite authoritative sources (USCIS Policy Manual, 8 CFR, SEVP guidance, Federal Register), refuses out-of-scope questions, and uses a deterministic rules engine — not the LLM — for any date or window calculation.

## Design pillars

1. **Citation or refusal.** Every claim ties to a passage; no source → no answer.
2. **Two-tier sources.** Authoritative (USCIS / 8 CFR / SEVP) vs. practitioner (NAFSA, OISS). Answers always identify which tier is being cited.
3. **Rules out of LLM.** Date arithmetic (OPT windows, STEM extension cutoffs, unemployment counters) lives in deterministic Python, not in the model.
4. **Post-generation verification.** Every answer is re-checked against retrieved passages; low confidence → refusal.

## Architecture

```
[User Question]
      │
      ▼
[Profile + intent classifier] ──► is this a date/window question?
      │                                      │
      │                                      ▼
      │                            [Rules engine] ──► deterministic answer
      ▼
[Hybrid retrieval]  (BM25 + dense)
      │
      ▼
[Cohere reranker]
      │
      ▼
[LLM generation with inline citations]
      │
      ▼
[Self-check verifier] ──► if unsupported, fall back to refusal
      │
      ▼
[Answer + citations + tier labels]
```

## Project layout

```
visa_rag/
├── README.md                    # this file
├── WEEK1_CHECKLIST.md           # day-by-day week 1 plan
├── requirements.txt
├── .env.example
├── .gitignore
├── db/
│   └── init.sql                 # pgvector schema
├── src/
│   ├── main.py                  # FastAPI entrypoint
│   ├── ingestion/
│   │   ├── parse_pdf.py         # Unstructured-based PDF parsing
│   │   ├── chunk.py             # section-aware chunking
│   │   └── embed_and_index.py   # embed + insert into pgvector
│   ├── retrieval/
│   │   ├── hybrid_search.py     # BM25 + dense fusion
│   │   └── rerank.py            # Cohere rerank
│   ├── generation/
│   │   └── rag.py               # answer with citation + self-check
│   └── rules/
│       └── opt_timeline.py      # deterministic OPT/STEM math
├── eval/
│   └── golden_set.jsonl         # 100-question test set (you build this)
├── data/
│   ├── raw/                     # downloaded PDFs (gitignored)
│   ├── processed/               # parsed JSONL (gitignored)
│   └── sources.md               # provenance log
└── docs/
    └── architecture.png         # add later
```

## Getting started

See **WEEK1_CHECKLIST.md** for the day-by-day plan. The TL;DR:

```bash
cd visa_rag
cp .env.example .env                 # fill in ANTHROPIC_API_KEY, optionally COHERE_API_KEY
docker compose up -d                 # start postgres (with schema auto-applied) + app
docker compose logs -f app           # tail logs; wait for "Uvicorn running on ..."
curl http://localhost:8000/health    # → {"status":"ok"}
```

The Postgres container auto-runs `db/init.sql` on first start (only when the
data volume is empty). The app container hot-reloads when you edit `./src`.

To run ingestion scripts inside the container:

```bash
docker compose exec app python -m src.ingestion.parse_pdf \
    data/raw/uscis_vol2_partf_ch5.pdf \
    --output data/processed/uscis_vol2_partf_ch5.jsonl

docker compose exec app python -m src.ingestion.embed_and_index \
    --jsonl data/processed/uscis_vol2_partf_ch5.jsonl \
    --prefix "Vol 2, Part F, Ch 5" \
    --source-url "https://www.uscis.gov/policy-manual/volume-2-part-f-chapter-5" \
    --title "USCIS Policy Manual: F-1 Students, Employment" \
    --publisher USCIS --tier 1
```

Reset everything (drops the database):

```bash
docker compose down -v
```

### Working without Docker

If you'd rather not use Docker, you can still run the stack natively:

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
# Use a local Postgres or a one-off container for just the DB:
docker run -d --name visa_pg -e POSTGRES_PASSWORD=dev -p 5432:5432 \
  -v "$PWD/db/init.sql:/docker-entrypoint-initdb.d/01_init.sql:ro" \
  pgvector/pgvector:pg16
uvicorn src.main:app --reload
```

## Status

Week 1 of 10 — skeleton + ingestion.
