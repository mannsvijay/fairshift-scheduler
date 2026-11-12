# Entity-relationship diagram

Generated from `fairshift/schema.py`. Every relationship is 1:N from parent to child;
`employee_skill` is the bridge table that resolves the N:M between `employee` and `skill`.

```mermaid
erDiagram
    employee ||--o{ team : "manager_employee_id"
    team ||--o{ employee : "team_id"
    employee ||--o{ employee_skill : "employee_id"
    skill ||--o{ employee_skill : "skill_id"
    shift_template ||--o{ shift : "template_id"
    team ||--o{ coverage_requirement : "team_id"
    shift_template ||--o{ coverage_requirement : "template_id"
    skill |o--o{ coverage_requirement : "skill_id"
    shift ||--o{ shift_assignment : "shift_id"
    employee ||--o{ shift_assignment : "employee_id"
    team ||--o{ shift_assignment : "team_id"
    skill |o--o{ shift_assignment : "slot_skill_id"
    employee |o--o{ shift_assignment : "created_by_employee_id"
    swap_request |o--o{ shift_assignment : "swap_id"
    shift_assignment |o--o{ shift_assignment : "replaces_assignment_id"
    shift_assignment ||--o{ assignment_event : "assignment_id"
    employee |o--o{ assignment_event : "actor_employee_id"
    leave_request |o--o{ assignment_event : "related_leave_id"
    swap_request |o--o{ assignment_event : "related_swap_id"
    shift_assignment |o--o{ assignment_event : "related_assignment_id"
    employee ||--o{ leave_request : "employee_id"
    employee |o--o{ leave_request : "decided_by_employee_id"
    leave_request ||--o{ leave_request_event : "leave_id"
    employee |o--o{ leave_request_event : "actor_employee_id"
    employee ||--o{ attendance_event : "employee_id"
    shift_assignment ||--o{ attendance_event : "assignment_id"
    team ||--o{ swap_request : "team_id"
    employee ||--o{ swap_request : "requester_employee_id"
    shift_assignment ||--o{ swap_request : "requester_assignment_id"
    employee ||--o{ swap_request : "target_employee_id"
    shift_assignment |o--o{ swap_request : "target_assignment_id"
    employee |o--o{ swap_request : "decided_by_employee_id"
    swap_request ||--o{ swap_request_event : "swap_id"
    employee |o--o{ swap_request_event : "actor_employee_id"
    team {
        string team_id PK
        string team_name
        string department
        string region_code
        string manager_employee_id FK
        date created_date
    }
    skill {
        string skill_id PK
        string skill_code
        string skill_name
        string category
        boolean requires_certification
        integer certification_validity_days
    }
    employee {
        string employee_id PK
        string first_name
        string last_name
        string email
        string team_id FK
        string role
        string employment_type
        decimal contracted_weekly_hours
        decimal max_weekly_hours
        boolean night_shift_eligible
        date hire_date
        date termination_date
        string employment_status
        decimal annual_leave_opening_balance_days
    }
    employee_skill {
        string employee_skill_id PK
        string employee_id FK
        string skill_id FK
        integer proficiency_level
        date valid_from
        date valid_to
    }
    shift_template {
        string template_id PK
        string template_code
        string template_name
        time start_time
        time end_time
        decimal duration_hours
        boolean crosses_midnight
        boolean is_night
    }
    holiday_calendar {
        string holiday_id PK
        string calendar_id
        date holiday_date
        string holiday_name
        string scope
        string region_code
        string date_precision
    }
    shift {
        string shift_id PK
        date shift_date
        string template_id FK
        datetime start_datetime
        datetime end_datetime
        string iso_week
        boolean is_weekend
        datetime publication_datetime
    }
    coverage_requirement {
        string coverage_requirement_id PK
        string team_id FK
        string template_id FK
        string day_type
        string skill_id FK
        integer min_headcount
        date effective_from
        date effective_to
    }
    shift_assignment {
        string assignment_id PK
        string shift_id FK
        string employee_id FK
        string team_id FK
        string slot_skill_id FK
        string source
        string status
        datetime created_at
        string created_by_employee_id FK
        string swap_id FK
        string replaces_assignment_id FK
    }
    assignment_event {
        string assignment_event_id PK
        string assignment_id FK
        string event_type
        datetime event_ts
        string reason
        string actor_employee_id FK
        string related_leave_id FK
        string related_swap_id FK
        string related_assignment_id FK
    }
    leave_request {
        string leave_id PK
        string employee_id FK
        string leave_type
        date start_date
        date end_date
        decimal days_requested
        datetime submitted_at
        string status
        datetime decided_at
        string decided_by_employee_id FK
        string decision_channel
        string decision_reason
        datetime cancelled_at
    }
    leave_request_event {
        string leave_event_id PK
        string leave_id FK
        string event_type
        datetime event_ts
        string actor_employee_id FK
        string reason
    }
    attendance_event {
        string attendance_event_id PK
        string employee_id FK
        string assignment_id FK
        string event_type
        datetime event_ts
        string capture_method
    }
    swap_request {
        string swap_id PK
        string swap_type
        string team_id FK
        string requester_employee_id FK
        string requester_assignment_id FK
        string target_employee_id FK
        string target_assignment_id FK
        datetime requested_at
        string status
        datetime decided_at
        string decided_by_employee_id FK
        string decision_reason
        datetime applied_at
    }
    swap_request_event {
        string swap_event_id PK
        string swap_id FK
        string event_type
        datetime event_ts
        string actor_employee_id FK
        string reason
    }
```

