"""Cohere reranker — promotes precision of the top-k.

Free tier gives 1000 calls/month. Disable rerank in dev by setting
COHERE_API_KEY="" and letting `maybe_rerank` pass through.
"""

from __future__ import annotations

import os

import cohere

from src.retrieval.hybrid_search import Hit


def maybe_rerank(query: str, hits: list[Hit], top_k: int = 6) -> list[Hit]:
    api_key = os.environ.get("COHERE_API_KEY", "").strip()
    if not api_key:
        return hits[:top_k]

    co = cohere.Client(api_key)
    docs = [h.text for h in hits]
    if not docs:
        return []

    rsp = co.rerank(
        query=query,
        documents=docs,
        top_n=top_k,
        model=os.environ.get("RERANK_MODEL", "rerank-english-v3.0"),
    )

    reranked: list[Hit] = []
    for r in rsp.results:
        h = hits[r.index]
        # Replace fused score with rerank relevance for downstream gating.
        reranked.append(Hit(
            chunk_id=h.chunk_id,
            text=h.text,
            section_path=h.section_path,
            publisher=h.publisher,
            tier=h.tier,
            source_url=h.source_url,
            page_start=h.page_start,
            page_end=h.page_end,
            score=float(r.relevance_score),
        ))
    return reranked
