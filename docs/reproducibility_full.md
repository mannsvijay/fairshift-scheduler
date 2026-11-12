# Reproducibility check — scale `full`, seed `20261022`

Two independent processes with different `PYTHONHASHSEED` values generated the dataset.

**Result: IDENTICAL** — 29 files compared by SHA-256, 23 row counts compared.

| File | Bytes | SHA-256 (run 1) | Same in run 2 |
|---|---:|---|---|
| `data/csv/assignment_event.csv` | 8,447,401 | `08804ab34fcc5968…` | yes |
| `data/csv/attendance_event.csv` | 17,025,998 | `4a662b701525195b…` | yes |
| `data/csv/coverage_requirement.csv` | 166,484 | `ce9c6a791842e0d9…` | yes |
| `data/csv/employee.csv` | 256,553 | `4be3c019ba061274…` | yes |
| `data/csv/employee_skill.csv` | 192,337 | `ca13766624e86dbd…` | yes |
| `data/csv/holiday_calendar.csv` | 888 | `2f2911262608e99c…` | yes |
| `data/csv/leave_request.csv` | 721,279 | `77062207d09516fc…` | yes |
| `data/csv/leave_request_event.csv` | 819,106 | `9948bc3f0da24dc0…` | yes |
| `data/csv/shift.csv` | 29,993 | `f6c7b49af11c076d…` | yes |
| `data/csv/shift_assignment.csv` | 9,423,383 | `d6ab33941ad6b781…` | yes |
| `data/csv/shift_template.csv` | 227 | `5cb2cfb7e6b9ae3e…` | yes |
| `data/csv/skill.csv` | 825 | `81bc10dd52069f48…` | yes |
| `data/csv/swap_request.csv` | 255,481 | `81aff6a98f3cfe15…` | yes |
| `data/csv/swap_request_event.csv` | 317,821 | `cbd03d1816b8bc86…` | yes |
| `data/csv/team.csv` | 7,014 | `27285e5aad9f4d42…` | yes |
| `derived/attendance_reconciliation.csv` | 16,132,636 | `1e2c151c0343e3e4…` | yes |
| `derived/coverage_gaps.csv` | 377,865 | `a73c93ef055641e0…` | yes |
| `derived/coverage_status.csv` | 6,918,128 | `fbdb02e214d71b9c…` | yes |
| `derived/exceptions.csv` | 26,745 | `0a6af9f19a57aa06…` | yes |
| `derived/fairness_by_team.csv` | 5,976 | `bbfcc2e5fb350f48…` | yes |
| `derived/leave_balance.csv` | 88,002 | `9594d3855e04223e…` | yes |
| `derived/weekly_hours.csv` | 1,952,271 | `c369e0da684307bd…` | yes |
| `ground_truth/ground_truth.csv` | 27,253 | `83066ac9897e0a94…` | yes |
| `ground_truth/ground_truth.json` | 49,027 | `00876ae71db92209…` | yes |
| `reports/evaluation.json` | 4,876 | `7a07908c6253009a…` | yes |
| `reports/report.html` | 1,107,407 | `02903c1edf621a55…` | yes |
| `reports/summary.md` | 2,917 | `2f4419100e6b687e…` | yes |
| `reports/validation_summary.json` | 33,592 | `b9893ec3c55cf556…` | yes |
| `reports/validation_summary.md` | 13,084 | `ba145f21a61f286e…` | yes |

| Table | Rows run 1 | Rows run 2 |
|---|---:|---:|
| team | 100 | 100 |
| skill | 13 | 13 |
| employee | 2,000 | 2,000 |
| employee_skill | 3,948 | 3,948 |
| shift_template | 3 | 3 |
| holiday_calendar | 11 | 11 |
| shift | 270 | 270 |
| coverage_requirement | 3,060 | 3,060 |
| shift_assignment | 94,455 | 94,455 |
| assignment_event | 97,555 | 97,555 |
| leave_request | 5,000 | 5,000 |
| leave_request_event | 10,169 | 10,169 |
| attendance_event | 179,883 | 179,883 |
| swap_request | 1,515 | 1,515 |
| swap_request_event | 3,773 | 3,773 |
| derived/attendance_reconciliation | 91,355 | 91,355 |
| derived/weekly_hours | 25,723 | 25,723 |
| derived/coverage_status | 92,960 | 92,960 |
| derived/coverage_gaps | 2,264 | 2,264 |
| derived/leave_balance | 1,900 | 1,900 |
| derived/fairness_by_team | 100 | 100 |
| derived/exceptions | 100 | 100 |
| ground_truth | 100 | 100 |
