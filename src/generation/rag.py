"""RAG generation with inline citations, post-generation self-check, and
timeline routing.

Flow of `generate_answer`:
  1. Classify intent. If the question is about computing specific dates /
     deadlines for an individual, route to the deterministic timeline engine
     (LLM understands the question, the rules engine does the date math).
  2. Otherwise run normal RAG: retrieve -> rerank -> generate -> self-check.

Design principle: the LLM never computes dates. It only (a) classifies intent
and (b) extracts the program end date from natural language. All date
arithmetic happens in src.rules.opt_timeline, which is deterministic.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date

from anthropic import Anthropic
from dotenv import load_dotenv

from src.retrieval.hybrid_search import Hit, hybrid_search
from src.retrieval.rerank import maybe_rerank
from src.rules.opt_timeline import TimelineInput, compute_timeline

load_dotenv()

ANTHROPIC = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
MIN_RELEVANCE = float(os.environ.get("MIN_RELEVANCE_SCORE", "0.35"))


GENERATION_SYSTEM = """You are an informational assistant for U.S. F-1 student visa, OPT, and STEM OPT questions.

Strict rules:
1. Answer ONLY using the numbered passages provided. If the passages do not contain the answer, say so explicitly — do not guess, do not use prior knowledge.
2. Every factual claim must be followed by a citation in the form [n] referring to a passage number.
3. If passages disagree, surface the disagreement rather than picking one.
4. Never compute dates or deadlines yourself — if the question requires date arithmetic, say "Use the timeline tool with your specific dates."
5. End every answer with: "This is informational only, not legal advice. Verify with your DSO."
6. Tone: clear, plain, ~150 words or less."""


VERIFICATION_SYSTEM = """You verify whether an answer is grounded in the cited passages.

Given an ANSWER and the PASSAGES it was based on, decide whether every factual
claim in the answer can be supported by one of the passages.

Respond with ONLY a JSON object — no code fences, no commentary:
{"supported": true, "unsupported_claims": []}

Guidance:
- Minor paraphrasing or summarizing of passage content counts as supported.
- The closing disclaimer sentence ("This is informational only...") is always
  supported — never flag it.
- Set "supported" to false only if a substantive factual claim genuinely cannot
  be found in any passage, and list those claims."""


INTENT_SYSTEM = """You classify a user's question about F-1 student visa / OPT.

Respond with ONLY a JSON object — no code fences, no commentary:
{"intent": "timeline"} or {"intent": "general"}

- "timeline": the question asks to compute specific calendar dates, deadlines,
  or filing windows for an individual — e.g. "when can I file for OPT",
  "what is my OPT application deadline", "when must I file my STEM extension".
- "general": questions about rules, eligibility, definitions, or how something
  works — e.g. "how long is post-completion OPT", "who can work off campus"."""


EXTRACT_SYSTEM = """Extract timeline parameters from a user's question about OPT.

Respond with ONLY a JSON object — no code fences, no commentary:
{"program_end_date": "YYYY-MM-DD", "is_stem_eligible": false}

- program_end_date: the student's program completion / graduation date if the
  question states one (in any format); otherwise null.
- is_stem_eligible: true only if the student indicates a STEM degree or asks
  about the STEM OPT extension; otherwise false."""


@dataclass
class Citation:
    n: int
    section_path: str
    publisher: str
    tier: int
    source_url: str


@dataclass
class Answer:
    mode: str               # "answered" | "timeline" | "needs_dates" | "refused"
    text: str
    citations: list[Citation]
    confidence: str         # "high" | "medium" | "low"
    debug: dict


def _format_passages(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{i+1}] ({hit.publisher}, Tier {hit.tier}, {hit.section_path})\n{hit.text}"
        for i, hit in enumerate(hits)
    )


def _call_llm(system: str, user: str, max_tokens: int = 600) -> str:
    """Call the LLM with a single user message."""
    msg = ANTHROPIC.messages.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()


def _extract_json(raw: str) -> dict | None:
    """Parse a JSON object out of an LLM response, tolerating code fences/prose."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


# --- Intent classification + timeline routing --------------------------------

def _classify_intent(question: str) -> str:
    """Return "timeline" or "general". Defaults to "general" on any uncertainty."""
    raw = _call_llm(INTENT_SYSTEM, question, max_tokens=50)
    data = _extract_json(raw)
    if data and data.get("intent") == "timeline":
        return "timeline"
    return "general"


def _extract_timeline_params(question: str) -> dict | None:
    """Pull {program_end_date, is_stem_eligible} from the question via the LLM."""
    raw = _call_llm(EXTRACT_SYSTEM, question, max_tokens=100)
    return _extract_json(raw)


def _format_timeline_answer(result, is_stem: bool) -> str:
    """Render a deterministic TimelineResult into readable text. No LLM here."""
    lines = ["## Your OPT Timeline (estimated)", "", result.summary, "",
             "Key dates and deadlines:"]
    for m in result.milestones:
        parts = []
        if m.earliest:
            parts.append(f"earliest {m.earliest.isoformat()}")
        if m.latest:
            parts.append(f"latest {m.latest.isoformat()}")
        when = "; ".join(parts) if parts else "see note"
        lines.append(f"- {m.label}: {when}  [{m.regulatory_citation}]")
        if m.notes:
            lines.append(f"    Note: {m.notes}")
    if not is_stem:
        lines.append("")
        lines.append("(If you hold an eligible STEM degree, ask again mentioning "
                      "STEM to also see the 24-month extension dates.)")
    lines.append("")
    lines.append("These dates are computed directly from the cited regulations. "
                 "USCIS may exercise discretion outside the regulatory window. "
                 "This is informational only, not legal advice. Verify with your DSO.")
    return "\n".join(lines)


