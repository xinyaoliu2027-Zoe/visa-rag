"""FastAPI entrypoint.

Run locally:
    uvicorn src.main:app --reload --port 8000

Endpoints:
    GET  /                        web UI
    GET  /health                  liveness
    POST /ask     {question}      RAG answer
    POST /timeline {program_end_date, is_stem_eligible}  deterministic OPT math
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

WEB_DIR = Path(__file__).parent / "web"

from src.generation.rag import Answer, generate_answer
from src.profile.infer import build_suggestion, detect_signals
from src.profile.progress import compute_progress
from src.profile.store import get_profile, save_profile
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
    profile_suggestion: dict | None = None
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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the web UI. Read on each request so edits show without a restart."""
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    ans: Answer = generate_answer(req.question)

    # If the user has a profile, check whether this message reveals a case
    # update worth suggesting (detection only — the user confirms in the UI).
    profile = get_profile()
    suggestion = None
    if profile is not None:
        suggestion = build_suggestion(detect_signals(req.question), profile)

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
        profile_suggestion=suggestion,
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


# --- User profile & progress -------------------------------------------------

VALID_STAGES = {"studying", "opt_filed", "opt_active",
                "stem_filed", "stem_active", "done"}


class ProfileRequest(BaseModel):
    program_end_date: date
    is_stem_eligible: bool = False
    current_stage: str = "studying"


@app.get("/profile")
def read_profile() -> dict:
    """Return the saved F-1 case profile, if any."""
    profile = get_profile()
    return {"has_profile": profile is not None, "profile": profile}


@app.put("/profile")
def write_profile(req: ProfileRequest) -> dict:
    """Create or update the user's F-1 case profile."""
    stage = req.current_stage if req.current_stage in VALID_STAGES else "studying"
    profile = save_profile(req.program_end_date, req.is_stem_eligible, stage)
    return {"has_profile": True, "profile": profile}


@app.get("/progress")
def read_progress() -> dict:
    """Return the personalised progress view computed from the saved profile."""
    profile = get_profile()
    if profile is None:
        return {"has_profile": False}
    prog = compute_progress(
        program_end_date=date.fromisoformat(profile["program_end_date"]),
        is_stem_eligible=profile["is_stem_eligible"],
        current_stage=profile["current_stage"],
    )
    return {"has_profile": True, "progress": asdict(prog)}
