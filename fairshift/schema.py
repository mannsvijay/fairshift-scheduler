"""Single source of truth for the data model.

The data dictionary (docs/DATA_DICTIONARY.md), the ER diagram, the SQL DDL,
CSV column order, type parsing and the integrity validator are all generated
from these definitions, so documentation can never drift from the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STRING, INTEGER, DECIMAL, DATE, DATETIME, BOOLEAN, TIME = (
    "STRING", "INTEGER", "DECIMAL", "DATE", "DATETIME", "BOOLEAN", "TIME")


@dataclass(frozen=True)
class Col:
    name: str
    type: str
    required: bool = True
    desc: str = ""
    enum: tuple | None = None
    unit: str | None = None
    unique: bool = False
    fk: str | None = None          # "table.column"
    pattern: str | None = None     # regex the value must fully match
    rule: str | None = None        # human-readable validation rule
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Table:
    name: str
    kind: str                      # master | bridge | transaction | event
    desc: str
    pk: str
    columns: tuple
    unique_together: tuple = ()
    lifecycle: dict | None = None  # state -> allowed next states
    notes: tuple = ()

    def col(self, name: str) -> Col:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


DEPARTMENTS = ("INBOUND", "OUTBOUND", "INVENTORY", "RETURNS", "CUSTOMER_SUPPORT")
REGIONS = ("IN-RJ", "IN-MH", "IN-KA", "IN-TG", "IN-DL")
ROLES = ("ASSOCIATE", "SENIOR_ASSOCIATE", "SHIFT_LEAD", "MANAGER")
DAY_TYPES = ("WEEKDAY", "WEEKEND", "HOLIDAY")
LEAVE_TYPES = ("ANNUAL", "SICK", "PERSONAL", "UNPAID")
LEAVE_STATUSES = ("SUBMITTED", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED")
LEAVE_REASONS = ("POLICY_COMPLIANT", "SICK_AUTO_APPROVED", "INSUFFICIENT_NOTICE",
                 "INSUFFICIENT_BALANCE", "ALLOWANCE_EXCEEDED", "TEAM_CAPACITY",
                 "DUPLICATE_OVERLAP", "MANAGER_NO_RESPONSE", "EMPLOYEE_CANCELLED")
SWAP_STATUSES = ("REQUESTED", "APPROVED", "REJECTED", "WITHDRAWN", "APPLIED")
SWAP_REASONS = ("CONSTRAINTS_SATISFIED", "ASSIGNMENT_CHANGED", "LATE_REQUEST", "ON_LEAVE",
                "DOUBLE_BOOKING", "REST_RULE", "CONSECUTIVE_DAYS", "WEEKLY_HOURS_CAP",
                "NIGHT_INELIGIBLE", "NOT_EMPLOYED", "SKILL_MISMATCH", "SKILL_COVERAGE",
                "REQUESTER_WITHDREW", "NOT_ROTA")
ASSIGNMENT_SOURCES = ("PLANNED", "REPLACEMENT", "MANUAL", "SWAP")
ASSIGNMENT_STATUSES = ("ACTIVE", "RELEASED", "SUPERSEDED")
ASSIGNMENT_EVENT_TYPES = ("CREATED", "RELEASED", "SUPERSEDED")
ASSIGNMENT_REASONS = ("SCHEDULE_PUBLISHED", "LEAVE_REPLACEMENT", "MANUAL_TOPUP",
                      "MANUAL_REASSIGNMENT", "SWAP_APPLIED", "LEAVE_APPROVED")

_ID_EMP = r"EMP-\d{6}"
_ID_TEAM = r"TEAM-\d{3}"
_ID_SKILL = r"SKL-\d{3}"


def _emp_fk(name, required=True, desc="", **kw):
    return Col(name, STRING, required, desc, fk="employee.employee_id", pattern=_ID_EMP, **kw)


TABLES: tuple[Table, ...] = (
    Table("team", "master", "An operational team at one site. Teams in the same department and region are 'sister teams' that may lend staff.",
          "team_id", (
              Col("team_id", STRING, desc="Primary key.", unique=True, pattern=_ID_TEAM),
              Col("team_name", STRING, desc="Display name.", unique=True),
              Col("department", STRING, desc="Business function; determines which skills the team requires.", enum=DEPARTMENTS),
              Col("region_code", STRING, desc="ISO 3166-2 style site region; selects regional holidays.", enum=REGIONS),
              _emp_fk("manager_employee_id", desc="Manager who approves leave and swaps for this team.",
                      rule="Referenced employee has role MANAGER and belongs to this team."),
              Col("created_date", DATE, desc="Date the team was created.", rule="<= planning window start"),
          )),
    Table("skill", "master", "A competency that coverage requirements can demand.", "skill_id", (
        Col("skill_id", STRING, desc="Primary key.", unique=True, pattern=_ID_SKILL),
        Col("skill_code", STRING, desc="Stable mnemonic code.", unique=True, pattern=r"[A-Z0-9_]+"),
        Col("skill_name", STRING, desc="Display name.", unique=True),
        Col("category", STRING, desc="Skill family.", enum=("OPERATIONAL", "SAFETY", "SYSTEMS", "CUSTOMER")),
        Col("requires_certification", BOOLEAN, desc="If true, holdings expire and must be renewed."),
        Col("certification_validity_days", INTEGER, required=False, unit="days", min=1,
            desc="Validity of one certification; null when requires_certification is false.",
            rule="Required iff requires_certification = true"),
    )),
    Table("employee", "master", "A person employed in a team. Managers are employees but are not on the shift rota.",
          "employee_id", (
              Col("employee_id", STRING, desc="Primary key; numbered in hire-date order.", unique=True, pattern=_ID_EMP),
              Col("first_name", STRING, desc="Synthetic given name."),
              Col("last_name", STRING, desc="Synthetic family name."),
              Col("email", STRING, desc="Synthetic address on the reserved example.com domain.", unique=True,
                  pattern=r"[a-z]+\.[a-z]+\.\d{6}@example\.com"),
              Col("team_id", STRING, desc="Home team.", fk="team.team_id", pattern=_ID_TEAM),
              Col("role", STRING, desc="Job role. MANAGER is excluded from the shift rota.", enum=ROLES),
              Col("employment_type", STRING, desc="Contract type.", enum=("FULL_TIME", "PART_TIME")),
              Col("contracted_weekly_hours", DECIMAL, unit="hours/ISO week", min=1, max=60,
                  desc="Regular hours; scheduled hours above this are overtime."),
              Col("max_weekly_hours", DECIMAL, unit="hours/ISO week", min=1, max=60,
                  desc="Overtime cap; scheduled hours must not exceed it.", rule=">= contracted_weekly_hours"),
              Col("night_shift_eligible", BOOLEAN, desc="False means the employee must never be assigned a night shift."),
              Col("hire_date", DATE, desc="First day of employment (effective-from)."),
              Col("termination_date", DATE, required=False, desc="Last day of employment (effective-to); null if still employed.",
                  rule=">= hire_date"),
              Col("employment_status", STRING, desc="Status as of the end of the planning window.",
                  enum=("ACTIVE", "TERMINATED"), rule="TERMINATED iff termination_date <= window end"),
              Col("annual_leave_opening_balance_days", DECIMAL, unit="days", min=0, max=40,
                  desc="Annual-leave balance available at the start of the planning window."),
          )),
    Table("employee_skill", "bridge", "N:M bridge between employee and skill with effective dating. A renewed certification is a new row; history is never overwritten.",
          "employee_skill_id", (
              Col("employee_skill_id", STRING, desc="Primary key.", unique=True, pattern=r"ESK-\d{7}"),
              _emp_fk("employee_id", desc="Holder."),
              Col("skill_id", STRING, desc="Skill held.", fk="skill.skill_id", pattern=_ID_SKILL),
              Col("proficiency_level", INTEGER, desc="1 = working, 2 = proficient, 3 = expert.", min=1, max=3),
              Col("valid_from", DATE, desc="First day the holding is valid."),
              Col("valid_to", DATE, required=False, desc="Last valid day (certification expiry); null = no expiry.",
                  rule=">= valid_from; periods for the same employee+skill never overlap"),
          )),
    Table("shift_template", "master", "Reusable definition of a shift pattern.", "template_id", (
        Col("template_id", STRING, desc="Primary key.", unique=True, pattern=r"TPL-[A-Z]"),
        Col("template_code", STRING, desc="Single-letter code used in shift IDs.", unique=True, pattern=r"[A-Z]"),
        Col("template_name", STRING, desc="Display name."),
        Col("start_time", TIME, desc="Local start time (HH:MM, site local time, Asia/Kolkata)."),
        Col("end_time", TIME, desc="Local end time (HH:MM)."),
        Col("duration_hours", DECIMAL, unit="hours", min=1, max=12, desc="Paid duration (breaks are paid).",
            rule="= end - start (+24h if crosses_midnight)"),
        Col("crosses_midnight", BOOLEAN, desc="True if the shift ends on the next calendar day."),
        Col("is_night", BOOLEAN, desc="Night shift; requires night_shift_eligible."),
    )),
    Table("holiday_calendar", "master", "Public holidays. A REGIONAL holiday applies only to teams in its region.",
          "holiday_id", (
              Col("holiday_id", STRING, desc="Primary key.", unique=True, pattern=r"HOL-\d{4}-\d{3}"),
              Col("calendar_id", STRING, desc="Calendar this entry belongs to.", pattern=r"CAL-[A-Z]{2}-\d{4}"),
              Col("holiday_date", DATE, desc="Date of the holiday."),
              Col("holiday_name", STRING, desc="Name."),
              Col("scope", STRING, desc="NATIONAL applies to all regions.", enum=("NATIONAL", "REGIONAL")),
              Col("region_code", STRING, required=False, enum=REGIONS, desc="Region for REGIONAL holidays; null for NATIONAL.",
                  rule="Required iff scope = REGIONAL"),
              Col("date_precision", STRING, enum=("EXACT", "APPROXIMATE"),
                  desc="APPROXIMATE for lunar-calendar festivals whose date must be confirmed against the official notification."),
          ), unique_together=(("holiday_date", "scope", "region_code"),)),
    Table("shift", "master", "A dated instance of a shift template (one per date per template), e.g. SHIFT-2026-01-01-A. Team-specific staffing lives in coverage_requirement and shift_assignment.",
          "shift_id", (
              Col("shift_id", STRING, desc="Primary key: SHIFT-<date>-<template code>.", unique=True,
                  pattern=r"SHIFT-\d{4}-\d{2}-\d{2}-[A-Z]"),
              Col("shift_date", DATE, desc="Calendar date the shift starts."),
              Col("template_id", STRING, desc="Template.", fk="shift_template.template_id", pattern=r"TPL-[A-Z]"),
              Col("start_datetime", DATETIME, desc="Local start."),
              Col("end_datetime", DATETIME, desc="Local end.", rule="= start + template duration"),
              Col("iso_week", STRING, desc="ISO week of shift_date (weekly hours are counted per ISO week).",
                  pattern=r"\d{4}-W\d{2}"),
              Col("is_weekend", BOOLEAN, desc="Saturday or Sunday."),
              Col("publication_datetime", DATETIME, desc="When the schedule for this shift's week is published.",
                  rule="< start_datetime"),
          ), unique_together=(("shift_date", "template_id"),)),
    Table("coverage_requirement", "master", "Minimum staffing per team, shift template and day type. skill_id null = total headcount; otherwise the minimum number of assigned people who hold that skill. Effective-dated.",
          "coverage_requirement_id", (
              Col("coverage_requirement_id", STRING, desc="Primary key.", unique=True, pattern=r"COV-\d{6}"),
              Col("team_id", STRING, fk="team.team_id", pattern=_ID_TEAM, desc="Team."),
              Col("template_id", STRING, fk="shift_template.template_id", pattern=r"TPL-[A-Z]", desc="Shift template."),
              Col("day_type", STRING, enum=DAY_TYPES, desc="HOLIDAY if a holiday applies to the team's region, else WEEKEND/WEEKDAY."),
              Col("skill_id", STRING, required=False, fk="skill.skill_id", pattern=_ID_SKILL,
                  desc="Null = total headcount requirement."),
              Col("min_headcount", INTEGER, min=0, max=50, unit="people", desc="Minimum people required."),
              Col("effective_from", DATE, desc="First day the requirement applies."),
              Col("effective_to", DATE, required=False, desc="Last day it applies; null = open-ended.", rule=">= effective_from"),
          ), notes=("At most one requirement row is effective per (team, template, day_type, skill) on any date.",)),
    Table("shift_assignment", "transaction", "One employee working one shift for one team. Rows are never deleted or reassigned; a change ends the old row (RELEASED/SUPERSEDED) and creates a new one, recorded in assignment_event.",
          "assignment_id", (
              Col("assignment_id", STRING, desc="Primary key, sequenced by created_at.", unique=True, pattern=r"ASG-\d{4}-\d{7}"),
              Col("shift_id", STRING, fk="shift.shift_id", pattern=r"SHIFT-\d{4}-\d{2}-\d{2}-[A-Z]", desc="Shift worked."),
              _emp_fk("employee_id", desc="Assigned employee."),
              Col("team_id", STRING, fk="team.team_id", pattern=_ID_TEAM,
                  desc="Team being staffed; differs from the employee's home team for cross-team cover."),
              Col("slot_skill_id", STRING, required=False, fk="skill.skill_id", pattern=_ID_SKILL,
                  desc="Skill slot this person was placed to cover; null = general headcount.",
                  rule="If set, the employee must hold a valid holding of this skill on shift_date"),
              Col("source", STRING, enum=ASSIGNMENT_SOURCES, desc="How the assignment was created."),
              Col("status", STRING, enum=ASSIGNMENT_STATUSES, desc="Current state; must equal the state implied by the last assignment_event."),
              Col("created_at", DATETIME, desc="Creation timestamp.", rule="< shift start"),
              _emp_fk("created_by_employee_id", required=False, desc="Manager who created it; null = automated planner."),
              Col("swap_id", STRING, required=False, fk="swap_request.swap_id", pattern=r"SWP-\d{4}-\d{6}",
                  desc="Swap that produced this row (source = SWAP).", rule="Required iff source = SWAP"),
              Col("replaces_assignment_id", STRING, required=False, fk="shift_assignment.assignment_id",
                  pattern=r"ASG-\d{4}-\d{7}", desc="Assignment this row replaces (replacement, reassignment, swap)."),
          )),
    Table("assignment_event", "event", "Append-only history of assignment state changes.", "assignment_event_id", (
        Col("assignment_event_id", STRING, desc="Primary key, sequenced by event_ts.", unique=True, pattern=r"AEV-\d{4}-\d{7}"),
        Col("assignment_id", STRING, fk="shift_assignment.assignment_id", pattern=r"ASG-\d{4}-\d{7}", desc="Assignment."),
        Col("event_type", STRING, enum=ASSIGNMENT_EVENT_TYPES, desc="Transition."),
        Col("event_ts", DATETIME, desc="When it happened."),
        Col("reason", STRING, enum=ASSIGNMENT_REASONS, desc="Business reason."),
        _emp_fk("actor_employee_id", required=False, desc="Manager who acted; null = system."),
        Col("related_leave_id", STRING, required=False, fk="leave_request.leave_id", pattern=r"LVE-\d{4}-\d{6}",
            desc="Leave that caused a release."),
        Col("related_swap_id", STRING, required=False, fk="swap_request.swap_id", pattern=r"SWP-\d{4}-\d{6}",
            desc="Swap that caused a supersede/create."),
        Col("related_assignment_id", STRING, required=False, fk="shift_assignment.assignment_id",
            pattern=r"ASG-\d{4}-\d{7}", desc="Counterpart assignment (replacement or replaced)."),
    ), lifecycle={"": ("CREATED",), "CREATED": ("RELEASED", "SUPERSEDED"), "RELEASED": (), "SUPERSEDED": ()}),
    Table("leave_request", "transaction", "A request for time off and its outcome. Decisions follow the documented leave rules.",
          "leave_id", (
              Col("leave_id", STRING, desc="Primary key, sequenced by submitted_at.", unique=True, pattern=r"LVE-\d{4}-\d{6}"),
              _emp_fk("employee_id", desc="Requester."),
              Col("leave_type", STRING, enum=LEAVE_TYPES, desc="Type of leave."),
              Col("start_date", DATE, desc="First day off."),
              Col("end_date", DATE, desc="Last day off.", rule=">= start_date"),
              Col("days_requested", DECIMAL, unit="days", min=0, max=31,
                  desc="Derived: calendar days in range excluding holidays that apply to the employee's region."),
              Col("submitted_at", DATETIME, desc="Submission time."),
              Col("status", STRING, enum=LEAVE_STATUSES, desc="Current state (projection of leave_request_event)."),
              Col("decided_at", DATETIME, required=False, desc="Decision time.", rule=">= submitted_at"),
              _emp_fk("decided_by_employee_id", required=False, desc="Approving/rejecting manager; null for automatic decisions."),
              Col("decision_channel", STRING, required=False, enum=("AUTO", "MANAGER"), desc="Who decided."),
              Col("decision_reason", STRING, required=False, enum=LEAVE_REASONS, desc="Rule that produced the decision."),
              Col("cancelled_at", DATETIME, required=False, desc="Cancellation time.", rule=">= decided_at"),
          )),
    Table("leave_request_event", "event", "Append-only history of leave state changes.", "leave_event_id", (
        Col("leave_event_id", STRING, desc="Primary key, sequenced by event_ts.", unique=True, pattern=r"LEV-\d{4}-\d{6}"),
        Col("leave_id", STRING, fk="leave_request.leave_id", pattern=r"LVE-\d{4}-\d{6}", desc="Leave request."),
        Col("event_type", STRING, enum=LEAVE_STATUSES, desc="New state."),
        Col("event_ts", DATETIME, desc="When."),
        _emp_fk("actor_employee_id", required=False, desc="Employee or manager who acted; null = system."),
        Col("reason", STRING, required=False, enum=LEAVE_REASONS, desc="Rule applied."),
    ), lifecycle={"": ("SUBMITTED",), "SUBMITTED": ("APPROVED", "REJECTED", "EXPIRED"),
                  "APPROVED": ("CANCELLED",), "REJECTED": (), "EXPIRED": (), "CANCELLED": ()}),
    Table("attendance_event", "event", "Badge/mobile clock events. ID = ATT-<employee-id>-<timestamp>.",
          "attendance_event_id", (
              Col("attendance_event_id", STRING, desc="Primary key.", unique=True,
                  pattern=r"ATT-EMP-\d{6}-\d{8}T\d{6}"),
              _emp_fk("employee_id", desc="Who clocked."),
              Col("assignment_id", STRING, fk="shift_assignment.assignment_id", pattern=r"ASG-\d{4}-\d{7}",
                  desc="Assignment the clock event belongs to.", rule="Assignment is ACTIVE and belongs to employee_id"),
              Col("event_type", STRING, enum=("CLOCK_IN", "CLOCK_OUT"), desc="Direction."),
              Col("event_ts", DATETIME, desc="Clock time (seconds precision)."),
              Col("capture_method", STRING, enum=("BADGE", "MOBILE", "MANUAL"), desc="How it was captured."),
          ), unique_together=(("employee_id", "event_ts"),)),
    Table("swap_request", "transaction", "Employee-initiated shift swap. Only APPROVED swaps may be APPLIED; applying supersedes the original assignments and creates new ones.",
          "swap_id", (
              Col("swap_id", STRING, desc="Primary key, sequenced by requested_at.", unique=True, pattern=r"SWP-\d{4}-\d{6}"),
              Col("swap_type", STRING, enum=("EXCHANGE", "GIVEAWAY"),
                  desc="EXCHANGE trades two shifts; GIVEAWAY hands one shift to a teammate."),
              Col("team_id", STRING, fk="team.team_id", pattern=_ID_TEAM, desc="Team whose manager decides."),
              _emp_fk("requester_employee_id", desc="Employee giving up a shift."),
              Col("requester_assignment_id", STRING, fk="shift_assignment.assignment_id", pattern=r"ASG-\d{4}-\d{7}",
                  desc="Assignment offered."),
              _emp_fk("target_employee_id", desc="Teammate taking the shift."),
              Col("target_assignment_id", STRING, required=False, fk="shift_assignment.assignment_id",
                  pattern=r"ASG-\d{4}-\d{7}", desc="Target's assignment given back (EXCHANGE only).",
                  rule="Required iff swap_type = EXCHANGE"),
              Col("requested_at", DATETIME, desc="Request time."),
              Col("status", STRING, enum=SWAP_STATUSES, desc="Current state (projection of swap_request_event)."),
              Col("decided_at", DATETIME, required=False, desc="Decision time.", rule=">= requested_at"),
              _emp_fk("decided_by_employee_id", required=False, desc="Deciding manager."),
              Col("decision_reason", STRING, required=False, enum=SWAP_REASONS, desc="Rule that produced the decision."),
              Col("applied_at", DATETIME, required=False, desc="When the swap was applied.", rule=">= decided_at"),
          )),
    Table("swap_request_event", "event", "Append-only history of swap state changes.", "swap_event_id", (
        Col("swap_event_id", STRING, desc="Primary key, sequenced by event_ts.", unique=True, pattern=r"SEV-\d{4}-\d{6}"),
        Col("swap_id", STRING, fk="swap_request.swap_id", pattern=r"SWP-\d{4}-\d{6}", desc="Swap request."),
        Col("event_type", STRING, enum=SWAP_STATUSES, desc="New state."),
        Col("event_ts", DATETIME, desc="When."),
        _emp_fk("actor_employee_id", required=False, desc="Who acted."),
        Col("reason", STRING, required=False, enum=SWAP_REASONS, desc="Rule applied."),
    ), lifecycle={"": ("REQUESTED",), "REQUESTED": ("APPROVED", "REJECTED", "WITHDRAWN"),
                  "APPROVED": ("APPLIED",), "REJECTED": (), "WITHDRAWN": (), "APPLIED": ()}),
)

TABLE_BY_NAME = {t.name: t for t in TABLES}
TABLE_ORDER = [t.name for t in TABLES]  # parents before children

# Which event table carries the history for which transaction table.
EVENT_LOGS = {
    "shift_assignment": ("assignment_event", "assignment_id"),
    "leave_request": ("leave_request_event", "leave_id"),
    "swap_request": ("swap_request_event", "swap_id"),
}

# How a transaction's current status maps to the state reached in its event log.
STATUS_FROM_EVENT = {
    "shift_assignment": {"CREATED": "ACTIVE", "RELEASED": "RELEASED", "SUPERSEDED": "SUPERSEDED"},
    "leave_request": {s: s for s in LEAVE_STATUSES},
    "swap_request": {s: s for s in SWAP_STATUSES},
}

# Column names that would leak ground truth into the input data if they existed.
FORBIDDEN_INPUT_COLUMNS = ("issue_type", "ground_truth", "is_anomaly", "anomaly_id", "label", "injected")

GROUND_TRUTH_COLUMNS = ["anomaly_id", "issue_type", "record_type", "record_id", "related_record_ids",
                        "employee_id", "team_id", "shift_id", "business_date", "iso_week",
                        "expected_rule", "description"]

ISSUE_TYPES = ("DOUBLE_BOOKED", "LEAVE_OVERLAPS_ASSIGNMENT", "REQUIRED_SKILL_ABSENT",
               "OVERTIME_CAP_EXCEEDED", "SWAP_APPLIED_WITHOUT_APPROVAL")


def relationships():
    """(parent, child, fk column, cardinality, optional) derived from FK definitions."""
    rels = []
    for t in TABLES:
        for c in t.columns:
            if c.fk:
                parent = c.fk.split(".")[0]
                rels.append((parent, t.name, c.name, "1:N", not c.required))
    return rels
