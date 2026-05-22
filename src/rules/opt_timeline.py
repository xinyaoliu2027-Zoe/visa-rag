"""Deterministic OPT / STEM OPT timeline math.

WHY THIS LIVES OUTSIDE THE LLM
------------------------------
LLMs misadd dates with shocking frequency, and OPT date math is high stakes
(miss a deadline, lose status). Every date-bearing rule encoded here cites the
CFR or USCIS Policy Manual section it implements; if regs change, update both
the constant and the citation in one place.

Each milestone also carries a stable `key` so other modules (e.g. the progress
view) can look up specific dates without string-matching the human label.

CAVEATS
-------
- These calculations assume standard post-completion OPT (no extension other
  than the 24-month STEM extension).
- USCIS sometimes accepts I-765 outside the strict window in practice; we
  encode the regulation, not USCIS's day-to-day discretion.
- ALWAYS pair output with a "verify with DSO" disclaimer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


# --- Regulatory constants -----------------------------------------------------
# 8 CFR §214.2(f)(11)(i)(B): I-765 can be filed up to 90 days before program
# end date, and up to 60 days after.
OPT_FILE_BEFORE_DAYS = 90
OPT_FILE_AFTER_DAYS = 60

# 8 CFR §214.2(f)(10)(ii)(A)(3): post-completion OPT is up to 12 months.
OPT_DURATION_DAYS = 365

# 8 CFR §214.2(f)(10)(ii)(E): 90 days unemployment allowed during initial OPT.
OPT_UNEMPLOYMENT_DAYS = 90

# 8 CFR §214.2(f)(10)(ii)(C)(2): 24-month STEM extension.
STEM_EXTENSION_DAYS = 24 * 30  # rough; USCIS counts months, not days
# Total unemployment during initial OPT + STEM = 150 days.
STEM_TOTAL_UNEMPLOYMENT_DAYS = 150


@dataclass
class TimelineInput:
    program_end_date: date           # last day of academic program
    today: date = date.today()
    has_existing_opt: bool = False   # if true, we treat program_end as OPT start anchor
    is_stem_eligible: bool = False


@dataclass
class TimelineMilestone:
    label: str
    earliest: date | None
    latest: date | None
    regulatory_citation: str
    notes: str = ""
    key: str = ""                    # stable identifier for programmatic lookup


@dataclass
class TimelineResult:
    inputs: TimelineInput
    milestones: list[TimelineMilestone]
    summary: str


def _fmt(d: date | None) -> str:
    return d.isoformat() if d else "N/A"


def compute_timeline(inp: TimelineInput) -> TimelineResult:
    program_end = inp.program_end_date

    file_window_start = program_end - timedelta(days=OPT_FILE_BEFORE_DAYS)
    file_window_end = program_end + timedelta(days=OPT_FILE_AFTER_DAYS)

    # OPT start date: chosen by applicant on I-765, must fall within 60 days
    # after program end. We surface that window — not a single date.
    opt_start_earliest = program_end
    opt_start_latest = program_end + timedelta(days=OPT_FILE_AFTER_DAYS)

    # OPT end window depends on chosen start; we show the latest-possible end.
    latest_opt_end = opt_start_latest + timedelta(days=OPT_DURATION_DAYS)

    milestones = [
        TimelineMilestone(
            key="opt_file_earliest",
            label="Earliest date you may file Form I-765 for post-completion OPT",
            earliest=file_window_start,
            latest=None,
            regulatory_citation="8 CFR §214.2(f)(11)(i)(B)",
        ),
        TimelineMilestone(
            key="opt_file_latest",
            label="Latest date you may file Form I-765",
            earliest=None,
            latest=file_window_end,
            regulatory_citation="8 CFR §214.2(f)(11)(i)(B)",
            notes="USCIS must receive the application by this date.",
        ),
        TimelineMilestone(
            key="opt_start_window",
            label="Allowed window for OPT start date you select on I-765",
            earliest=opt_start_earliest,
            latest=opt_start_latest,
            regulatory_citation="8 CFR §214.2(f)(11)(i)(B)",
        ),
        TimelineMilestone(
            key="opt_end_latest",
            label="Latest possible OPT end date (12 months from latest start)",
            earliest=None,
            latest=latest_opt_end,
            regulatory_citation="8 CFR §214.2(f)(10)(ii)(A)(3)",
        ),
    ]

    if inp.is_stem_eligible:
        stem_apply_earliest = latest_opt_end - timedelta(days=90)
        stem_apply_latest = latest_opt_end
        stem_end = latest_opt_end + timedelta(days=STEM_EXTENSION_DAYS)
        milestones.extend([
            TimelineMilestone(
                key="stem_file_window",
                label="STEM extension I-765 filing window",
                earliest=stem_apply_earliest,
                latest=stem_apply_latest,
                regulatory_citation="8 CFR §214.2(f)(10)(ii)(C)(2)",
                notes="Must file before initial OPT EAD expires.",
            ),
            TimelineMilestone(
                key="stem_end_latest",
                label="Latest possible STEM OPT end date",
                earliest=None,
                latest=stem_end,
                regulatory_citation="8 CFR §214.2(f)(10)(ii)(C)(2)",
            ),
            TimelineMilestone(
                key="unemployment_cap",
                label="Cumulative unemployment cap (initial + STEM)",
                earliest=None,
                latest=None,
                regulatory_citation="8 CFR §214.2(f)(10)(ii)(E)",
                notes=f"{STEM_TOTAL_UNEMPLOYMENT_DAYS} days total across initial + STEM OPT.",
            ),
        ])
    else:
        milestones.append(TimelineMilestone(
            key="unemployment_cap",
            label="Unemployment cap during initial OPT",
            earliest=None,
            latest=None,
            regulatory_citation="8 CFR §214.2(f)(10)(ii)(E)",
            notes=f"{OPT_UNEMPLOYMENT_DAYS} days during the 12-month initial OPT.",
        ))

    summary_lines = [
        f"Program end: {_fmt(program_end)}",
        f"File I-765 between {_fmt(file_window_start)} and {_fmt(file_window_end)}.",
        f"Choose OPT start in {_fmt(opt_start_earliest)} – {_fmt(opt_start_latest)}.",
    ]
    if inp.is_stem_eligible:
        summary_lines.append("STEM extension adds up to 24 months; file before EAD expires.")

    return TimelineResult(
        inputs=inp,
        milestones=milestones,
        summary="\n".join(summary_lines),
    )


if __name__ == "__main__":
    # Example matching the user's situation (Northwestern MSIT, Dec 2026).
    inp = TimelineInput(
        program_end_date=date(2026, 12, 18),  # placeholder; replace with real date
        is_stem_eligible=True,
    )
    result = compute_timeline(inp)
    print(result.summary)
    print()
    for m in result.milestones:
        print(f"- [{m.key}] {m.label}")
        if m.earliest:
            print(f"    earliest: {_fmt(m.earliest)}")
        if m.latest:
            print(f"    latest:   {_fmt(m.latest)}")
        print(f"    cite:     {m.regulatory_citation}")
        if m.notes:
            print(f"    notes:    {m.notes}")
