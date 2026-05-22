"""Infer F-1 case signals from a user's question.

Used to SUGGEST profile updates as the user chats. This is detection only —
the user always confirms before anything is saved. The profile is a high-stakes
legal tracker, so there are deliberately no silent state changes.
"""

from __future__ import annotations

from src.generation.rag import _call_llm, _extract_json

_STAGE_LABELS = {
    "studying": "In F-1 study",
    "opt_filed": "OPT application filed",
    "opt_active": "On post-completion OPT",
    "stem_filed": "STEM extension filed",
    "stem_active": "On STEM OPT",
    "done": "Journey complete",
}

INFER_SYSTEM = """You read ONE message from an F-1 student and extract only explicit signals about where they are in the OPT process.

Respond with ONLY a JSON object — no code fences, no commentary:
{"stage": null, "program_end_date": null, "is_stem_eligible": null}

- stage: one of studying, opt_filed, opt_active, stem_filed, stem_active, done —
  ONLY if the message clearly states the student has reached that point.
  Examples: "I just filed my I-765" -> opt_filed; "I got my EAD" or
  "I'm on OPT now" -> opt_active; "I filed my STEM extension" -> stem_filed.
- program_end_date: "YYYY-MM-DD" if the message states their graduation or
  program completion date; otherwise null.
- is_stem_eligible: true if they mention a STEM degree or the STEM extension;
  otherwise null.

Be conservative — use null unless the message is explicit. Asking ABOUT a topic
is NOT a signal: "how do I file Form I-765?" does NOT mean they have filed."""


def detect_signals(question: str) -> dict:
    """Return explicit profile signals found in the question; {} if none."""
    raw = _call_llm(INFER_SYSTEM, question, max_tokens=80)
    data = _extract_json(raw)
    if not data:
        return {}
    out: dict = {}
    if data.get("stage") in _STAGE_LABELS:
        out["current_stage"] = data["stage"]
    if data.get("program_end_date"):
        out["program_end_date"] = str(data["program_end_date"])
    if data.get("is_stem_eligible") is True:
        out["is_stem_eligible"] = True
    return out


def build_suggestion(signals: dict, profile: dict | None) -> dict | None:
    """Compare detected signals to the saved profile.

    Returns a suggestion dict {message, changes} only when something genuinely
    differs from the saved profile. None means there is nothing to suggest.
    """
    if not profile or not signals:
        return None

    changes: dict = {}
    if ("current_stage" in signals
            and signals["current_stage"] != profile["current_stage"]):
        changes["current_stage"] = signals["current_stage"]
    if ("program_end_date" in signals
            and signals["program_end_date"] != profile["program_end_date"]):
        changes["program_end_date"] = signals["program_end_date"]
    if signals.get("is_stem_eligible") and not profile["is_stem_eligible"]:
        changes["is_stem_eligible"] = True

    if not changes:
        return None

    parts = []
    if "current_stage" in changes:
        parts.append(f'you\'ve reached "{_STAGE_LABELS[changes["current_stage"]]}"')
    if "program_end_date" in changes:
        parts.append(f'your program completion date is {changes["program_end_date"]}')
    if "is_stem_eligible" in changes:
        parts.append("you have a STEM-eligible degree")
    message = "It sounds like " + ", and ".join(parts) + "."
    return {"message": message, "changes": changes}
