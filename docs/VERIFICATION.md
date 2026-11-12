# How I know it works

Everything below is produced by commands in the README and can be re-run by a reviewer.

## 1. Automated checks on every run

`python -m fairshift generate` exports the data, reads the CSVs back, and runs:

- **144 integrity and acceptance checks** (`reports/validation_summary.md`): parsing, primary keys, required fields,
  enums, ID formats, numeric ranges, uniqueness (incl. composite keys), all 34 foreign keys, conditional rules,
  date ordering, effective-dating overlaps, arithmetic reconciliation (shift durations and ISO weeks, leave days net of
  holidays, leave balances, weekly hours and overtime, coverage gaps), lifecycle state machines and row-vs-event
  timestamps, duplicates, the four acceptance criteria, ground-truth separation, and a load of `schema.sql` +
  `seed.sql` into SQLite with `PRAGMA foreign_keys = ON` plus `foreign_key_check`.
- **Exception detection vs ground truth** (`reports/evaluation.json`): precision 1.000 and recall 1.000 for all five
  issue types at both scales. Five guard rules (rest, consecutive days, night eligibility, employment dates, managers
  off rota) found 0 violations across 91,355 active assignments.

## 2. Tests (`python -m unittest -v`, 27 tests)

- `test_rules.py` exercises each hard constraint in isolation: rest after a night shift (0 h / 8 h / 16 h cases),
  double booking, the 6-day limit, the contract-then-cap tiers, leave, night eligibility, managers off rota, and
  release-keeps-history. It also checks that leave decisions follow the documented rules and that every rejection
  path is exercised.
- `test_pipeline.py` covers the end-to-end starter run: validation passes, the detector is exact, all five edge-case
  types are present, volumes match the configuration, ID conventions hold, IDs are chronological (no leakage), there
  are no label columns, and history is preserved.
- `test_checks_catch_problems.py` holds the **negative tests**. It corrupts data on purpose (a broken FK, an
  overwritten status, a bad enum, reversed dates, a new double-booking, unlabelled violations) and asserts that each
  is caught.
- `test_reproducibility.py` confirms that the same seed gives identical files, a different seed gives different
  data, and custom scales work.

## 3. Reproducibility

`python -m fairshift repro` runs the generator in two separate processes with different `PYTHONHASHSEED` values and
compares the SHA-256 of every file and every row count. Result: identical at starter scale
(`sample_output/starter/reports/reproducibility_report.md`) and at full scale (`docs/reproducibility_full.md`).

## 4. Problems the checks caught during development

These were real bugs, found by the verification layer rather than by inspection:

1. **Leave expired before it was submitted.** A same-day planned-leave request was "expired" at midnight, before its
   submission time. *Caught by:* date-ordering and lifecycle checks. *Fix:* only requests submitted before the leave
   starts can expire; same-day requests fall under the notice rule.
2. **Replacement created "in the future".** Call-in replacements were created inside the leave handler with a later
   timestamp, so another event could release them before they existed. *Caught by:* the lifecycle check
   (`START → RELEASED`). *Fix:* replacements became their own scheduled event.
3. **SQLite load took ~215 s.** Deferred foreign keys scanned unindexed child tables on every parent insert.
   *Fix:* index every FK column (good schema practice anyway); the load now takes ~4.5 s.
4. **Analysis crashed on corrupted data** instead of reporting it. *Caught by:* the negative tests. *Fix:* derive and
   detect skip rows with broken references; the validator reports them.

## 5. Manual review

- The HTML report was rendered and checked in light and dark modes.
- Distributions were sanity-checked against expectations:
  - leave approval about 76% for annual leave, with every rejection reason present;
  - swap approval about 50% across 13 distinct rejection reasons;
  - about 1.2% no-shows, about 4% late arrivals, about 8% staying late.
