# Validation summary — starter

**Overall: PASS** — 144/144 checks passed.

| Category | Check | Status | Records checked | Failures |
|---|---|---|---:|---:|
| parsing | CSV headers match schema and every value parses as its declared type | PASS | 8,113 | 0 |
| primary_keys | team.team_id unique and non-null | PASS | 6 | 0 |
| primary_keys | skill.skill_id unique and non-null | PASS | 13 | 0 |
| primary_keys | employee.employee_id unique and non-null | PASS | 120 | 0 |
| primary_keys | employee_skill.employee_skill_id unique and non-null | PASS | 223 | 0 |
| primary_keys | shift_template.template_id unique and non-null | PASS | 3 | 0 |
| primary_keys | holiday_calendar.holiday_id unique and non-null | PASS | 11 | 0 |
| primary_keys | shift.shift_id unique and non-null | PASS | 84 | 0 |
| primary_keys | coverage_requirement.coverage_requirement_id unique and non-null | PASS | 190 | 0 |
| primary_keys | shift_assignment.assignment_id unique and non-null | PASS | 1,777 | 0 |
| primary_keys | assignment_event.assignment_event_id unique and non-null | PASS | 1,882 | 0 |
| primary_keys | leave_request.leave_id unique and non-null | PASS | 100 | 0 |
| primary_keys | leave_request_event.leave_event_id unique and non-null | PASS | 201 | 0 |
| primary_keys | attendance_event.attendance_event_id unique and non-null | PASS | 3,287 | 0 |
| primary_keys | swap_request.swap_id unique and non-null | PASS | 62 | 0 |
| primary_keys | swap_request_event.swap_event_id unique and non-null | PASS | 154 | 0 |
| required_fields | team: required columns populated | PASS | 6 | 0 |
| allowed_values | team: enum values allowed | PASS | 6 | 0 |
| formats | team: ID/code formats match conventions | PASS | 6 | 0 |
| ranges | team: numeric values within declared ranges | PASS | 6 | 0 |
| uniqueness | team: unique columns and composite keys | PASS | 6 | 0 |
| required_fields | skill: required columns populated | PASS | 13 | 0 |
| allowed_values | skill: enum values allowed | PASS | 13 | 0 |
| formats | skill: ID/code formats match conventions | PASS | 13 | 0 |
| ranges | skill: numeric values within declared ranges | PASS | 13 | 0 |
| uniqueness | skill: unique columns and composite keys | PASS | 13 | 0 |
| required_fields | employee: required columns populated | PASS | 120 | 0 |
| allowed_values | employee: enum values allowed | PASS | 120 | 0 |
| formats | employee: ID/code formats match conventions | PASS | 120 | 0 |
| ranges | employee: numeric values within declared ranges | PASS | 120 | 0 |
| uniqueness | employee: unique columns and composite keys | PASS | 120 | 0 |
| required_fields | employee_skill: required columns populated | PASS | 223 | 0 |
| allowed_values | employee_skill: enum values allowed | PASS | 223 | 0 |
| formats | employee_skill: ID/code formats match conventions | PASS | 223 | 0 |
| ranges | employee_skill: numeric values within declared ranges | PASS | 223 | 0 |
| uniqueness | employee_skill: unique columns and composite keys | PASS | 223 | 0 |
| required_fields | shift_template: required columns populated | PASS | 3 | 0 |
| allowed_values | shift_template: enum values allowed | PASS | 3 | 0 |
| formats | shift_template: ID/code formats match conventions | PASS | 3 | 0 |
| ranges | shift_template: numeric values within declared ranges | PASS | 3 | 0 |
| uniqueness | shift_template: unique columns and composite keys | PASS | 3 | 0 |
| required_fields | holiday_calendar: required columns populated | PASS | 11 | 0 |
| allowed_values | holiday_calendar: enum values allowed | PASS | 11 | 0 |
| formats | holiday_calendar: ID/code formats match conventions | PASS | 11 | 0 |
| ranges | holiday_calendar: numeric values within declared ranges | PASS | 11 | 0 |
| uniqueness | holiday_calendar: unique columns and composite keys | PASS | 11 | 0 |
| required_fields | shift: required columns populated | PASS | 84 | 0 |
| allowed_values | shift: enum values allowed | PASS | 84 | 0 |
| formats | shift: ID/code formats match conventions | PASS | 84 | 0 |
| ranges | shift: numeric values within declared ranges | PASS | 84 | 0 |
| uniqueness | shift: unique columns and composite keys | PASS | 84 | 0 |
| required_fields | coverage_requirement: required columns populated | PASS | 190 | 0 |
| allowed_values | coverage_requirement: enum values allowed | PASS | 190 | 0 |
| formats | coverage_requirement: ID/code formats match conventions | PASS | 190 | 0 |
| ranges | coverage_requirement: numeric values within declared ranges | PASS | 190 | 0 |
| uniqueness | coverage_requirement: unique columns and composite keys | PASS | 190 | 0 |
| required_fields | shift_assignment: required columns populated | PASS | 1,777 | 0 |
| allowed_values | shift_assignment: enum values allowed | PASS | 1,777 | 0 |
| formats | shift_assignment: ID/code formats match conventions | PASS | 1,777 | 0 |
| ranges | shift_assignment: numeric values within declared ranges | PASS | 1,777 | 0 |
| uniqueness | shift_assignment: unique columns and composite keys | PASS | 1,777 | 0 |
| required_fields | assignment_event: required columns populated | PASS | 1,882 | 0 |
| allowed_values | assignment_event: enum values allowed | PASS | 1,882 | 0 |
| formats | assignment_event: ID/code formats match conventions | PASS | 1,882 | 0 |
| ranges | assignment_event: numeric values within declared ranges | PASS | 1,882 | 0 |
| uniqueness | assignment_event: unique columns and composite keys | PASS | 1,882 | 0 |
| required_fields | leave_request: required columns populated | PASS | 100 | 0 |
| allowed_values | leave_request: enum values allowed | PASS | 100 | 0 |
| formats | leave_request: ID/code formats match conventions | PASS | 100 | 0 |
| ranges | leave_request: numeric values within declared ranges | PASS | 100 | 0 |
| uniqueness | leave_request: unique columns and composite keys | PASS | 100 | 0 |
| required_fields | leave_request_event: required columns populated | PASS | 201 | 0 |
| allowed_values | leave_request_event: enum values allowed | PASS | 201 | 0 |
| formats | leave_request_event: ID/code formats match conventions | PASS | 201 | 0 |
| ranges | leave_request_event: numeric values within declared ranges | PASS | 201 | 0 |
| uniqueness | leave_request_event: unique columns and composite keys | PASS | 201 | 0 |
| required_fields | attendance_event: required columns populated | PASS | 3,287 | 0 |
| allowed_values | attendance_event: enum values allowed | PASS | 3,287 | 0 |
| formats | attendance_event: ID/code formats match conventions | PASS | 3,287 | 0 |
| ranges | attendance_event: numeric values within declared ranges | PASS | 3,287 | 0 |
| uniqueness | attendance_event: unique columns and composite keys | PASS | 3,287 | 0 |
| required_fields | swap_request: required columns populated | PASS | 62 | 0 |
| allowed_values | swap_request: enum values allowed | PASS | 62 | 0 |
| formats | swap_request: ID/code formats match conventions | PASS | 62 | 0 |
| ranges | swap_request: numeric values within declared ranges | PASS | 62 | 0 |
| uniqueness | swap_request: unique columns and composite keys | PASS | 62 | 0 |
| required_fields | swap_request_event: required columns populated | PASS | 154 | 0 |
| allowed_values | swap_request_event: enum values allowed | PASS | 154 | 0 |
| formats | swap_request_event: ID/code formats match conventions | PASS | 154 | 0 |
| ranges | swap_request_event: numeric values within declared ranges | PASS | 154 | 0 |
| uniqueness | swap_request_event: unique columns and composite keys | PASS | 154 | 0 |
| foreign_keys | team.manager_employee_id -> employee.employee_id | PASS | 6 | 0 |
| foreign_keys | employee.team_id -> team.team_id | PASS | 120 | 0 |
| foreign_keys | employee_skill.employee_id -> employee.employee_id | PASS | 223 | 0 |
| foreign_keys | employee_skill.skill_id -> skill.skill_id | PASS | 223 | 0 |
| foreign_keys | shift.template_id -> shift_template.template_id | PASS | 84 | 0 |
| foreign_keys | coverage_requirement.team_id -> team.team_id | PASS | 190 | 0 |
| foreign_keys | coverage_requirement.template_id -> shift_template.template_id | PASS | 190 | 0 |
| foreign_keys | coverage_requirement.skill_id -> skill.skill_id | PASS | 190 | 0 |
| foreign_keys | shift_assignment.shift_id -> shift.shift_id | PASS | 1,777 | 0 |
| foreign_keys | shift_assignment.employee_id -> employee.employee_id | PASS | 1,777 | 0 |
| foreign_keys | shift_assignment.team_id -> team.team_id | PASS | 1,777 | 0 |
| foreign_keys | shift_assignment.slot_skill_id -> skill.skill_id | PASS | 1,777 | 0 |
| foreign_keys | shift_assignment.created_by_employee_id -> employee.employee_id | PASS | 1,777 | 0 |
| foreign_keys | shift_assignment.swap_id -> swap_request.swap_id | PASS | 1,777 | 0 |
| foreign_keys | shift_assignment.replaces_assignment_id -> shift_assignment.assignment_id | PASS | 1,777 | 0 |
| foreign_keys | assignment_event.assignment_id -> shift_assignment.assignment_id | PASS | 1,882 | 0 |
| foreign_keys | assignment_event.actor_employee_id -> employee.employee_id | PASS | 1,882 | 0 |
| foreign_keys | assignment_event.related_leave_id -> leave_request.leave_id | PASS | 1,882 | 0 |
| foreign_keys | assignment_event.related_swap_id -> swap_request.swap_id | PASS | 1,882 | 0 |
| foreign_keys | assignment_event.related_assignment_id -> shift_assignment.assignment_id | PASS | 1,882 | 0 |
| foreign_keys | leave_request.employee_id -> employee.employee_id | PASS | 100 | 0 |
| foreign_keys | leave_request.decided_by_employee_id -> employee.employee_id | PASS | 100 | 0 |
| foreign_keys | leave_request_event.leave_id -> leave_request.leave_id | PASS | 201 | 0 |
| foreign_keys | leave_request_event.actor_employee_id -> employee.employee_id | PASS | 201 | 0 |
| foreign_keys | attendance_event.employee_id -> employee.employee_id | PASS | 3,287 | 0 |
| foreign_keys | attendance_event.assignment_id -> shift_assignment.assignment_id | PASS | 3,287 | 0 |
| foreign_keys | swap_request.team_id -> team.team_id | PASS | 62 | 0 |
| foreign_keys | swap_request.requester_employee_id -> employee.employee_id | PASS | 62 | 0 |
| foreign_keys | swap_request.requester_assignment_id -> shift_assignment.assignment_id | PASS | 62 | 0 |
| foreign_keys | swap_request.target_employee_id -> employee.employee_id | PASS | 62 | 0 |
| foreign_keys | swap_request.target_assignment_id -> shift_assignment.assignment_id | PASS | 62 | 0 |
| foreign_keys | swap_request.decided_by_employee_id -> employee.employee_id | PASS | 62 | 0 |
| foreign_keys | swap_request_event.swap_id -> swap_request.swap_id | PASS | 154 | 0 |
| foreign_keys | swap_request_event.actor_employee_id -> employee.employee_id | PASS | 154 | 0 |
| conditional_rules | Conditional required fields and role/ownership rules (see data dictionary) | PASS | 1,989 | 0 |
| date_ordering | start<=end, submitted<=decided<=cancelled/applied, published<start<end, created before shift | PASS | 2,556 | 0 |
| effective_dating | Skill holdings and coverage requirements have non-overlapping effective periods | PASS | 394 | 0 |
| arithmetic | Shift IDs, times, durations and ISO weeks reconcile with templates | PASS | 87 | 0 |
| arithmetic | leave_request.days_requested = calendar days minus applicable holidays | PASS | 100 | 0 |
| arithmetic | Leave balance: closing = opening - approved annual days, and never negative | PASS | 114 | 0 |
| arithmetic | Weekly hours sum to all active assignment hours; overtime = max(0, scheduled - contracted) | PASS | 546 | 0 |
| arithmetic | Coverage gaps = max(0, required - staffed) at each stage | PASS | 1,728 | 0 |
| lifecycle | shift_assignment: event history follows the state machine and matches current status | PASS | 1,777 | 0 |
| lifecycle | leave_request: event history follows the state machine and matches current status | PASS | 100 | 0 |
| lifecycle | swap_request: event history follows the state machine and matches current status | PASS | 62 | 0 |
| lifecycle | Row timestamps (created/submitted/requested/applied/cancelled) equal their event timestamps | PASS | 1,939 | 0 |
| duplicates | No duplicate business records (same content under different IDs) | PASS | 5,226 | 0 |
| acceptance | AC1 Coverage requirements are met or the gap is reported (every shortfall is in coverage_gaps) | PASS | 1,728 | 0 |
| acceptance | AC2 Working-hour constraints hold: every rest/consecutive/overtime/booking violation is a labelled anomaly | PASS | 1,672 | 0 |
| acceptance | AC3 Attendance reconciles with schedules (events only on ACTIVE assignments of the same employee, one IN, at most one OUT, OUT after IN) | PASS | 3,287 | 0 |
| acceptance | AC4 Swap history preserved: originals kept as SUPERSEDED, new rows link back, applied swaps produced the right number of assignments | PASS | 62 | 0 |
| ground_truth | Ground truth is separate (no label columns in inputs) and every label points at a real record | PASS | 15 | 0 |
| sql | schema.sql + seed.sql load into SQLite with FOREIGN KEYS ON; row counts match CSV | PASS | 8,113 | 0 |