def _answer_timeline(question: str) -> Answer:
    """Handle a timeline question: extract the date, run the rules engine."""
    params = _extract_timeline_params(question)
    end_date_str = params.get("program_end_date") if params else None

    if not end_date_str:
        return Answer(
            mode="needs_dates",
            text=(
                "To compute your OPT deadlines I need your program completion date. "
                "Please ask again and include it — for example: "
                '"I finish my program on 2026-12-18, when can I file for OPT?" '
                "This is informational only, not legal advice."
            ),
            citations=[],
            confidence="low",
            debug={"reason": "no_date_in_question", "params": params},
        )

    try:
        program_end = date.fromisoformat(str(end_date_str))
    except ValueError:
        return Answer(
            mode="needs_dates",
            text=(
                f"I couldn't read \"{end_date_str}\" as a valid date. Please ask again "
                "with a clear program completion date, e.g. 2026-12-18. "
                "This is informational only, not legal advice."
            ),
            citations=[],
            confidence="low",
            debug={"reason": "unparseable_date", "raw": end_date_str},
        )

    is_stem = bool(params.get("is_stem_eligible")) if params else False
    result = compute_timeline(TimelineInput(
        program_end_date=program_end,
        is_stem_eligible=is_stem,
    ))
    return Answer(
        mode="timeline",
        text=_format_timeline_answer(result, is_stem),
        citations=[],
        confidence="high",
        debug={"program_end_date": program_end.isoformat(), "is_stem_eligible": is_stem},
    )


# --- Self-check ---------------------------------------------------------------

def _verify(answer: str, passages: str) -> tuple[bool, list[str]]:
    """Ask the model whether the answer is grounded. Conservative on parse failure."""
    raw = _call_llm(
        VERIFICATION_SYSTEM,
        f"PASSAGES:\n{passages}\n\nANSWER:\n{answer}",
        max_tokens=300,
    )
    data = _extract_json(raw)
    if data is None:
        return False, [f"verifier output could not be parsed: {raw[:200]}"]
    return bool(data.get("supported")), list(data.get("unsupported_claims", []))


# --- Orchestration ------------------------------------------------------------

def generate_answer(question: str) -> Answer:
    # 0. Route date/deadline questions to the deterministic timeline engine.
    if _classify_intent(question) == "timeline":
        return _answer_timeline(question)

    # 1. Retrieve.
    raw_hits = hybrid_search(question, top_k=int(os.environ.get("RETRIEVAL_TOP_K", "20")))
    hits = maybe_rerank(question, raw_hits, top_k=int(os.environ.get("RERANK_TOP_K", "6")))

    if not hits:
        return Answer(
            mode="refused",
            text=(
                "I could not find authoritative passages addressing this question. "
                "Please consult your school's DSO or an immigration attorney. "
                "This is informational only, not legal advice."
            ),
            citations=[],
            confidence="low",
            debug={"reason": "no_hits"},
        )

    top_score = hits[0].score
    if top_score < MIN_RELEVANCE:
        return Answer(
            mode="refused",
            text=(
                "My sources don't clearly address this question. Please consult your DSO "
                "or an immigration attorney. This is informational only, not legal advice."
            ),
            citations=[],
            confidence="low",
            debug={"reason": "low_relevance", "top_score": top_score},
        )

    # 2. Generate.
    passages_block = _format_passages(hits)
    draft = _call_llm(
        GENERATION_SYSTEM,
        f"PASSAGES:\n{passages_block}\n\nQUESTION: {question}",
    )

    # 3. Verify.
    supported, unsupported = _verify(draft, passages_block)
    if not supported:
        return Answer(
            mode="refused",
            text=(
                "I drafted an answer but couldn't fully verify it against the source passages, "
                "so I'm declining to surface it. Please consult your DSO or an immigration attorney. "
                "This is informational only, not legal advice."
            ),
            citations=[],
            confidence="low",
            debug={"reason": "self_check_failed", "draft": draft, "unsupported": unsupported},
        )

    citations = [
        Citation(
            n=i + 1,
            section_path=h.section_path,
            publisher=h.publisher,
            tier=h.tier,
            source_url=h.source_url,
        )
        for i, h in enumerate(hits)
    ]

    # Confidence heuristic: high if all top-3 hits are Tier 1 and top_score > 0.6.
    tier1_count = sum(1 for h in hits[:3] if h.tier == 1)
    if tier1_count == 3 and top_score > 0.6:
        confidence = "high"
    elif tier1_count >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return Answer(
        mode="answered",
        text=draft,
        citations=citations,
        confidence=confidence,
        debug={"top_score": top_score, "n_hits": len(hits)},
    )


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Can an F-1 student work off-campus during the first academic year?"
    ans = generate_answer(q)
    print(f"\n=== MODE: {ans.mode}  CONFIDENCE: {ans.confidence} ===\n")
    print(ans.text)
    print()
    for c in ans.citations:
        print(f"  [{c.n}] {c.publisher} (Tier {c.tier}) — {c.section_path}")
        print(f"        {c.source_url}")
    if ans.mode == "refused":
        print("\n--- debug ---")
        for k, v in ans.debug.items():
            print(f"{k}: {v}")
