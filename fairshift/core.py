"""Small shared utilities: deterministic IDs, seeded RNG streams, calendar helpers."""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Deterministic randomness
# ---------------------------------------------------------------------------
# Every component draws from its *own* stream derived from (seed, component, keys).
# Consequences:
#   * the same seed always reproduces the same data, byte for byte;
#   * changing how one component consumes randomness does not shift the
#     random numbers seen by any other component;
#   * per-record streams (e.g. attendance per employee+shift) mean that injecting
#     an anomaly does not change the attendance of unrelated records.
# Python's hash() is salted per process, so we never use it (or iterate sets of
# strings) anywhere that affects output order.


def derive_seed(seed: int, *parts) -> int:
    payload = "|".join([str(seed), *[str(p) for p in parts]]).encode()
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def rng_for(seed: int, *parts) -> random.Random:
    return random.Random(derive_seed(seed, *parts))


# ---------------------------------------------------------------------------
# ID conventions (from the brief)
# ---------------------------------------------------------------------------

def employee_id(n: int) -> str:
    return f"EMP-{n:06d}"


def team_id(n: int) -> str:
    return f"TEAM-{n:03d}"


def skill_id(n: int) -> str:
    return f"SKL-{n:03d}"


def shift_id(d: date, code: str) -> str:
    return f"SHIFT-{d.isoformat()}-{code}"


def attendance_id(emp_id: str, ts: datetime) -> str:
    return f"ATT-{emp_id}-{ts:%Y%m%dT%H%M%S}"


# Sequenced, year-scoped IDs. Assigned once, after generation, in chronological
# order of creation (see pipeline.finalize_ids) so that the ID sequence never
# reveals which records were injected as anomalies.
SEQUENCED_ID_FORMATS = {
    "A": ("ASG", 7),   # shift_assignment
    "AE": ("AEV", 7),  # assignment_event
    "L": ("LVE", 6),   # leave_request
    "LE": ("LEV", 6),  # leave_request_event
    "S": ("SWP", 6),   # swap_request
    "SE": ("SEV", 6),  # swap_request_event
}


def sequenced_id(kind: str, year: int, n: int) -> str:
    prefix, width = SEQUENCED_ID_FORMATS[kind]
    return f"{prefix}-{year}-{n:0{width}d}"


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def iso_week_label(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def at(d: date, hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss)


def hours_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0


def random_ts_between(rng: random.Random, a: datetime, b: datetime) -> datetime:
    """Uniform timestamp in [a, b], truncated to whole seconds."""
    if b <= a:
        return a.replace(microsecond=0)
    span = int((b - a).total_seconds())
    return (a + timedelta(seconds=rng.randint(0, span))).replace(microsecond=0)
