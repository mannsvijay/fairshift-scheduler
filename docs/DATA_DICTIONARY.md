# Data dictionary

Generated from `fairshift/schema.py` by `python -m fairshift docs` — do not edit by hand.
The same definitions drive the CSV column order, SQL DDL and the validator, so this document cannot drift from the data.

Conventions: timestamps are local site time (Asia/Kolkata, no offset) at second precision; dates are ISO 8601;
booleans are `true`/`false` in CSV and JSON, `1`/`0` in SQL; null is an empty CSV field.

| Table | Kind | Primary key | Purpose |
|---|---|---|---|
| [`team`](#team) | master | `team_id` | An operational team at one site. Teams in the same department and region are 'sister teams' that may lend staff. |
| [`skill`](#skill) | master | `skill_id` | A competency that coverage requirements can demand. |
| [`employee`](#employee) | master | `employee_id` | A person employed in a team. Managers are employees but are not on the shift rota. |
| [`employee_skill`](#employee_skill) | bridge | `employee_skill_id` | N:M bridge between employee and skill with effective dating. A renewed certification is a new row; history is never overwritten. |
| [`shift_template`](#shift_template) | master | `template_id` | Reusable definition of a shift pattern. |
| [`holiday_calendar`](#holiday_calendar) | master | `holiday_id` | Public holidays. A REGIONAL holiday applies only to teams in its region. |
| [`shift`](#shift) | master | `shift_id` | A dated instance of a shift template (one per date per template), e.g. SHIFT-2026-01-01-A. Team-specific staffing lives in coverage_requirement and shift_assignment. |
| [`coverage_requirement`](#coverage_requirement) | master | `coverage_requirement_id` | Minimum staffing per team, shift template and day type. skill_id null = total headcount; otherwise the minimum number of assigned people who hold that skill. Effective-dated. |
| [`shift_assignment`](#shift_assignment) | transaction | `assignment_id` | One employee working one shift for one team. Rows are never deleted or reassigned; a change ends the old row (RELEASED/SUPERSEDED) and creates a new one, recorded in assignment_event. |
| [`assignment_event`](#assignment_event) | event | `assignment_event_id` | Append-only history of assignment state changes. |
| [`leave_request`](#leave_request) | transaction | `leave_id` | A request for time off and its outcome. Decisions follow the documented leave rules. |
| [`leave_request_event`](#leave_request_event) | event | `leave_event_id` | Append-only history of leave state changes. |
| [`attendance_event`](#attendance_event) | event | `attendance_event_id` | Badge/mobile clock events. ID = ATT-<employee-id>-<timestamp>. |
| [`swap_request`](#swap_request) | transaction | `swap_id` | Employee-initiated shift swap. Only APPROVED swaps may be APPLIED; applying supersedes the original assignments and creates new ones. |
| [`swap_request_event`](#swap_request_event) | event | `swap_event_id` | Append-only history of swap state changes. |

## team

An operational team at one site. Teams in the same department and region are 'sister teams' that may lend staff.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `team_id` PK | STRING | yes | yes | `TEAM-\d{3}` |  |  |  | Primary key. |
| `team_name`  | STRING | yes | yes |  |  |  |  | Display name. |
| `department`  | STRING | yes |  | `INBOUND`, `OUTBOUND`, `INVENTORY`, `RETURNS`, `CUSTOMER_SUPPORT` |  |  |  | Business function; determines which skills the team requires. |
| `region_code`  | STRING | yes |  | `IN-RJ`, `IN-MH`, `IN-KA`, `IN-TG`, `IN-DL` |  |  |  | ISO 3166-2 style site region; selects regional holidays. |
| `manager_employee_id`  | STRING | yes |  | `EMP-\d{6}` |  | `employee.employee_id` | Referenced employee has role MANAGER and belongs to this team. | Manager who approves leave and swaps for this team. |
| `created_date`  | DATE | yes |  |  |  |  | <= planning window start | Date the team was created. |

## skill

A competency that coverage requirements can demand.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `skill_id` PK | STRING | yes | yes | `SKL-\d{3}` |  |  |  | Primary key. |
| `skill_code`  | STRING | yes | yes | `[A-Z0-9_]+` |  |  |  | Stable mnemonic code. |
| `skill_name`  | STRING | yes | yes |  |  |  |  | Display name. |
| `category`  | STRING | yes |  | `OPERATIONAL`, `SAFETY`, `SYSTEMS`, `CUSTOMER` |  |  |  | Skill family. |
| `requires_certification`  | BOOLEAN | yes |  |  |  |  |  | If true, holdings expire and must be renewed. |
| `certification_validity_days`  | INTEGER | no |  |  | days |  | Required iff requires_certification = true; >= 1 | Validity of one certification; null when requires_certification is false. |

## employee

A person employed in a team. Managers are employees but are not on the shift rota.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `employee_id` PK | STRING | yes | yes | `EMP-\d{6}` |  |  |  | Primary key; numbered in hire-date order. |
| `first_name`  | STRING | yes |  |  |  |  |  | Synthetic given name. |
| `last_name`  | STRING | yes |  |  |  |  |  | Synthetic family name. |
| `email`  | STRING | yes | yes | `[a-z]+\.[a-z]+\.\d{6}@example\.com` |  |  |  | Synthetic address on the reserved example.com domain. |
| `team_id`  | STRING | yes |  | `TEAM-\d{3}` |  | `team.team_id` |  | Home team. |
| `role`  | STRING | yes |  | `ASSOCIATE`, `SENIOR_ASSOCIATE`, `SHIFT_LEAD`, `MANAGER` |  |  |  | Job role. MANAGER is excluded from the shift rota. |
| `employment_type`  | STRING | yes |  | `FULL_TIME`, `PART_TIME` |  |  |  | Contract type. |
| `contracted_weekly_hours`  | DECIMAL | yes |  |  | hours/ISO week |  | >= 1, <= 60 | Regular hours; scheduled hours above this are overtime. |
| `max_weekly_hours`  | DECIMAL | yes |  |  | hours/ISO week |  | >= contracted_weekly_hours; >= 1, <= 60 | Overtime cap; scheduled hours must not exceed it. |
| `night_shift_eligible`  | BOOLEAN | yes |  |  |  |  |  | False means the employee must never be assigned a night shift. |
| `hire_date`  | DATE | yes |  |  |  |  |  | First day of employment (effective-from). |
| `termination_date`  | DATE | no |  |  |  |  | >= hire_date | Last day of employment (effective-to); null if still employed. |
| `employment_status`  | STRING | yes |  | `ACTIVE`, `TERMINATED` |  |  | TERMINATED iff termination_date <= window end | Status as of the end of the planning window. |
| `annual_leave_opening_balance_days`  | DECIMAL | yes |  |  | days |  | >= 0, <= 40 | Annual-leave balance available at the start of the planning window. |

## employee_skill

N:M bridge between employee and skill with effective dating. A renewed certification is a new row; history is never overwritten.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `employee_skill_id` PK | STRING | yes | yes | `ESK-\d{7}` |  |  |  | Primary key. |
| `employee_id`  | STRING | yes |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Holder. |
| `skill_id`  | STRING | yes |  | `SKL-\d{3}` |  | `skill.skill_id` |  | Skill held. |
| `proficiency_level`  | INTEGER | yes |  |  |  |  | >= 1, <= 3 | 1 = working, 2 = proficient, 3 = expert. |
| `valid_from`  | DATE | yes |  |  |  |  |  | First day the holding is valid. |
| `valid_to`  | DATE | no |  |  |  |  | >= valid_from; periods for the same employee+skill never overlap | Last valid day (certification expiry); null = no expiry. |

## shift_template

Reusable definition of a shift pattern.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `template_id` PK | STRING | yes | yes | `TPL-[A-Z]` |  |  |  | Primary key. |
| `template_code`  | STRING | yes | yes | `[A-Z]` |  |  |  | Single-letter code used in shift IDs. |
| `template_name`  | STRING | yes |  |  |  |  |  | Display name. |
| `start_time`  | TIME | yes |  |  |  |  |  | Local start time (HH:MM, site local time, Asia/Kolkata). |
| `end_time`  | TIME | yes |  |  |  |  |  | Local end time (HH:MM). |
| `duration_hours`  | DECIMAL | yes |  |  | hours |  | = end - start (+24h if crosses_midnight); >= 1, <= 12 | Paid duration (breaks are paid). |
| `crosses_midnight`  | BOOLEAN | yes |  |  |  |  |  | True if the shift ends on the next calendar day. |
| `is_night`  | BOOLEAN | yes |  |  |  |  |  | Night shift; requires night_shift_eligible. |

## holiday_calendar

Public holidays. A REGIONAL holiday applies only to teams in its region.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `holiday_id` PK | STRING | yes | yes | `HOL-\d{4}-\d{3}` |  |  |  | Primary key. |
| `calendar_id`  | STRING | yes |  | `CAL-[A-Z]{2}-\d{4}` |  |  |  | Calendar this entry belongs to. |
| `holiday_date`  | DATE | yes |  |  |  |  |  | Date of the holiday. |
| `holiday_name`  | STRING | yes |  |  |  |  |  | Name. |
| `scope`  | STRING | yes |  | `NATIONAL`, `REGIONAL` |  |  |  | NATIONAL applies to all regions. |
| `region_code`  | STRING | no |  | `IN-RJ`, `IN-MH`, `IN-KA`, `IN-TG`, `IN-DL` |  |  | Required iff scope = REGIONAL | Region for REGIONAL holidays; null for NATIONAL. |
| `date_precision`  | STRING | yes |  | `EXACT`, `APPROXIMATE` |  |  |  | APPROXIMATE for lunar-calendar festivals whose date must be confirmed against the official notification. |

Composite uniqueness: `(holiday_date, scope, region_code)`.

## shift

A dated instance of a shift template (one per date per template), e.g. SHIFT-2026-01-01-A. Team-specific staffing lives in coverage_requirement and shift_assignment.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `shift_id` PK | STRING | yes | yes | `SHIFT-\d{4}-\d{2}-\d{2}-[A-Z]` |  |  |  | Primary key: SHIFT-<date>-<template code>. |
| `shift_date`  | DATE | yes |  |  |  |  |  | Calendar date the shift starts. |
| `template_id`  | STRING | yes |  | `TPL-[A-Z]` |  | `shift_template.template_id` |  | Template. |
| `start_datetime`  | DATETIME | yes |  |  |  |  |  | Local start. |
| `end_datetime`  | DATETIME | yes |  |  |  |  | = start + template duration | Local end. |
| `iso_week`  | STRING | yes |  | `\d{4}-W\d{2}` |  |  |  | ISO week of shift_date (weekly hours are counted per ISO week). |
| `is_weekend`  | BOOLEAN | yes |  |  |  |  |  | Saturday or Sunday. |
| `publication_datetime`  | DATETIME | yes |  |  |  |  | < start_datetime | When the schedule for this shift's week is published. |

Composite uniqueness: `(shift_date, template_id)`.

## coverage_requirement

Minimum staffing per team, shift template and day type. skill_id null = total headcount; otherwise the minimum number of assigned people who hold that skill. Effective-dated.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `coverage_requirement_id` PK | STRING | yes | yes | `COV-\d{6}` |  |  |  | Primary key. |
| `team_id`  | STRING | yes |  | `TEAM-\d{3}` |  | `team.team_id` |  | Team. |
| `template_id`  | STRING | yes |  | `TPL-[A-Z]` |  | `shift_template.template_id` |  | Shift template. |
| `day_type`  | STRING | yes |  | `WEEKDAY`, `WEEKEND`, `HOLIDAY` |  |  |  | HOLIDAY if a holiday applies to the team's region, else WEEKEND/WEEKDAY. |
| `skill_id`  | STRING | no |  | `SKL-\d{3}` |  | `skill.skill_id` |  | Null = total headcount requirement. |
| `min_headcount`  | INTEGER | yes |  |  | people |  | >= 0, <= 50 | Minimum people required. |
| `effective_from`  | DATE | yes |  |  |  |  |  | First day the requirement applies. |
| `effective_to`  | DATE | no |  |  |  |  | >= effective_from | Last day it applies; null = open-ended. |

Note: At most one requirement row is effective per (team, template, day_type, skill) on any date.

## shift_assignment

One employee working one shift for one team. Rows are never deleted or reassigned; a change ends the old row (RELEASED/SUPERSEDED) and creates a new one, recorded in assignment_event.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `assignment_id` PK | STRING | yes | yes | `ASG-\d{4}-\d{7}` |  |  |  | Primary key, sequenced by created_at. |
| `shift_id`  | STRING | yes |  | `SHIFT-\d{4}-\d{2}-\d{2}-[A-Z]` |  | `shift.shift_id` |  | Shift worked. |
| `employee_id`  | STRING | yes |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Assigned employee. |
| `team_id`  | STRING | yes |  | `TEAM-\d{3}` |  | `team.team_id` |  | Team being staffed; differs from the employee's home team for cross-team cover. |
| `slot_skill_id`  | STRING | no |  | `SKL-\d{3}` |  | `skill.skill_id` | If set, the employee must hold a valid holding of this skill on shift_date | Skill slot this person was placed to cover; null = general headcount. |
| `source`  | STRING | yes |  | `PLANNED`, `REPLACEMENT`, `MANUAL`, `SWAP` |  |  |  | How the assignment was created. |
| `status`  | STRING | yes |  | `ACTIVE`, `RELEASED`, `SUPERSEDED` |  |  |  | Current state; must equal the state implied by the last assignment_event. |
| `created_at`  | DATETIME | yes |  |  |  |  | < shift start | Creation timestamp. |
| `created_by_employee_id`  | STRING | no |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Manager who created it; null = automated planner. |
| `swap_id`  | STRING | no |  | `SWP-\d{4}-\d{6}` |  | `swap_request.swap_id` | Required iff source = SWAP | Swap that produced this row (source = SWAP). |
| `replaces_assignment_id`  | STRING | no |  | `ASG-\d{4}-\d{7}` |  | `shift_assignment.assignment_id` |  | Assignment this row replaces (replacement, reassignment, swap). |

## assignment_event

Append-only history of assignment state changes.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `assignment_event_id` PK | STRING | yes | yes | `AEV-\d{4}-\d{7}` |  |  |  | Primary key, sequenced by event_ts. |
| `assignment_id`  | STRING | yes |  | `ASG-\d{4}-\d{7}` |  | `shift_assignment.assignment_id` |  | Assignment. |
| `event_type`  | STRING | yes |  | `CREATED`, `RELEASED`, `SUPERSEDED` |  |  |  | Transition. |
| `event_ts`  | DATETIME | yes |  |  |  |  |  | When it happened. |
| `reason`  | STRING | yes |  | `SCHEDULE_PUBLISHED`, `LEAVE_REPLACEMENT`, `MANUAL_TOPUP`, `MANUAL_REASSIGNMENT`, `SWAP_APPLIED`, `LEAVE_APPROVED` |  |  |  | Business reason. |
| `actor_employee_id`  | STRING | no |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Manager who acted; null = system. |
| `related_leave_id`  | STRING | no |  | `LVE-\d{4}-\d{6}` |  | `leave_request.leave_id` |  | Leave that caused a release. |
| `related_swap_id`  | STRING | no |  | `SWP-\d{4}-\d{6}` |  | `swap_request.swap_id` |  | Swap that caused a supersede/create. |
| `related_assignment_id`  | STRING | no |  | `ASG-\d{4}-\d{7}` |  | `shift_assignment.assignment_id` |  | Counterpart assignment (replacement or replaced). |

Allowed state transitions: `START` → `CREATED`, `CREATED` → `RELEASED`, `CREATED` → `SUPERSEDED`.

## leave_request

A request for time off and its outcome. Decisions follow the documented leave rules.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `leave_id` PK | STRING | yes | yes | `LVE-\d{4}-\d{6}` |  |  |  | Primary key, sequenced by submitted_at. |
| `employee_id`  | STRING | yes |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Requester. |
| `leave_type`  | STRING | yes |  | `ANNUAL`, `SICK`, `PERSONAL`, `UNPAID` |  |  |  | Type of leave. |
| `start_date`  | DATE | yes |  |  |  |  |  | First day off. |
| `end_date`  | DATE | yes |  |  |  |  | >= start_date | Last day off. |
| `days_requested`  | DECIMAL | yes |  |  | days |  | >= 0, <= 31 | Derived: calendar days in range excluding holidays that apply to the employee's region. |
| `submitted_at`  | DATETIME | yes |  |  |  |  |  | Submission time. |
| `status`  | STRING | yes |  | `SUBMITTED`, `APPROVED`, `REJECTED`, `CANCELLED`, `EXPIRED` |  |  |  | Current state (projection of leave_request_event). |
| `decided_at`  | DATETIME | no |  |  |  |  | >= submitted_at | Decision time. |
| `decided_by_employee_id`  | STRING | no |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Approving/rejecting manager; null for automatic decisions. |
| `decision_channel`  | STRING | no |  | `AUTO`, `MANAGER` |  |  |  | Who decided. |
| `decision_reason`  | STRING | no |  | `POLICY_COMPLIANT`, `SICK_AUTO_APPROVED`, `INSUFFICIENT_NOTICE`, `INSUFFICIENT_BALANCE`, `ALLOWANCE_EXCEEDED`, `TEAM_CAPACITY`, `DUPLICATE_OVERLAP`, `MANAGER_NO_RESPONSE`, `EMPLOYEE_CANCELLED` |  |  |  | Rule that produced the decision. |
| `cancelled_at`  | DATETIME | no |  |  |  |  | >= decided_at | Cancellation time. |

## leave_request_event

Append-only history of leave state changes.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `leave_event_id` PK | STRING | yes | yes | `LEV-\d{4}-\d{6}` |  |  |  | Primary key, sequenced by event_ts. |
| `leave_id`  | STRING | yes |  | `LVE-\d{4}-\d{6}` |  | `leave_request.leave_id` |  | Leave request. |
| `event_type`  | STRING | yes |  | `SUBMITTED`, `APPROVED`, `REJECTED`, `CANCELLED`, `EXPIRED` |  |  |  | New state. |
| `event_ts`  | DATETIME | yes |  |  |  |  |  | When. |
| `actor_employee_id`  | STRING | no |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Employee or manager who acted; null = system. |
| `reason`  | STRING | no |  | `POLICY_COMPLIANT`, `SICK_AUTO_APPROVED`, `INSUFFICIENT_NOTICE`, `INSUFFICIENT_BALANCE`, `ALLOWANCE_EXCEEDED`, `TEAM_CAPACITY`, `DUPLICATE_OVERLAP`, `MANAGER_NO_RESPONSE`, `EMPLOYEE_CANCELLED` |  |  |  | Rule applied. |

Allowed state transitions: `START` → `SUBMITTED`, `SUBMITTED` → `APPROVED`, `SUBMITTED` → `REJECTED`, `SUBMITTED` → `EXPIRED`, `APPROVED` → `CANCELLED`.

## attendance_event

Badge/mobile clock events. ID = ATT-<employee-id>-<timestamp>.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `attendance_event_id` PK | STRING | yes | yes | `ATT-EMP-\d{6}-\d{8}T\d{6}` |  |  |  | Primary key. |
| `employee_id`  | STRING | yes |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Who clocked. |
| `assignment_id`  | STRING | yes |  | `ASG-\d{4}-\d{7}` |  | `shift_assignment.assignment_id` | Assignment is ACTIVE and belongs to employee_id | Assignment the clock event belongs to. |
| `event_type`  | STRING | yes |  | `CLOCK_IN`, `CLOCK_OUT` |  |  |  | Direction. |
| `event_ts`  | DATETIME | yes |  |  |  |  |  | Clock time (seconds precision). |
| `capture_method`  | STRING | yes |  | `BADGE`, `MOBILE`, `MANUAL` |  |  |  | How it was captured. |

Composite uniqueness: `(employee_id, event_ts)`.

## swap_request

Employee-initiated shift swap. Only APPROVED swaps may be APPLIED; applying supersedes the original assignments and creates new ones.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `swap_id` PK | STRING | yes | yes | `SWP-\d{4}-\d{6}` |  |  |  | Primary key, sequenced by requested_at. |
| `swap_type`  | STRING | yes |  | `EXCHANGE`, `GIVEAWAY` |  |  |  | EXCHANGE trades two shifts; GIVEAWAY hands one shift to a teammate. |
| `team_id`  | STRING | yes |  | `TEAM-\d{3}` |  | `team.team_id` |  | Team whose manager decides. |
| `requester_employee_id`  | STRING | yes |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Employee giving up a shift. |
| `requester_assignment_id`  | STRING | yes |  | `ASG-\d{4}-\d{7}` |  | `shift_assignment.assignment_id` |  | Assignment offered. |
| `target_employee_id`  | STRING | yes |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Teammate taking the shift. |
| `target_assignment_id`  | STRING | no |  | `ASG-\d{4}-\d{7}` |  | `shift_assignment.assignment_id` | Required iff swap_type = EXCHANGE | Target's assignment given back (EXCHANGE only). |
| `requested_at`  | DATETIME | yes |  |  |  |  |  | Request time. |
| `status`  | STRING | yes |  | `REQUESTED`, `APPROVED`, `REJECTED`, `WITHDRAWN`, `APPLIED` |  |  |  | Current state (projection of swap_request_event). |
| `decided_at`  | DATETIME | no |  |  |  |  | >= requested_at | Decision time. |
| `decided_by_employee_id`  | STRING | no |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Deciding manager. |
| `decision_reason`  | STRING | no |  | `CONSTRAINTS_SATISFIED`, `ASSIGNMENT_CHANGED`, `LATE_REQUEST`, `ON_LEAVE`, `DOUBLE_BOOKING`, `REST_RULE`, `CONSECUTIVE_DAYS`, `WEEKLY_HOURS_CAP`, `NIGHT_INELIGIBLE`, `NOT_EMPLOYED`, `SKILL_MISMATCH`, `SKILL_COVERAGE`, `REQUESTER_WITHDREW`, `NOT_ROTA` |  |  |  | Rule that produced the decision. |
| `applied_at`  | DATETIME | no |  |  |  |  | >= decided_at | When the swap was applied. |

## swap_request_event

Append-only history of swap state changes.

| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `swap_event_id` PK | STRING | yes | yes | `SEV-\d{4}-\d{6}` |  |  |  | Primary key, sequenced by event_ts. |
| `swap_id`  | STRING | yes |  | `SWP-\d{4}-\d{6}` |  | `swap_request.swap_id` |  | Swap request. |
| `event_type`  | STRING | yes |  | `REQUESTED`, `APPROVED`, `REJECTED`, `WITHDRAWN`, `APPLIED` |  |  |  | New state. |
| `event_ts`  | DATETIME | yes |  |  |  |  |  | When. |
| `actor_employee_id`  | STRING | no |  | `EMP-\d{6}` |  | `employee.employee_id` |  | Who acted. |
| `reason`  | STRING | no |  | `CONSTRAINTS_SATISFIED`, `ASSIGNMENT_CHANGED`, `LATE_REQUEST`, `ON_LEAVE`, `DOUBLE_BOOKING`, `REST_RULE`, `CONSECUTIVE_DAYS`, `WEEKLY_HOURS_CAP`, `NIGHT_INELIGIBLE`, `NOT_EMPLOYED`, `SKILL_MISMATCH`, `SKILL_COVERAGE`, `REQUESTER_WITHDREW`, `NOT_ROTA` |  |  |  | Rule applied. |

Allowed state transitions: `START` → `REQUESTED`, `REQUESTED` → `APPROVED`, `REQUESTED` → `REJECTED`, `REQUESTED` → `WITHDRAWN`, `APPROVED` → `APPLIED`.

## Output files that are not input tables

**`ground_truth/ground_truth.csv`** (kept outside `data/`, never joined into inputs): `anomaly_id`, `issue_type`, `record_type`, `record_id`, `related_record_ids`, `employee_id`, `team_id`, `shift_id`, `business_date`, `iso_week`, `expected_rule`, `description`. `record_id` uses the ID of the record type named in `record_type`; for `employee_week` it is `EMP-xxxxxx|YYYY-Www`.

**`derived/`** — recomputed from the exported CSVs on every run:

- `weekly_hours.csv`: `employee_id`, `iso_week`, `employment_type`, `contracted_weekly_hours`, `max_weekly_hours`, `scheduled_shifts`, `scheduled_hours`, `overtime_scheduled_hours`, `attended_shifts`, `actual_hours`, `overtime_actual_hours`, `missing_clock_outs`, `cap_exceeded`
- `coverage_status.csv`: `team_id`, `shift_id`, `shift_date`, `template_id`, `day_type`, `requirement`, `required`, `planned`, `final`, `attended`, `planned_gap`, `final_gap`, `attended_gap`
- `coverage_gaps.csv`: `team_id`, `shift_id`, `shift_date`, `template_id`, `day_type`, `requirement`, `required`, `planned`, `final`, `attended`, `final_gap`, `attended_gap`, `gap_stage`, `explanation`
- `attendance_reconciliation.csv`: `assignment_id`, `employee_id`, `team_id`, `shift_id`, `scheduled_start`, `scheduled_end`, `clock_in`, `clock_out`, `scheduled_hours`, `actual_hours`, `start_variance_min`, `end_variance_min`, `outcome`, `stayed_late`, `on_approved_leave`
- `leave_balance.csv`: `employee_id`, `opening_balance_days`, `approved_annual_days`, `closing_balance_days`, `approved_sick_days`, `approved_personal_days`, `approved_unpaid_days`, `requests_total`, `requests_rejected`
- `fairness_by_team.csv`: `team_id`, `rota_members`, `mean_utilisation`, `gini_utilisation`, `min_utilisation`, `max_utilisation`, `night_shifts_mean`, `night_shifts_std`, `unsocial_shifts_mean`, `unsocial_shifts_std`, `overtime_hours_total`
- `exceptions.csv`: `finding_id`, `issue_type`, `category`, `severity`, `record_type`, `record_id`, `related_record_ids`, `employee_id`, `team_id`, `shift_id`, `business_date`, `iso_week`, `rule`, `detail`
