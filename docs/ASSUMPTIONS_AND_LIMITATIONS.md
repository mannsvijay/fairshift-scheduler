# Assumptions, deviations, limitations and next steps

## Assumptions

| Area | Assumption | Why |
|---|---|---|
| Domain | Multi-site warehouse + customer support, 5 Indian regions, 5 departments, 13 skills | Gives skills with certifications/expiry, night work and regional holidays |
| Time | Single timezone (site local, Asia/Kolkata); timestamps stored without offset | All sites in one country; avoids DST/offset complexity |
| Shifts | Three fixed 8 h templates (06–14, 14–22, 22–06); breaks paid; a shift belongs to its start date | Common 24/7 pattern; makes the rest rule meaningful (Night → next Early = 0 h rest) |
| Shift IDs | `SHIFT-<date>-<code>` identifies a *dated template instance* shared by all teams | Follows the brief's convention exactly; team-specific needs live in coverage requirements |
| Weeks | Hours and overtime counted per ISO week (Mon–Sun) by shift start date | Standard payroll convention |
| Overtime | Hours above contract (40 FT / 24 PT) are overtime; cap = contract + 8 h | Simple, explicit, configurable in `config.py` |
| Rota | Managers are employees but are not on the shift rota; they approve leave and swaps | Separates approvers from the people being scheduled |
| Coverage | Skill minimums count people holding a *valid* holding on the date; one person can satisfy several skill minimums | Reflects how floors actually work; avoids an artificial one-role-per-person rule |
| Leave | Applies to whole days and all shifts starting on those days; chargeable days exclude regional/national holidays; managers' own leave not modelled | Keeps the leave ↔ schedule interaction unambiguous |
| Leave volume | 5,000 = baseline + labelled anomalies, so the total matches the brief exactly | Requirement fidelity |
| Publication | Week *W* published Monday of *W − 1* at 12:00 | Typical one-week lead time |
| Swaps | Same team only; decided by the team manager; approved swaps applied immediately; overtime within cap allowed for voluntary swaps | Keeps approval authority clear |
| Holidays | Synthetic calendar modelled on Indian public holidays; lunar festival dates marked `APPROXIMATE` | No external data needed; provenance stays clean |
| IDs | Year segment in `LVE/SWP/ASG-YYYY-…` = plan year | The window sits inside 2026 |

## Deviations from the brief (and why)

- **Extra tables** beyond the ten named entities: `shift` (dated instances, required by the ID convention),
  `employee_skill` (N:M bridge) and three event-history tables. The brief asks for bridge tables and preserved history,
  so these implement it rather than deviate from it.
- **Volume of swaps (1,515) and other unspecified volumes** are my choice. The brief only fixes employees, teams,
  days and leave requests.
- **Full dataset is not committed** (~200 MB in three formats). It regenerates identically in ~30 s, and its
  checksums are in `docs/reproducibility_full.md`.

## Limitations

1. **Greedy scheduler, not a global optimiser.** Decisions are made shift by shift. Fairness is good (mean Gini 0.027)
   but not provably optimal, and the engine never revisits earlier days to free someone up.
2. **Fixed shift patterns.** No split shifts, variable lengths, on-call or part-day leave.
3. **Simplified people model.** No individual preferences, availability windows, seniority bidding or
   jurisdiction-specific labour law beyond the configured rules.
4. **Simplified operations.** Leave cancellations do not trigger re-planning; replacement call-ins only use the own
   team; no-shows are not backfilled.
5. **Detector rules mirror the generator's rule definitions.** The perfect scores show that the rules are implemented
   consistently and that injected cases are isolated. They do not show how well the detector would cope with messy
   real-world data, where ambiguous cases would lower precision.
6. **Synthetic data.** Distributions are plausible, but they are not calibrated against a real workforce.

## Next steps

1. Optional CP-SAT (OR-Tools) planner behind the same `ScheduleState.check` interface, compared against the greedy
   planner on fairness and overtime.
2. Employee preferences and availability as soft constraints in the load score.
3. Re-plan on leave cancellation; backfill no-shows from an on-call pool.
4. A small read-only API or UI for managers to review gaps and pending swaps.
5. Property-based tests (e.g. Hypothesis) for the constraint checker.
