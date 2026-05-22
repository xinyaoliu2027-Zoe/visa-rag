"""Storage for the user's F-1 case profile.

This is a single-profile design: one row in visa.user_profiles, keyed id = 1
and upserted. Multi-user accounts / auth are a deliberate future step — the
table and these functions would gain a user id at that point.
"""

from __future__ import annotations

import os
from datetime import date

import psycopg
from dotenv import load_dotenv

load_dotenv()


def _conn():
    return psycopg.connect(os.environ["DATABASE_URL"])


def get_profile() -> dict | None:
    """Return the saved profile as a dict, or None if none has been saved."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT program_end_date, is_stem_eligible, current_stage "
            "FROM visa.user_profiles WHERE id = 1"
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "program_end_date": row[0].isoformat(),
        "is_stem_eligible": row[1],
        "current_stage": row[2],
    }


def save_profile(
    program_end_date: date,
    is_stem_eligible: bool,
    current_stage: str,
) -> dict:
    """Insert or update the single profile row, then return it."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO visa.user_profiles
                (id, program_end_date, is_stem_eligible, current_stage, updated_at)
            VALUES (1, %s, %s, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                program_end_date = EXCLUDED.program_end_date,
                is_stem_eligible = EXCLUDED.is_stem_eligible,
                current_stage    = EXCLUDED.current_stage,
                updated_at       = NOW()
            """,
            (program_end_date, is_stem_eligible, current_stage),
        )
        conn.commit()
    return get_profile()
