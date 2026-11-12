# Design notes

## 1. Problem framing

The brief asks for an end-to-end workflow that turns leave, coverage needs, skills and labour rules into schedules
that are *feasible* and *fair*, while exposing decisions and exceptions and keeping history. I treated this as three
separable concerns:

1. **A scheduling engine** that never breaks hard constraints and spreads load fairly.
2. **A realistic operational record** — what actually happens after a rota is published (late sick calls,
   swaps, manager edits, no-shows) — kept as append-only events.
3. **An independent verification layer** that reads only the exported files and checks integrity, recomputes
   every derived number, and detects rule violations, scored against a separate ground truth.

Keeping (3) independent of (1) is the core design choice: if the engine and the checker shared code, a bug in
shared logic would be invisible to both.

## 2. Data model decisions

- **`shift` is a dated instance of a template** (`SHIFT-2026-01-01-A`), shared by all teams. The ID convention in the
  brief has no team component, so team-specific staffing lives in `coverage_requirement`, and the team being staffed
  is recorded on each `shift_assignment`. This also makes cross-team cover natural: an assignment's `team_id` can
  differ from the employee's home team.
- **History is never overwritten.** A change ends the old assignment (`RELEASED` or `SUPERSEDED`) and creates a new
  one that points back via `replaces_assignment_id`. Every transition is a row in an event table
  (`assignment_event`, `leave_request_event`, `swap_request_event`). The `status` column is a projection of the event
  log, and the validator checks that the two agree and that transitions follow the state machine.
- **Effective dating** appears where it matters operationally: certifications expire and are renewed as *new*
  `employee_skill` rows (sometimes with a lapse), coverage requirements change mid-window (peak-season uplift), and
  employees join or leave during the window.
- **Coverage semantics.** A requirement row with `skill_id = NULL` is total headcount; otherwise it is the minimum
  number of assigned people holding a *valid* holding of that skill on the date. A person can satisfy several skill
  requirements at once. `slot_skill_id` on an assignment records which requirement the scheduler placed someone to
  cover; it must be held validly (this is the "required skill absent" rule).
- **Foreign keys are `DEFERRABLE INITIALLY DEFERRED`** because there are genuine cycles (team ↔ manager,
  assignment ↔ swap). Every FK column is indexed. Without indexes, SQLite's deferred-FK bookkeeping scanned child
  tables on every parent insert: loading the full seed took ~215 s. With indexes it takes ~4.5 s.

## 3. Scheduling

**Publication.** Week *W* is planned at 12:00 on Monday of *W − 1* using only leave approved by then. Shifts are filled
night-first (fewest eligible people), and within a shift **skill minimums first, scarcest skill first**, then total
headcount.

**Two-tier eligibility.** For each shift, eligible candidates are split into "fits within contracted hours" and
"needs overtime (within cap)". Overtime candidates are only used when the first tier is exhausted. Eligibility of one
person never depends on another person's assignment, so the ranked list is computed once per shift.

**Fairness score** (lower is preferred):
`2 × weekly_hours / contract + cumulative_hours / contract + 0.35 × nights (night shifts) + 0.35 × weekend/holiday
shifts (on those days) + 0.5 × holiday shifts (on holidays) [+ 0.15 × scarce skills held, for general slots]`,
plus a tiny seeded tie-breaker. The scarce-skill term keeps skill holders available for the slots only they can fill.

**Why greedy rather than an optimiser.** A MILP/CP-SAT model would give provably optimal rotas, but it would add a
heavy dependency, make the 2,000-person run much slower, and make decisions harder to explain line by line. The
greedy engine is transparent, fast (~3.5 s for 90 days × 100 teams), and its fairness can be measured directly (mean
Gini 0.027). The trade-off is local decisions: it cannot, for example, move someone from Tuesday to free them for a
hard-to-fill Thursday. This is listed as the main next step.

## 4. Operations timeline (event-driven)

After publication, reality happens. All events go through one priority queue in timestamp order against one live
state, so each decision only sees what was known at that moment:

| Event | Behaviour |
|---|---|
| `LEAVE_APPROVED` on a published day | Release the assignment (reason `LEAVE_APPROVED`, linked to the leave), then schedule a call-in replacement 10–90 min later if ≥ 2 h remain before the shift |
| `REPLACE` | Pick the best eligible teammate (skill-qualified if the slot needs it); otherwise the gap stays and is reported |
| `TOPUP` | 1–3 days after publication, a manager may cover remaining gaps from the own team or a sister team (same department and region) |
| `SWAP_REQUEST` → `SWAP_DECISION` | Manager decides by rule; approved swaps are applied atomically: originals `SUPERSEDED`, new `SWAP` assignments created |
| `REASSIGN` | Manager moves a shift to another qualified teammate without breaking coverage |
| `LEAVE_CANCELLED` | Frees the days (no automatic re-scheduling) |

An early version created replacements *inside* the leave handler with a future timestamp. A later event could then
release a replacement "before" it existed. The validator's lifecycle check caught this, and replacements became their
own scheduled event.

