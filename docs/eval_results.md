# Evaluation Results

**Date:** 2026-05-22

## Setup

A seed evaluation set of 16 questions (`src/eval/golden_set.jsonl`) covering
three categories:

- **general** (8) — rule/eligibility questions answerable from the ingested docs
- **timeline** (4) — date/deadline questions, including one with no date given
- **out_of_scope** (4) — questions deliberately outside the F-1/OPT corpus

The harness (`src/eval/run_eval.py`) runs every question through
`generate_answer` and reports three metrics:

- **Routing accuracy** — did each question reach the correct mode?
- **Key-fact coverage** — do answers contain the expected facts?
- **Refusal rate** — are out-of-scope questions correctly refused?

## Run 1 — baseline

| Metric | Result |
|---|---|
| Routing accuracy | 14/16 = 88% |
| Key-fact coverage | 15/15 = 100% |
| Refusal on out-of-scope | 2/4 = 50% |

**Finding:** two out-of-scope questions — "What is the annual H-1B visa cap?"
and "How do I apply for a green card through marriage?" — were answered instead
of refused. Diagnosis: the embedding relevance score only filters out clearly
unrelated questions; immigration-adjacent questions retrieved tangentially
related passages, cleared the relevance threshold, and reached generation.

## Fix — answerability gate

Added `_can_answer()` to `rag.py`: after retrieval, an LLM reads the retrieved
passages and judges whether they actually contain the answer. If not, the
system refuses. This treats embedding similarity as a weak signal and adds a
content-based check.

## Run 2 — after the fix

| Metric | Result |
|---|---|
| Routing accuracy | 16/16 = 100% |
| Key-fact coverage | 15/15 = 100% |
| Refusal on out-of-scope | 4/4 = 100% |

No regressions on in-scope questions.

## Honest caveats

- 16 questions is a **seed set**. 100% here means "no failures in a small set I
  designed myself" — not "the system is perfect."
- The eval becomes meaningful as it grows toward ~100 questions, especially with
  adversarial and edge-case questions written to probe weak spots.
- Grading is deterministic substring matching on key facts; an LLM-as-judge
  grader would catch subtler correctness errors.

## Résumé-ready summary

> Built an evaluation harness measuring routing accuracy, key-fact coverage, and
> out-of-scope refusal rate. Diagnosed a refusal leak on topically-adjacent
> queries and added an LLM answerability gate, raising out-of-scope refusal from
> 50% to 100% with no in-scope regressions.
