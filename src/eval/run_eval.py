"""Evaluation harness for the Visa RAG system.

Runs every question in golden_set.jsonl through generate_answer and reports
three metrics:

  - Routing accuracy   — did each question reach the correct mode
                         (answered / timeline / needs_dates / refused)?
  - Key-fact coverage  — do answered/timeline answers contain the facts they
                         should (substring check against expected key_facts)?
  - Refusal rate       — are out-of-scope questions correctly refused?

Run from the project root:
    docker compose exec app python -m src.eval.run_eval

Detailed per-question results are written to data/eval_last_run.json so you can
inspect exactly which questions failed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.generation.rag import generate_answer

GOLDEN_SET = Path(__file__).parent / "golden_set.jsonl"
RESULTS_OUT = Path("data/eval_last_run.json")


def load_golden() -> list[dict]:
    with GOLDEN_SET.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def grade(item: dict, answer) -> dict:
    """Score one answer against its golden entry. Pure, deterministic checks."""
    facts = item.get("key_facts", [])
    text_low = answer.text.lower()
    missing = [f for f in facts if f.lower() not in text_low]
    return {
        "id": item["id"],
        "category": item["category"],
        "question": item["question"],
        "expected_mode": item["expected_mode"],
        "actual_mode": answer.mode,
        "mode_ok": answer.mode == item["expected_mode"],
        "facts_total": len(facts),
        "facts_found": len(facts) - len(missing),
        "missing_facts": missing,
    }


def main() -> None:
    golden = load_golden()
    print(f"Running {len(golden)} eval questions "
          f"(this calls the LLM several times per question — a few minutes)...\n")

    rows: list[dict] = []
    for item in golden:
        t0 = time.time()
        answer = generate_answer(item["question"])
        elapsed = round(time.time() - t0, 1)
        row = grade(item, answer)
        row["latency_s"] = elapsed
        rows.append(row)

        mark = "PASS" if row["mode_ok"] else "FAIL"
        facts = (f"facts {row['facts_found']}/{row['facts_total']}"
                 if row["facts_total"] else "")
        print(f"  {mark}  [{row['id']:<4}] {row['actual_mode']:<11} "
              f"(want {row['expected_mode']:<11}) {facts}  {elapsed}s")

    # --- Metrics ---
    total = len(rows)
    mode_ok = sum(1 for r in rows if r["mode_ok"])

    fact_rows = [r for r in rows if r["facts_total"] > 0]
    facts_found = sum(r["facts_found"] for r in fact_rows)
    facts_total = sum(r["facts_total"] for r in fact_rows)

    oos = [r for r in rows if r["category"] == "out_of_scope"]
    oos_refused = sum(1 for r in oos if r["actual_mode"] == "refused")

    print("\n=== METRICS ===")
    print(f"Routing accuracy:        {mode_ok}/{total} = {mode_ok / total:.0%}")
    if facts_total:
        print(f"Key-fact coverage:       {facts_found}/{facts_total} "
              f"= {facts_found / facts_total:.0%}")
    if oos:
        print(f"Refusal on out-of-scope: {oos_refused}/{len(oos)} "
              f"= {oos_refused / len(oos):.0%}")

    failures = [r for r in rows if not r["mode_ok"] or r["missing_facts"]]
    if failures:
        print(f"\n{len(failures)} item(s) to review:")
        for r in failures:
            issues = []
            if not r["mode_ok"]:
                issues.append(f"mode {r['actual_mode']} != {r['expected_mode']}")
            if r["missing_facts"]:
                issues.append(f"missing facts {r['missing_facts']}")
            print(f"  [{r['id']}] {r['question']}")
            print(f"        {'; '.join(issues)}")
    else:
        print("\nAll items passed.")

    RESULTS_OUT.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_OUT.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nDetailed results saved to {RESULTS_OUT}")


if __name__ == "__main__":
    main()