## Relationship list

| Parent | Child | Foreign key | Cardinality | Optional |
|---|---|---|---|---|
| employee | team | `manager_employee_id` | 1:N | no |
| team | employee | `team_id` | 1:N | no |
| employee | employee_skill | `employee_id` | 1:N | no |
| skill | employee_skill | `skill_id` | 1:N | no |
| shift_template | shift | `template_id` | 1:N | no |
| team | coverage_requirement | `team_id` | 1:N | no |
| shift_template | coverage_requirement | `template_id` | 1:N | no |
| skill | coverage_requirement | `skill_id` | 1:N | yes |
| shift | shift_assignment | `shift_id` | 1:N | no |
| employee | shift_assignment | `employee_id` | 1:N | no |
| team | shift_assignment | `team_id` | 1:N | no |
| skill | shift_assignment | `slot_skill_id` | 1:N | yes |
| employee | shift_assignment | `created_by_employee_id` | 1:N | yes |
| swap_request | shift_assignment | `swap_id` | 1:N | yes |
| shift_assignment | shift_assignment | `replaces_assignment_id` | 1:N | yes |
| shift_assignment | assignment_event | `assignment_id` | 1:N | no |
| employee | assignment_event | `actor_employee_id` | 1:N | yes |
| leave_request | assignment_event | `related_leave_id` | 1:N | yes |
| swap_request | assignment_event | `related_swap_id` | 1:N | yes |
| shift_assignment | assignment_event | `related_assignment_id` | 1:N | yes |
| employee | leave_request | `employee_id` | 1:N | no |
| employee | leave_request | `decided_by_employee_id` | 1:N | yes |
| leave_request | leave_request_event | `leave_id` | 1:N | no |
| employee | leave_request_event | `actor_employee_id` | 1:N | yes |
| employee | attendance_event | `employee_id` | 1:N | no |
| shift_assignment | attendance_event | `assignment_id` | 1:N | no |
| team | swap_request | `team_id` | 1:N | no |
| employee | swap_request | `requester_employee_id` | 1:N | no |
| shift_assignment | swap_request | `requester_assignment_id` | 1:N | no |
| employee | swap_request | `target_employee_id` | 1:N | no |
| shift_assignment | swap_request | `target_assignment_id` | 1:N | yes |
| employee | swap_request | `decided_by_employee_id` | 1:N | yes |
| swap_request | swap_request_event | `swap_id` | 1:N | no |
| employee | swap_request_event | `actor_employee_id` | 1:N | yes |

Many-to-many: `employee` N:M `skill` through `employee_skill` (effective-dated rows; a renewed certification is a new row).

Circular references (`team.manager_employee_id` ↔ `employee.team_id`, `shift_assignment.swap_id` ↔ `swap_request.requester_assignment_id`) are why all FKs are declared `DEFERRABLE INITIALLY DEFERRED`.
