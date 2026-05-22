"""RAG generation with inline citations and post-generation self-check.

Key design choices:
  - Refuse if rerank score of top hit < MIN_RELEVANCE_SCORE.
  - Force the model to emit [n] citations referring to passages.
  - After generation, ask the model to verify every claim is supported by
    a cited passage. If verification fails, fall back to refusal.

`generate_answer` returns a structured Answer so the API layer can render
citations and confidence labels.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from anthropic import Anthropic
from dotenv import load_dotenv

from src.retrieval.hybrid_search import Hit, hybrid_search
from src.retrieval.rerank import maybe_rerank

load_dotenv()

ANTHROPIC = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-3-5-sonnet-20241022")
MIN_RELEVANCE = float(os.environ.get("MIN_RELEVANCE_SCORE", "0.35"))


GENERATION_SYSTEM = """You are an informational assistant for U.S. F-1 student visa, OPT, and STEM OPT questions.

Strict rules:
1. Answer ONLY using the numbered passages provided. If the passages do not contain the answer, say so explicitly — do not guess, do not use prior knowledge.
2. Every factual claim must be followed by a citation in the form [n] referring to a passage number.
3. If passages disagree, surface the disagreement rather than picking one.
4. Never compute dates or deadlines yourself — if the question requires date arithmetic, say "Use the timeline tool with your specific dates."
5. End every answer with: "This is informational only, not legal advice. Verify with your DSO."
6. Tone: clear, plain, ~150 words or less."""


VERIFICATION_SYSTEM = """You verify whether an answer is fully grounded in the cited passages.

Given an ANSWER and the PASSAGES it was based on, return JSON of the form:
{"supported": true|false, "unsupported_claims": ["..."]}

A claim is unsupported if it cannot be directly read off one of the cited passages.
Citing prior knowledge counts as unsupported. Be strict."""


@dataclass
class Citation:
    n: int
    section_path: str
    publisher: str
    tier: int
    source_url: str


@dataclass
class Answer:
    mode: str               # "answered" | "refused" | "needs_timeline_tool"
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
    msg = ANTHROPIC.messages.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()


def _verify(answer: str, passages: str) -> tuple[bool, list[str]]:
    raw = _call_llm(
        VERIFICATION_SYSTEM,
        f"PASSAGES:\n{passages}\n\nANSWER:\n{answer}\n\nReturn JSON only.",
        max_tokens=300,
    )
    try:
        data = json.loads(raw)
        return bool(data.get("supported")), list(data.get("unsupported_claims", []))
    except (json.JSONDecodeError, AttributeError):
        # If we can't parse, be conservative — treat as unsupported.
        return False, ["verifier returned unparseable output"]


def generate_answer(question: str) -> Answer:
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
