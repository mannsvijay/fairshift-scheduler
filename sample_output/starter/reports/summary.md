# Run summary — starter

Seed `20261022` · window 2026-01-01 → 2026-01-28 (28 days) · generator v1.0.0

**Validation: PASS** (144/144 checks). **Exception detector: precision 1.000, recall 1.000** on 15 labelled anomalies.

## Volumes

| Table | Rows |
|---|---:|
| team | 6 |
| skill | 13 |
| employee | 120 |
| employee_skill | 223 |
| shift_template | 3 |
| holiday_calendar | 11 |
| shift | 84 |
| coverage_requirement | 190 |
| shift_assignment | 1,777 |
| assignment_event | 1,882 |
| leave_request | 100 |
| leave_request_event | 201 |
| attendance_event | 3,287 |
| swap_request | 62 |
| swap_request_event | 154 |

## Exception detection vs ground truth

| Issue type | Labelled | Detected | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOUBLE_BOOKED | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| LEAVE_OVERLAPS_ASSIGNMENT | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| REQUIRED_SKILL_ABSENT | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| OVERTIME_CAP_EXCEEDED | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |
| SWAP_APPLIED_WITHOUT_APPROVAL | 3 | 3 | 3 | 0 | 0 | 1.000 | 1.000 |

Guard rules (constraints the scheduler must never break; expected 0): REST_RULE_VIOLATION=0, CONSECUTIVE_DAYS_EXCEEDED=0, NIGHT_INELIGIBLE_ASSIGNED=0, ASSIGNED_OUTSIDE_EMPLOYMENT=0, MANAGER_ON_ROTA=0

## Coverage

- Requirement checks (team × shift × requirement): 1,728
- Met at publication: 99.9% · final schedule: 99.0% · attended: 97.1%
- Planning gaps recovered by manager top-ups: 0
- Reported gaps by stage: {'ATTENDANCE': 33, 'PLANNING': 2, 'POST_PUBLICATION': 15}
- Cross-team cover assignments: 3

## Working time

- Scheduled hours: 13,376 (overtime 232); actual overtime from late clock-outs: 323
- Employee-weeks with scheduled overtime: 26; over the cap: 3 (all labelled anomalies)

## Fairness

- Mean Gini of utilisation within teams: 0.0739 (worst team 0.0952); 0 = perfectly even
- Mean std-dev of night shifts per 4 weeks: 2.128; of weekend/holiday shifts: 1.097

## Leave, swaps, attendance

- Leave outcomes: {'APPROVED': 80, 'CANCELLED': 1, 'EXPIRED': 5, 'REJECTED': 14}
- Leave decision reasons: {'DUPLICATE_OVERLAP': 5, 'INSUFFICIENT_BALANCE': 1, 'INSUFFICIENT_NOTICE': 1, 'MANAGER_NO_RESPONSE': 5, 'POLICY_COMPLIANT': 54, 'SICK_AUTO_APPROVED': 27, 'TEAM_CAPACITY': 7}
- Swap outcomes: {'APPLIED': 33, 'REJECTED': 24, 'REQUESTED': 3, 'WITHDRAWN': 2}
- Swap decision reasons: {'ASSIGNMENT_CHANGED': 2, 'CONSTRAINTS_SATISFIED': 33, 'DOUBLE_BOOKING': 7, 'LATE_REQUEST': 8, 'ON_LEAVE': 1, 'PENDING': 3, 'REQUESTER_WITHDREW': 2, 'REST_RULE': 5, 'SKILL_MISMATCH': 1}
- Attendance outcomes: {'EARLY_DEPARTURE': 19, 'LATE': 72, 'MISSING_CLOCK_OUT': 9, 'NO_SHOW': 24, 'ON_TIME': 1548}
