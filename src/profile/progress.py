"""Personalised progress view.

Given a saved profile, this computes:
  - where the user is in the F-1 -> OPT -> STEM journey (a stage tracker),
  - the single most important next action, with urgency, and
  - countdowns to upcoming deadlines.

Everything is deterministic and built on the opt_timeline rules engine — no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.rules.opt_timeline import TimelineInput, compute_timeline

# The journey in order. The third field marks STEM-only stages, which are
# dropped from the tracker for students who are not STEM-eligible.
_ALL_STAGES: list[tuple[str, str, bool]] = [
    ("studying", "In F-1 study", False),
    ("opt_filed", "OPT application filed", False),
    ("opt_active", "On post-completion OPT", False),
    ("stem_filed", "STEM extension filed", True),
    ("stem_active", "On STEM OPT", True),
    ("done", "Journey complete", False),
]


@dataclass
class StageView:
    key: str
    label: str
    status: str  # "done" | "current" | "upcoming"


@dataclass
class UpcomingDate:
    label: str
    date: str        # ISO format
    days_until: int


@dataclass
class ProgressView:
    current_stage: str
    stages: list[StageView]
    next_title: str
    next_detail: str
    next_urgency: str           # "info" | "action" | "warning"
    upcoming_dates: list[UpcomingDate]


def _stages_for(is_stem: bool) -> list[tuple[str, str]]:
    return [(k, lbl) for k, lbl, stem_only in _ALL_STAGES if is_stem or not stem_only]


def _key_dates(m: dict, is_stem: bool) -> list[tuple[str, date]]:
    """Curated, human-labelled key dates pulled from the timeline milestones."""
    items: list[tuple[str, date]] = []
    if m["opt_file_earliest"].earliest:
        items.append(("OPT filing window opens", m["opt_file_earliest"].earliest))
    if m["opt_file_latest"].latest:
        items.append(("OPT filing window closes", m["opt_file_latest"].latest))
    if m["opt_start_window"].latest:
        items.append(("Latest OPT start date", m["opt_start_window"].latest))
    if m["opt_end_latest"].latest:
        items.append(("Latest OPT end date", m["opt_end_latest"].latest))
    if is_stem and "stem_file_window" in m:
        if m["stem_file_window"].earliest:
            items.append(("STEM filing window opens", m["stem_file_window"].earliest))
        if m["stem_file_window"].latest:
            items.append(("STEM filing window closes", m["stem_file_window"].latest))
        if m["stem_end_latest"].latest:
            items.append(("Latest STEM OPT end date", m["stem_end_latest"].latest))
    return items


def _next_action(stage: str, m: dict, today: date, is_stem: bool) -> tuple[str, str, str]:
    """Return (title, detail, urgency) for the user's single most important next step."""
    file_open = m["opt_file_earliest"].earliest
    file_close = m["opt_file_latest"].latest
    opt_start_latest = m["opt_start_window"].latest

    if stage == "studying":
        if today < file_open:
            days = (file_open - today).days
            return (
                "OPT filing window not open yet",
                f"You can file Form I-765 for post-completion OPT starting "
                f"{file_open.isoformat()} (in {days} days). Filing earlier is not allowed.",
                "info",
            )
        if today <= file_close:
            days = (file_close - today).days
            return (
                "File your OPT application now",
                f"Your I-765 filing window is OPEN and closes {file_close.isoformat()} "
                f"({days} days left). File Form I-765 with USCIS and update your stage once filed.",
                "action",
            )
        return (
            "OPT filing window has closed",
            f"The I-765 filing window closed on {file_close.isoformat()}. "
            f"Contact your DSO right away to discuss your options.",
            "warning",
        )

    if stage == "opt_filed":
        return (
            "Waiting for your EAD",
            f"USCIS is processing your I-765. Post-completion OPT begins once you receive "
            f"your EAD; the latest your OPT can start is {opt_start_latest.isoformat()}.",
            "info",
        )

    if stage == "opt_active":
        if is_stem and "stem_file_window" in m:
            sw_open = m["stem_file_window"].earliest
            sw_close = m["stem_file_window"].latest
            return (
                "On OPT — plan your STEM extension",
                f"You're on post-completion OPT. File your 24-month STEM extension between "
                f"{sw_open.isoformat()} and {sw_close.isoformat()}, before your EAD expires. "
                f"Keep unemployment under 90 days.",
                "info",
            )
        return (
            "On post-completion OPT",
            "You're on post-completion OPT (up to 12 months). Keep total unemployment "
            "under 90 days.",
            "info",
        )

    if stage == "stem_filed":
        return (
            "Waiting for your STEM EAD",
            "USCIS is processing your STEM extension. If you filed on time, you may keep "
            "working for up to 180 days while it is pending.",
            "info",
        )

    if stage == "stem_active":
        return (
            "On STEM OPT",
            "You're on the 24-month STEM extension. The cumulative unemployment cap is "
            "150 days; your employer must keep E-Verify and reporting current.",
            "info",
        )

    if stage == "done":
        return ("Journey complete", "No upcoming OPT actions are being tracked.", "info")

    return ("—", "", "info")


def compute_progress(
    program_end_date: date,
    is_stem_eligible: bool,
    current_stage: str,
    today: date | None = None,
) -> ProgressView:
    today = today or date.today()
    timeline = compute_timeline(TimelineInput(
        program_end_date=program_end_date,
        is_stem_eligible=is_stem_eligible,
    ))
    m = {ms.key: ms for ms in timeline.milestones}

    # Stage tracker.
    stage_defs = _stages_for(is_stem_eligible)
    keys = [k for k, _ in stage_defs]
    current = current_stage if current_stage in keys else keys[0]
    current_idx = keys.index(current)
    stages = [
        StageView(
            key=k,
            label=lbl,
            status=("done" if i < current_idx
                    else "current" if i == current_idx
                    else "upcoming"),
        )
        for i, (k, lbl) in enumerate(stage_defs)
    ]

    # Upcoming deadlines (future only), soonest first.
    upcoming = [
        UpcomingDate(label=label, date=d.isoformat(), days_until=(d - today).days)
        for label, d in _key_dates(m, is_stem_eligible)
        if d >= today
    ]
    upcoming.sort(key=lambda u: u.days_until)

    title, detail, urgency = _next_action(current, m, today, is_stem_eligible)

    return ProgressView(
        current_stage=current,
        stages=stages,
        next_title=title,
        next_detail=detail,
        next_urgency=urgency,
        upcoming_dates=upcoming,
    )


if __name__ == "__main__":
    p = compute_progress(date(2026, 12, 18), is_stem_eligible=True, current_stage="studying")
    print("current:", p.current_stage)
    for s in p.stages:
        print(f"  [{s.status:8}] {s.label}")
    print(f"\nNEXT ({p.next_urgency}): {p.next_title}\n  {p.next_detail}\n")
    for u in p.upcoming_dates:
        print(f"  {u.date}  (in {u.days_until} days)  {u.label}")
