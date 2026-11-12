"""Run configuration: scale presets and business-policy parameters.

Every number that drives a business rule lives here so that it is documented in
one place, printed into the run manifest, and identical between the starter and
full datasets (only *scale* changes between them, never *rules*).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace, asdict
from datetime import date, timedelta

DEFAULT_SEED = 20261022
GENERATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class Scale:
    name: str
    employees: int
    teams: int
    start_date: date
    days: int
    leave_requests: int
    swap_requests: int
    manual_reassignments: int
    anomalies_per_type: int

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.days - 1)

    def validate(self) -> None:
        if self.teams < 2:
            raise ValueError("need at least 2 teams (cross-team cover needs a sister team)")
        if self.employees < self.teams * 10:
            raise ValueError("need at least 10 employees per team on average")
        if self.days < 14:
            raise ValueError("need at least 14 days so weekly rules are meaningful")
        if self.leave_requests <= self.anomalies_per_type:
            raise ValueError("leave_requests must exceed anomalies_per_type")


SCALES: dict[str, Scale] = {
    # Small, fast dataset committed to the repo for reviewers.
    "starter": Scale("starter", employees=120, teams=6, start_date=date(2026, 1, 1), days=28,
                     leave_requests=100, swap_requests=60, manual_reassignments=10,
                     anomalies_per_type=3),
    # The volume requested in the brief: 2,000 employees, 100 teams, 90 days, 5,000 leaves.
    "full": Scale("full", employees=2000, teams=100, start_date=date(2026, 1, 1), days=90,
                  leave_requests=5000, swap_requests=1500, manual_reassignments=150,
                  anomalies_per_type=20),
}


@dataclass(frozen=True)
class Policy:
    # --- Contracts and working-time rules (hours per ISO week) ---
    ft_contract_hours: float = 40.0
    ft_max_hours: float = 48.0           # overtime cap: contract + 8h
    pt_contract_hours: float = 24.0
    pt_max_hours: float = 32.0
    part_time_share: float = 0.15
    night_ineligible_share: float = 0.12  # e.g. medical / personal restriction
    min_rest_hours: float = 11.0          # between end of one shift and start of next
    max_consecutive_days: int = 6

    # --- Leave policy ---
    team_leave_concurrency_ratio: float = 0.15  # max share of rota on planned leave per day
    min_leave_notice_days: int = 3              # planned leave (not sick)
    max_personal_days: float = 3.0              # per employee in the planning window
    max_unpaid_days: float = 10.0               # per request
    leave_cancel_rate: float = 0.06

    # --- Scheduling / operations ---
    publication_lead_days: int = 7      # week W is published (Mon of W - 7 days) at 12:00
    swap_min_notice_hours: float = 24.0
    callin_min_notice_hours: float = 2.0
    topup_probability: float = 0.6      # chance a manager manually tops up a planning gap
    swap_withdraw_rate: float = 0.04

    # --- Staffing: minimum headcount as share of team rota, per day type & shift ---
    staffing_ratio: dict = field(default_factory=lambda: {
        "WEEKDAY": {"A": 0.22, "B": 0.22, "C": 0.12},
        "WEEKEND": {"A": 0.17, "B": 0.17, "C": 0.10},
        "HOLIDAY": {"A": 0.15, "B": 0.15, "C": 0.10},
    })
    min_total_headcount: int = 2
    core_skill_share: float = 0.4       # share of TOTAL that must hold the team's core skill
    peak_uplift_departments: tuple = ("OUTBOUND",)
    peak_uplift_headcount: int = 1      # extra A/B weekday headcount from the uplift date

    # --- Attendance behaviour (probabilities per attended shift) ---
    no_show_rate: float = 0.012
    late_rate: float = 0.04
    stay_late_rate: float = 0.08
    early_departure_rate: float = 0.015
    missing_clock_out_rate: float = 0.006

    def peak_uplift_from(self, scale: Scale) -> date:
        return scale.start_date + timedelta(days=(scale.days * 2) // 3)


def resolve_scale(name: str, **overrides) -> Scale:
    if name not in SCALES:
        raise ValueError(f"unknown scale '{name}', choose from {sorted(SCALES)}")
    clean = {k: v for k, v in overrides.items() if v is not None}
    if "start_date" in clean and isinstance(clean["start_date"], str):
        clean["start_date"] = date.fromisoformat(clean["start_date"])
    scale = replace(SCALES[name], **clean)
    if clean:
        scale = replace(scale, name=f"{name}-custom")
    scale.validate()
    return scale


def config_snapshot(scale: Scale, policy: Policy, seed: int) -> dict:
    s = asdict(scale)
    s["start_date"] = scale.start_date.isoformat()
    s["end_date"] = scale.end_date.isoformat()
    p = asdict(policy)
    p["peak_uplift_departments"] = list(policy.peak_uplift_departments)
    p["peak_uplift_from"] = policy.peak_uplift_from(scale).isoformat()
    return {"seed": seed, "generator_version": GENERATOR_VERSION, "scale": s, "policy": p}
