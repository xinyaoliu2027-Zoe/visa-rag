"""FastAPI entrypoint.

Run locally:
    uvicorn src.main:app --reload --port 8000

Endpoints:
    GET  /health                  liveness
    POST /ask     {question}      RAG answer
    POST /timeline {program_end_date, is_stem_eligible}  deterministic OPT math
"""

from __future__ import annotations

from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.generation.rag import Answer, generate_answer
from src.rules.opt_timeline import TimelineInput, compute_timeline

load_dotenv()

app = FastAPI(title="Visa RAG", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class CitationOut(BaseModel):
    n: int
    section_path: str
    publisher: str
    tier: int
    source_url: str


class AskResponse(BaseModel):
    mode: str
    text: str
    confidence: str
    citations: list[CitationOut]
    disclaimer: str = (
        "This is informational only, not legal advice. "
        "Verify with your DSO and a licensed immigration attorney before acting."
    )


class TimelineRequest(BaseModel):
    program_end_date: date
    is_stem_eligible: bool = False


class MilestoneOut(BaseModel):
    label: str
    earliest: date | None
    latest: date | None
    regulatory_citation: str
    notes: str = ""


class TimelineResponse(BaseModel):
    summary: str
    milestones: list[MilestoneOut]
    disclaimer: str = (
        "Dates are computed from the cited CFR sections. "
        "USCIS may exercise discretion outside the regulatory window. "
        "Verify with your DSO."
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    ans: Answer = generate_answer(req.question)
    return AskResponse(
        mode=ans.mode,
        text=ans.text,
        confidence=ans.confidence,
        citations=[
            CitationOut(
                n=c.n,
                section_path=c.section_path,
                publisher=c.publisher,
                tier=c.tier,
                source_url=c.source_url,
            )
            for c in ans.citations
        ],
    )


@app.post("/timeline", response_model=TimelineResponse)
def timeline(req: TimelineRequest) -> TimelineResponse:
    result = compute_timeline(TimelineInput(
        program_end_date=req.program_end_date,
        is_stem_eligible=req.is_stem_eligible,
    ))
    return TimelineResponse(
        summary=result.summary,
        milestones=[
            MilestoneOut(
                label=m.label,
                earliest=m.earliest,
                latest=m.latest,
                regulatory_citation=m.regulatory_citation,
                notes=m.notes,
            )
            for m in result.milestones
        ],
    )
