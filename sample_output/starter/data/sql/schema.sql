-- Generated from fairshift/schema.py. Portable SQL (tested on SQLite; PostgreSQL-compatible).
-- All foreign keys are DEFERRABLE INITIALLY DEFERRED because team<->employee and
-- shift_assignment<->swap_request reference each other.

CREATE TABLE team (
  team_id TEXT PRIMARY KEY,
  team_name TEXT NOT NULL UNIQUE,
  department TEXT NOT NULL CHECK (department IN ('INBOUND', 'OUTBOUND', 'INVENTORY', 'RETURNS', 'CUSTOMER_SUPPORT')),
  region_code TEXT NOT NULL CHECK (region_code IN ('IN-RJ', 'IN-MH', 'IN-KA', 'IN-TG', 'IN-DL')),
  manager_employee_id TEXT NOT NULL,
  created_date TEXT NOT NULL,
  FOREIGN KEY (manager_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE skill (
  skill_id TEXT PRIMARY KEY,
  skill_code TEXT NOT NULL UNIQUE,
  skill_name TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL CHECK (category IN ('OPERATIONAL', 'SAFETY', 'SYSTEMS', 'CUSTOMER')),
  requires_certification INTEGER NOT NULL CHECK (requires_certification IN (0, 1)),
  certification_validity_days INTEGER
);

CREATE TABLE employee (
  employee_id TEXT PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  team_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('ASSOCIATE', 'SENIOR_ASSOCIATE', 'SHIFT_LEAD', 'MANAGER')),
  employment_type TEXT NOT NULL CHECK (employment_type IN ('FULL_TIME', 'PART_TIME')),
  contracted_weekly_hours REAL NOT NULL,
  max_weekly_hours REAL NOT NULL,
  night_shift_eligible INTEGER NOT NULL CHECK (night_shift_eligible IN (0, 1)),
  hire_date TEXT NOT NULL,
  termination_date TEXT,
  employment_status TEXT NOT NULL CHECK (employment_status IN ('ACTIVE', 'TERMINATED')),
  annual_leave_opening_balance_days REAL NOT NULL,
  FOREIGN KEY (team_id) REFERENCES team(team_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE employee_skill (
  employee_skill_id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  proficiency_level INTEGER NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  FOREIGN KEY (employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (skill_id) REFERENCES skill(skill_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE shift_template (
  template_id TEXT PRIMARY KEY,
  template_code TEXT NOT NULL UNIQUE,
  template_name TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  duration_hours REAL NOT NULL,
  crosses_midnight INTEGER NOT NULL CHECK (crosses_midnight IN (0, 1)),
  is_night INTEGER NOT NULL CHECK (is_night IN (0, 1))
);

CREATE TABLE holiday_calendar (
  holiday_id TEXT PRIMARY KEY,
  calendar_id TEXT NOT NULL,
  holiday_date TEXT NOT NULL,
  holiday_name TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('NATIONAL', 'REGIONAL')),
  region_code TEXT CHECK (region_code IN ('IN-RJ', 'IN-MH', 'IN-KA', 'IN-TG', 'IN-DL')),
  date_precision TEXT NOT NULL CHECK (date_precision IN ('EXACT', 'APPROXIMATE')),
  UNIQUE (holiday_date, scope, region_code)
);

CREATE TABLE shift (
  shift_id TEXT PRIMARY KEY,
  shift_date TEXT NOT NULL,
  template_id TEXT NOT NULL,
  start_datetime TEXT NOT NULL,
  end_datetime TEXT NOT NULL,
  iso_week TEXT NOT NULL,
  is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1)),
  publication_datetime TEXT NOT NULL,
  FOREIGN KEY (template_id) REFERENCES shift_template(template_id) DEFERRABLE INITIALLY DEFERRED,
  UNIQUE (shift_date, template_id)
);

CREATE TABLE coverage_requirement (
  coverage_requirement_id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  template_id TEXT NOT NULL,
  day_type TEXT NOT NULL CHECK (day_type IN ('WEEKDAY', 'WEEKEND', 'HOLIDAY')),
  skill_id TEXT,
  min_headcount INTEGER NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  FOREIGN KEY (team_id) REFERENCES team(team_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (template_id) REFERENCES shift_template(template_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (skill_id) REFERENCES skill(skill_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE shift_assignment (
  assignment_id TEXT PRIMARY KEY,
  shift_id TEXT NOT NULL,
  employee_id TEXT NOT NULL,
  team_id TEXT NOT NULL,
  slot_skill_id TEXT,
  source TEXT NOT NULL CHECK (source IN ('PLANNED', 'REPLACEMENT', 'MANUAL', 'SWAP')),
  status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RELEASED', 'SUPERSEDED')),
  created_at TEXT NOT NULL,
  created_by_employee_id TEXT,
  swap_id TEXT,
  replaces_assignment_id TEXT,
  FOREIGN KEY (shift_id) REFERENCES shift(shift_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (team_id) REFERENCES team(team_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (slot_skill_id) REFERENCES skill(skill_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (created_by_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (swap_id) REFERENCES swap_request(swap_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (replaces_assignment_id) REFERENCES shift_assignment(assignment_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE assignment_event (
  assignment_event_id TEXT PRIMARY KEY,
  assignment_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'RELEASED', 'SUPERSEDED')),
  event_ts TEXT NOT NULL,
  reason TEXT NOT NULL CHECK (reason IN ('SCHEDULE_PUBLISHED', 'LEAVE_REPLACEMENT', 'MANUAL_TOPUP', 'MANUAL_REASSIGNMENT', 'SWAP_APPLIED', 'LEAVE_APPROVED')),
  actor_employee_id TEXT,
  related_leave_id TEXT,
  related_swap_id TEXT,
  related_assignment_id TEXT,
  FOREIGN KEY (assignment_id) REFERENCES shift_assignment(assignment_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (actor_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (related_leave_id) REFERENCES leave_request(leave_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (related_swap_id) REFERENCES swap_request(swap_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (related_assignment_id) REFERENCES shift_assignment(assignment_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE leave_request (
  leave_id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  leave_type TEXT NOT NULL CHECK (leave_type IN ('ANNUAL', 'SICK', 'PERSONAL', 'UNPAID')),
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  days_requested REAL NOT NULL,
  submitted_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED')),
  decided_at TEXT,
  decided_by_employee_id TEXT,
  decision_channel TEXT CHECK (decision_channel IN ('AUTO', 'MANAGER')),
  decision_reason TEXT CHECK (decision_reason IN ('POLICY_COMPLIANT', 'SICK_AUTO_APPROVED', 'INSUFFICIENT_NOTICE', 'INSUFFICIENT_BALANCE', 'ALLOWANCE_EXCEEDED', 'TEAM_CAPACITY', 'DUPLICATE_OVERLAP', 'MANAGER_NO_RESPONSE', 'EMPLOYEE_CANCELLED')),
  cancelled_at TEXT,
  FOREIGN KEY (employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (decided_by_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE leave_request_event (
  leave_event_id TEXT PRIMARY KEY,
  leave_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED')),
  event_ts TEXT NOT NULL,
  actor_employee_id TEXT,
  reason TEXT CHECK (reason IN ('POLICY_COMPLIANT', 'SICK_AUTO_APPROVED', 'INSUFFICIENT_NOTICE', 'INSUFFICIENT_BALANCE', 'ALLOWANCE_EXCEEDED', 'TEAM_CAPACITY', 'DUPLICATE_OVERLAP', 'MANAGER_NO_RESPONSE', 'EMPLOYEE_CANCELLED')),
  FOREIGN KEY (leave_id) REFERENCES leave_request(leave_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (actor_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE attendance_event (
  attendance_event_id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  assignment_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('CLOCK_IN', 'CLOCK_OUT')),
  event_ts TEXT NOT NULL,
  capture_method TEXT NOT NULL CHECK (capture_method IN ('BADGE', 'MOBILE', 'MANUAL')),
  FOREIGN KEY (employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (assignment_id) REFERENCES shift_assignment(assignment_id) DEFERRABLE INITIALLY DEFERRED,
  UNIQUE (employee_id, event_ts)
);

CREATE TABLE swap_request (
  swap_id TEXT PRIMARY KEY,
  swap_type TEXT NOT NULL CHECK (swap_type IN ('EXCHANGE', 'GIVEAWAY')),
  team_id TEXT NOT NULL,
  requester_employee_id TEXT NOT NULL,
  requester_assignment_id TEXT NOT NULL,
  target_employee_id TEXT NOT NULL,
  target_assignment_id TEXT,
  requested_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'APPLIED')),
  decided_at TEXT,
  decided_by_employee_id TEXT,
  decision_reason TEXT CHECK (decision_reason IN ('CONSTRAINTS_SATISFIED', 'ASSIGNMENT_CHANGED', 'LATE_REQUEST', 'ON_LEAVE', 'DOUBLE_BOOKING', 'REST_RULE', 'CONSECUTIVE_DAYS', 'WEEKLY_HOURS_CAP', 'NIGHT_INELIGIBLE', 'NOT_EMPLOYED', 'SKILL_MISMATCH', 'SKILL_COVERAGE', 'REQUESTER_WITHDREW', 'NOT_ROTA')),
  applied_at TEXT,
  FOREIGN KEY (team_id) REFERENCES team(team_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (requester_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (requester_assignment_id) REFERENCES shift_assignment(assignment_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (target_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (target_assignment_id) REFERENCES shift_assignment(assignment_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (decided_by_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE swap_request_event (
  swap_event_id TEXT PRIMARY KEY,
  swap_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('REQUESTED', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'APPLIED')),
  event_ts TEXT NOT NULL,
  actor_employee_id TEXT,
  reason TEXT CHECK (reason IN ('CONSTRAINTS_SATISFIED', 'ASSIGNMENT_CHANGED', 'LATE_REQUEST', 'ON_LEAVE', 'DOUBLE_BOOKING', 'REST_RULE', 'CONSECUTIVE_DAYS', 'WEEKLY_HOURS_CAP', 'NIGHT_INELIGIBLE', 'NOT_EMPLOYED', 'SKILL_MISMATCH', 'SKILL_COVERAGE', 'REQUESTER_WITHDREW', 'NOT_ROTA')),
  FOREIGN KEY (swap_id) REFERENCES swap_request(swap_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (actor_employee_id) REFERENCES employee(employee_id) DEFERRABLE INITIALLY DEFERRED
);

-- Index every foreign-key column: keeps joins fast and lets the database check
-- referential integrity without scanning child tables.
CREATE INDEX idx_team_manager_employee_id ON team(manager_employee_id);
CREATE INDEX idx_employee_team_id ON employee(team_id);
CREATE INDEX idx_employee_skill_employee_id ON employee_skill(employee_id);
CREATE INDEX idx_employee_skill_skill_id ON employee_skill(skill_id);
CREATE INDEX idx_shift_template_id ON shift(template_id);
CREATE INDEX idx_coverage_requirement_team_id ON coverage_requirement(team_id);
CREATE INDEX idx_coverage_requirement_template_id ON coverage_requirement(template_id);
CREATE INDEX idx_coverage_requirement_skill_id ON coverage_requirement(skill_id);
CREATE INDEX idx_shift_assignment_shift_id ON shift_assignment(shift_id);
CREATE INDEX idx_shift_assignment_employee_id ON shift_assignment(employee_id);
CREATE INDEX idx_shift_assignment_team_id ON shift_assignment(team_id);
CREATE INDEX idx_shift_assignment_slot_skill_id ON shift_assignment(slot_skill_id);
CREATE INDEX idx_shift_assignment_created_by_employee_id ON shift_assignment(created_by_employee_id);
CREATE INDEX idx_shift_assignment_swap_id ON shift_assignment(swap_id);
CREATE INDEX idx_shift_assignment_replaces_assignment_id ON shift_assignment(replaces_assignment_id);
CREATE INDEX idx_assignment_event_assignment_id ON assignment_event(assignment_id);
CREATE INDEX idx_assignment_event_actor_employee_id ON assignment_event(actor_employee_id);
CREATE INDEX idx_assignment_event_related_leave_id ON assignment_event(related_leave_id);
CREATE INDEX idx_assignment_event_related_swap_id ON assignment_event(related_swap_id);
CREATE INDEX idx_assignment_event_related_assignment_id ON assignment_event(related_assignment_id);
CREATE INDEX idx_leave_request_employee_id ON leave_request(employee_id);
CREATE INDEX idx_leave_request_decided_by_employee_id ON leave_request(decided_by_employee_id);
CREATE INDEX idx_leave_request_event_leave_id ON leave_request_event(leave_id);
CREATE INDEX idx_leave_request_event_actor_employee_id ON leave_request_event(actor_employee_id);
CREATE INDEX idx_attendance_event_employee_id ON attendance_event(employee_id);
CREATE INDEX idx_attendance_event_assignment_id ON attendance_event(assignment_id);
CREATE INDEX idx_swap_request_team_id ON swap_request(team_id);
CREATE INDEX idx_swap_request_requester_employee_id ON swap_request(requester_employee_id);
CREATE INDEX idx_swap_request_requester_assignment_id ON swap_request(requester_assignment_id);
CREATE INDEX idx_swap_request_target_employee_id ON swap_request(target_employee_id);
CREATE INDEX idx_swap_request_target_assignment_id ON swap_request(target_assignment_id);
CREATE INDEX idx_swap_request_decided_by_employee_id ON swap_request(decided_by_employee_id);
CREATE INDEX idx_swap_request_event_swap_id ON swap_request_event(swap_id);
CREATE INDEX idx_swap_request_event_actor_employee_id ON swap_request_event(actor_employee_id);
