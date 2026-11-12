# Reproducibility check — scale `starter`, seed `20261022`

Two independent processes with different `PYTHONHASHSEED` values generated the dataset.

**Result: IDENTICAL** — 46 files compared by SHA-256, 23 row counts compared.

| File | Bytes | SHA-256 (run 1) | Same in run 2 |
|---|---:|---|---|
| `data/csv/assignment_event.csv` | 166,115 | `87cfe098bc0b7b9d…` | yes |
| `data/csv/attendance_event.csv` | 311,235 | `f354b761d240cbf2…` | yes |
| `data/csv/coverage_requirement.csv` | 10,498 | `9b09528b88f0a48b…` | yes |
| `data/csv/employee.csv` | 15,587 | `42e4992613241dc0…` | yes |
| `data/csv/employee_skill.csv` | 11,122 | `4956e1652dce0a9e…` | yes |
| `data/csv/holiday_calendar.csv` | 888 | `2f2911262608e99c…` | yes |
| `data/csv/leave_request.csv` | 14,504 | `3d521db226dcfe3d…` | yes |
| `data/csv/leave_request_event.csv` | 16,196 | `0b6dc112c0ae2b27…` | yes |
| `data/csv/shift.csv` | 9,401 | `0e8b68e7157b9150…` | yes |
| `data/csv/shift_assignment.csv` | 179,241 | `493f125c29f43391…` | yes |
| `data/csv/shift_template.csv` | 227 | `5cb2cfb7e6b9ae3e…` | yes |
| `data/csv/skill.csv` | 825 | `81bc10dd52069f48…` | yes |
| `data/csv/swap_request.csv` | 10,623 | `ecbd8f6054262561…` | yes |
| `data/csv/swap_request_event.csv` | 13,059 | `2a07d5ddf3082964…` | yes |
| `data/csv/team.csv` | 470 | `472e3207ec1d54f4…` | yes |
| `data/json/assignment_event.json` | 537,636 | `b9a07ac6fc0e68da…` | yes |
| `data/json/attendance_event.json` | 702,310 | `6f3f32163f1021e1…` | yes |
| `data/json/coverage_requirement.json` | 39,741 | `7095c6f854e6d098…` | yes |
| `data/json/employee.json` | 49,695 | `6d0585feffb54cd1…` | yes |
| `data/json/employee_skill.json` | 36,491 | `eb47da15077eca46…` | yes |
| `data/json/holiday_calendar.json` | 2,201 | `367eaf92fabca688…` | yes |
| `data/json/leave_request.json` | 39,002 | `1c5d0da0ffb0ab2e…` | yes |
| `data/json/leave_request_event.json` | 37,901 | `caf547fd1ef80c49…` | yes |
| `data/json/shift.json` | 21,819 | `c09d36099b228e0f…` | yes |
| `data/json/shift_assignment.json` | 553,436 | `56080b9b2bc3dec9…` | yes |
| `data/json/shift_template.json` | 561 | `d772f524ecaaae3f…` | yes |
| `data/json/skill.json` | 2,402 | `95d37a9673152637…` | yes |
| `data/json/swap_request.json` | 27,503 | `77eacf4fa97497e0…` | yes |
| `data/json/swap_request_event.json` | 29,289 | `8460d54288d7feed…` | yes |
| `data/json/team.json` | 1,071 | `0f568f685db927a9…` | yes |
| `data/sql/schema.sql` | 13,423 | `539441c3ad390800…` | yes |
| `data/sql/seed.sql` | 1,001,085 | `0d3228f7f86d21cc…` | yes |
| `derived/attendance_reconciliation.csv` | 295,218 | `b9228a025ba45445…` | yes |
| `derived/coverage_gaps.csv` | 8,486 | `38cb6cdd026d4025…` | yes |
| `derived/coverage_status.csv` | 128,720 | `38a2043baf3dea83…` | yes |
| `derived/exceptions.csv` | 4,135 | `0eebf1828324bc4c…` | yes |
| `derived/fairness_by_team.csv` | 530 | `67370690be8b1f9b…` | yes |
| `derived/leave_balance.csv` | 5,443 | `9af212b1a6a04e22…` | yes |
| `derived/weekly_hours.csv` | 41,618 | `2a00c606ecbd6607…` | yes |
| `ground_truth/ground_truth.csv` | 4,183 | `e892b2bd9c210b6a…` | yes |
| `ground_truth/ground_truth.json` | 7,327 | `f66d2b01dae26761…` | yes |
| `reports/evaluation.json` | 4,615 | `9972d1eff3da6a04…` | yes |
| `reports/report.html` | 53,528 | `9f3cb41b0700eb91…` | yes |
| `reports/summary.md` | 2,703 | `22dce693ef52dc6b…` | yes |
| `reports/validation_summary.json` | 33,679 | `37c266422bcd4841…` | yes |
| `reports/validation_summary.md` | 12,963 | `76ccd6c6c1ad3754…` | yes |

| Table | Rows run 1 | Rows run 2 |
|---|---:|---:|
| team | 6 | 6 |
| skill | 13 | 13 |
| employee | 120 | 120 |
| employee_skill | 223 | 223 |
| shift_template | 3 | 3 |
| holiday_calendar | 11 | 11 |
| shift | 84 | 84 |
| coverage_requirement | 190 | 190 |
| shift_assignment | 1,777 | 1,777 |
| assignment_event | 1,882 | 1,882 |
| leave_request | 100 | 100 |
| leave_request_event | 201 | 201 |
| attendance_event | 3,287 | 3,287 |
| swap_request | 62 | 62 |
| swap_request_event | 154 | 154 |
| derived/attendance_reconciliation | 1,672 | 1,672 |
| derived/weekly_hours | 546 | 546 |
| derived/coverage_status | 1,728 | 1,728 |
| derived/coverage_gaps | 50 | 50 |
| derived/leave_balance | 114 | 114 |
| derived/fairness_by_team | 6 | 6 |
| derived/exceptions | 15 | 15 |
| ground_truth | 15 | 15 |
