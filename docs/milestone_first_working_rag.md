# Milestone: First Working RAG Pipeline

**Date:** 2026-05-22

The first full end-to-end run of the Visa RAG system succeeded — a user question
flowed through the complete pipeline (retrieval → rerank → LLM generation →
self-check verification) and produced a structured, citation-grounded answer.

## Query

> When is an F-1 student allowed to work off campus?

## System output

```
=== MODE: answered  CONFIDENCE: high ===

## F-1 Off-Campus Employment

An F-1 student may work off campus in these situations:

**1. General Off-Campus Authorization**
After completing **one full academic year** in F-1 status and being in
**good academic standing**, USCIS may authorize part-time off-campus work. [1]

**2. Severe Economic Hardship**
If on-campus opportunities are unavailable or insufficient, or due to unforeseen
hardship (e.g., loss of financial aid, currency fluctuations, unexpected medical
bills), USCIS may authorize part-time off-campus work. [2]

**3. International Organization Sponsorship**
If offered employment by a recognized international organization. [5]

**Key Requirements for All Off-Campus Work:**
- DSO must recommend and endorse Form I-20 [2]
- Student must file Form I-765 [4]
- Student must **receive the EAD before starting work** [4]

EADs for economic hardship are granted in **1-year intervals**, not extending
past the program end date. [2]

---
*This is informational only, not legal advice. Verify with your DSO.*

  [1] USCIS (Tier 1) — USCIS Policy Manual, Vol 2, Part F, Ch 6, §B. Off-Campus Employment
  [2] USCIS (Tier 1) — USCIS Policy Manual, Vol 2, Part F, Ch 6, §1. Severe Economic Hardship
  [3] USCIS (Tier 1) — USCIS Policy Manual, Vol 2, Part F, Ch 6, §A. On-Campus Employment
  [4] USCIS (Tier 1) — USCIS Policy Manual, Vol 2, Part F, Ch 6, §2. Off-Campus Employment
  [5] USCIS (Tier 1) — USCIS Policy Manual, Vol 2, Part F, Ch 6, §D. F-1 Student Sponsored by an International Organization
  [6] USCIS (Tier 1) — USCIS Policy Manual, Vol 2, Part F, Ch 6, Preamble
```

## What this milestone proves

The complete vertical slice works: one source document (USCIS Policy Manual,
Volume 2, Part F, Chapter 6) was parsed, chunked, embedded, and stored in
pgvector, and the full query pipeline returns a grounded, cited answer.

- Hybrid retrieval (dense vectors + lexical) over pgvector
- Cohere reranking
- LLM answer generation with inline `[n]` citations
- Post-generation self-check verification
- Confidence scoring

## Debugging journey (the path to getting here)

Getting this first run working meant diagnosing and fixing a chain of issues —
each one a useful engineering lesson:

1. **Slow / stalled `torch` download during Docker build** — isolated torch into
   its own image layer, added pip cache mount + retry/timeout settings.
2. **`libGL.so.1` missing** — `unstructured`'s OpenCV dependency needed system
   libraries; added `libgl1` and `libglib2.0-0`.
3. **`pdfminer` version conflict inside `unstructured`** — replaced the heavy,
   fragile `unstructured` PDF parser with lightweight `pypdf`.
4. **Vector search returned 0 or too few results** — root cause was an IVFFlat
   index, which partitions vectors into lists and under-returns on a small
   corpus; switched to an HNSW index.
5. **Outdated model name (404)** — updated `LLM_MODEL` to a current model.
6. **Assistant-message prefill unsupported** — removed the prefill trick and
   relied on robust regex-based JSON extraction in the self-check.

## Next steps

- Ingest additional source documents (8 CFR §214.2(f), Form I-765 instructions,
  STEM OPT guidance).
- Data cleaning pass: strip webpage navigation noise, normalize ligatures
  (e.g. "Oﬀ" → "Off").
- Build the 100-question evaluation set.
- OPT/STEM timeline calculator, policy-update tracking, deployment.