**Swap rule** (in order): assignment still active → requested ≥ 24 h before every shift involved and not yet started
→ both people pass every hard constraint after the exchange → slot skill held by the new person → no skill
requirement that is currently met drops below its minimum. Requesters usually pre-arrange with a colleague who can
take the shift (70%), and sometimes ask regardless, so every rejection path is exercised.

## 5. Leave decisions

Requests are generated with realistic timing (planned leave 3–60 days ahead, some short-notice; sick leave called
in on the morning or the evening before; demand peaks around holidays and Mondays/Fridays). They are decided by
replaying them in decision-time order, so balances and team concurrency reflect earlier decisions:

| # | Rule | Outcome |
|---|---|---|
| 1 | Submitted before the leave starts, but the manager decision would land on/after day one | `EXPIRED` (`MANAGER_NO_RESPONSE`) |
| 2 | Overlaps the employee's own approved leave | `REJECTED` (`DUPLICATE_OVERLAP`) |
| 3 | Sick leave | `APPROVED` automatically |
| 4 | Notice < 3 days | `REJECTED` (`INSUFFICIENT_NOTICE`) |
| 5 | Annual days > remaining balance | `REJECTED` (`INSUFFICIENT_BALANCE`) |
| 6 | Personal > 3 days in window, or unpaid > 10 days | `REJECTED` (`ALLOWANCE_EXCEEDED`) |
| 7 | Any day already at the team cap (15% of rota) | `REJECTED` (`TEAM_CAPACITY`) |
| 8 | Otherwise | `APPROVED` (`POLICY_COMPLIANT`) |

6% of approved annual/personal leave is later cancelled, which restores balance and capacity. Chargeable days exclude
holidays that apply to the employee's region; this is recomputed and checked by the validator.

## 6. Edge cases and ground truth

Each of the five required edge cases is injected **after** the valid baseline, as a plausible event recorded
through the normal append-only mechanisms:

| Issue | Injected as | Detected by |
|---|---|---|
| Double-booked | A sister team "borrows" someone for a shift they already work | Overlapping ACTIVE assignments |
| Approved leave overlaps assignment | A 1-day personal leave approved without releasing the published shift | ACTIVE assignment on an approved-leave date |
| Required skill absent | Manual reassignment of a skill slot to someone who never held the skill or whose certification **just expired** | Slot skill not validly held on the date |
| Overtime cap exceeded | Manual top-ups push a part-timer past 32 h in an ISO week | Weekly scheduled hours > `max_weekly_hours` |
| Swap applied without approval | Self-service change applied while the swap is pending or withdrawn | `SWAP` assignment with no prior `APPROVED` event |

Isolation rules make the evaluation meaningful:
- each injection must pass **every other** rule, so it triggers exactly one detector;
- each touches a fresh employee and team-shift, so injections never interact;
- double-bookings are only placed where the extra 8 h stays within the cap;
- injected leave respects notice, allowance and team capacity.

Part-timers are used for the overtime case because a full-timer cannot exceed 48 h with 8-hour shifts without
working 7 days in a row, which would also break the consecutive-days rule.

**No leakage.** Ground truth lives in `ground_truth/`, never in input tables (the validator checks for label-like
columns). A subtler leak was the ID sequence: injected rows created last would get the highest IDs. All sequenced IDs
are therefore assigned *after* injection, in order of each record's own creation timestamp; a test asserts IDs are
chronological. Organic manual top-ups, cross-team loans, manager reassignments and pending swaps also exist in the
baseline, so `source = MANUAL` or a cross-team `team_id` do not identify an anomaly on their own.

Downstream consequences are realistic, not hand-written. Attendance follows generic rules: nobody clocks in while on
approved leave, and a double-booked person attends only the assignment created first. Injected anomalies therefore
show up as real no-shows and attendance gaps.

## 7. Reproducibility

- Every component draws from its own RNG stream derived from `sha256(seed, component, keys)`. Attendance and
  tie-breaks use per-record streams, so changing one part never shifts another part's random numbers.
- No wall-clock time is written into data; output formatting is fixed (column order, 2-dp decimals, LF endings).
- Python randomises string hashing per process, so nothing that affects output iterates a `set` of strings.
  `repro` deliberately runs two processes with different `PYTHONHASHSEED` values to prove this.

## 8. Verification layer

- `derive.py` rebuilds its own lookups (day types, holidays, skill validity, requirements) from the CSVs, so derived
  numbers are an independent recomputation, not a copy of the engine's state.
- `detect.py` implements the five evaluated rules plus five **guard** rules the engine promises never to break
  (expected count 0).
- `validate.py` runs 144 checks (see `reports/validation_summary.md`) including a load of `schema.sql` + `seed.sql`
  into SQLite with foreign keys enforced.
- Negative tests deliberately corrupt data (bad FK, overwritten history, bad enum, reversed dates, a new
  double-booking) and assert that each is caught.

## 9. Performance

Full scale: generation ~7 s, export ~7 s, reload + derive + detect + validate (incl. SQLite) ~14 s. The engine is
O(teams × shifts × team size); every check is O(1) via per-employee date and week indexes.
