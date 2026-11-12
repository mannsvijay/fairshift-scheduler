"""Data validation over the *exported* files.

Checks are grouped as in the brief (Step 8) plus the four acceptance criteria.
Integrity checks must all PASS. Injected anomalies are business-rule violations,
not integrity errors, so they never make a check fail; the acceptance checks
instead require every rule violation to be accounted for in ground truth.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from .core import daterange, hours_between, iso_week_label
from .derive import Reference
from .schema import EVENT_LOGS, FORBIDDEN_INPUT_COLUMNS, STATUS_FROM_EVENT, TABLE_BY_NAME, TABLES, TIME


class Report:
    def __init__(self):
        self.checks = []

    def add(self, category, name, failures, checked, detail=""):
        failures = list(failures)
        self.checks.append({"category": category, "check": name, "status": "PASS" if not failures else "FAIL",
                            "records_checked": checked, "failures": len(failures),
                            "examples": [str(f) for f in failures[:5]], "detail": detail})

    @property
    def ok(self):
        return all(c["status"] == "PASS" for c in self.checks)


def validate(t: dict, derived: dict, truth: list, findings: list, policy, parse_errors: list,
             sql_paths: tuple[Path, Path] | None) -> Report:
    rep = Report()
    ref = Reference(t)
    rep.add("parsing", "CSV headers match schema and every value parses as its declared type", parse_errors,
            sum(len(v) for v in t.values()))

    # ------------------------------------------------------------------ keys, types, enums, patterns
    index = {}
    for tb in TABLES:
        rows = t[tb.name]
        pks = [r[tb.pk] for r in rows]
        dup = [k for k, n in Counter(pks).items() if n > 1]
        rep.add("primary_keys", f"{tb.name}.{tb.pk} unique and non-null", dup + [None] * pks.count(None), len(rows))
        index[tb.name] = set(pks)
    for tb in TABLES:
        rows = t[tb.name]
        req_fail, enum_fail, pat_fail, range_fail, uniq_fail = [], [], [], [], []
        for c in tb.columns:
            rx = re.compile(c.pattern) if c.pattern else None
            seen = Counter()
            for r in rows:
                v = r.get(c.name)
                if v is None:
                    if c.required:
                        req_fail.append(f"{r[tb.pk]}.{c.name}")
                    continue
                if c.enum and v not in c.enum:
                    enum_fail.append(f"{r[tb.pk]}.{c.name}={v}")
                if rx and not rx.fullmatch(str(v)):
                    pat_fail.append(f"{r[tb.pk]}.{c.name}={v}")
                if c.type == TIME and not re.fullmatch(r"\d{2}:\d{2}", v):
                    pat_fail.append(f"{r[tb.pk]}.{c.name}={v}")
                if c.min is not None and v < c.min or c.max is not None and v > c.max:
                    range_fail.append(f"{r[tb.pk]}.{c.name}={v}")
                if c.unique:
                    seen[v] += 1
            uniq_fail += [f"{tb.name}.{c.name}={v}" for v, n in seen.items() if n > 1]
        for group in tb.unique_together:
            keys = Counter(tuple(r[g] for g in group) for r in rows)
            uniq_fail += [f"{tb.name}{group}={k}" for k, n in keys.items() if n > 1]
        n = len(rows)
        rep.add("required_fields", f"{tb.name}: required columns populated", req_fail, n)
        rep.add("allowed_values", f"{tb.name}: enum values allowed", enum_fail, n)
        rep.add("formats", f"{tb.name}: ID/code formats match conventions", pat_fail, n)
        rep.add("ranges", f"{tb.name}: numeric values within declared ranges", range_fail, n)
        rep.add("uniqueness", f"{tb.name}: unique columns and composite keys", uniq_fail, n)

    # ------------------------------------------------------------------ foreign keys
    for tb in TABLES:
        for c in tb.columns:
            if c.fk:
                parent = c.fk.split(".")[0]
                bad = [f"{r[tb.pk]}.{c.name}={r[c.name]}" for r in t[tb.name]
                       if r[c.name] is not None and r[c.name] not in index[parent]]
                rep.add("foreign_keys", f"{tb.name}.{c.name} -> {c.fk}", bad, len(t[tb.name]))

    # ------------------------------------------------------------------ conditional / semantic rules
    sem = []
    for r in t["skill"]:
        if (r["certification_validity_days"] is not None) != r["requires_certification"]:
            sem.append(r["skill_id"])
    for r in t["holiday_calendar"]:
        if (r["region_code"] is not None) != (r["scope"] == "REGIONAL"):
            sem.append(r["holiday_id"])
    for r in t["team"]:
        m = ref.emp.get(r["manager_employee_id"])
        if not m or m["role"] != "MANAGER" or m["team_id"] != r["team_id"]:
            sem.append(r["team_id"])
    end = ref.window[1]
    for e in t["employee"]:
        if e["max_weekly_hours"] < e["contracted_weekly_hours"]:
            sem.append(e["employee_id"])
        if (e["employment_status"] == "TERMINATED") != bool(e["termination_date"] and e["termination_date"] <= end):
            sem.append(e["employee_id"])
    for a in t["shift_assignment"]:
        if (a["source"] == "SWAP") != (a["swap_id"] is not None):
            sem.append(a["assignment_id"])
    for s in t["swap_request"]:
        if (s["swap_type"] == "EXCHANGE") != (s["target_assignment_id"] is not None):
            sem.append(s["swap_id"])
    rep.add("conditional_rules", "Conditional required fields and role/ownership rules (see data dictionary)", sem,
            sum(len(t[x]) for x in ("skill", "holiday_calendar", "team", "employee", "shift_assignment", "swap_request")))

    # ------------------------------------------------------------------ date ordering
    bad = []
    bad += [e["employee_id"] for e in t["employee"] if e["termination_date"] and e["termination_date"] < e["hire_date"]]
    bad += [r["employee_skill_id"] for r in t["employee_skill"] if r["valid_to"] and r["valid_to"] < r["valid_from"]]
    bad += [r["coverage_requirement_id"] for r in t["coverage_requirement"] if r["effective_to"] and r["effective_to"] < r["effective_from"]]
    bad += [r["team_id"] for r in t["team"] if r["created_date"] > ref.window[0]]
    for lv in t["leave_request"]:
        if lv["end_date"] < lv["start_date"] or (lv["decided_at"] and lv["decided_at"] < lv["submitted_at"]) \
                or (lv["cancelled_at"] and (not lv["decided_at"] or lv["cancelled_at"] < lv["decided_at"])):
            bad.append(lv["leave_id"])
    for s in t["swap_request"]:
        if (s["decided_at"] and s["decided_at"] < s["requested_at"]) or \
                (s["applied_at"] and (not s["decided_at"] or s["applied_at"] < s["decided_at"])):
            bad.append(s["swap_id"])
    for s in t["shift"]:
        if not (s["publication_datetime"] < s["start_datetime"] < s["end_datetime"]):
            bad.append(s["shift_id"])
    for a in t["shift_assignment"]:
        if a["shift_id"] not in ref.shift:
            continue  # reported under foreign keys
        if a["created_at"] >= ref.shift[a["shift_id"]]["start_datetime"]:
            bad.append(a["assignment_id"])
        if a["source"] == "PLANNED" and a["created_at"] != ref.shift[a["shift_id"]]["publication_datetime"]:
            bad.append(a["assignment_id"])
    rep.add("date_ordering", "start<=end, submitted<=decided<=cancelled/applied, published<start<end, created before shift",
            bad, sum(len(t[x]) for x in ("employee", "employee_skill", "coverage_requirement", "leave_request",
                                          "swap_request", "shift", "shift_assignment")))

    # ------------------------------------------------------------------ effective-dated periods never overlap
    bad = []
    periods = defaultdict(list)
    for r in t["employee_skill"]:
        periods[("skill", r["employee_id"], r["skill_id"])].append((r["valid_from"], r["valid_to"] or date.max))
    for r in t["coverage_requirement"]:
        periods[("cov", r["team_id"], r["template_id"], r["day_type"], r["skill_id"])].append(
            (r["effective_from"], r["effective_to"] or date.max))
    for k, ps in periods.items():
        ps.sort()
        for (f1, t1), (f2, _t2) in zip(ps, ps[1:]):
            if f2 <= t1:
                bad.append(k)
    rep.add("effective_dating", "Skill holdings and coverage requirements have non-overlapping effective periods",
            bad, len(periods))

    # ------------------------------------------------------------------ arithmetic reconciliation
    tpl_code = {k: v["template_code"] for k, v in ref.tpl.items()}
    bad = []
    for s in t["shift"]:
        tp = ref.tpl[s["template_id"]]
        if abs(hours_between(s["start_datetime"], s["end_datetime"]) - tp["duration_hours"]) > 1e-9 \
                or s["shift_id"] != f"SHIFT-{s['shift_date'].isoformat()}-{tpl_code[s['template_id']]}" \
                or s["iso_week"] != iso_week_label(s["shift_date"]) \
                or s["start_datetime"].strftime("%H:%M") != tp["start_time"] \
                or s["is_weekend"] != (s["shift_date"].weekday() >= 5):
            bad.append(s["shift_id"])
    for tp in t["shift_template"]:
        st = datetime.strptime(tp["start_time"], "%H:%M")
        en = datetime.strptime(tp["end_time"], "%H:%M")
        if tp["crosses_midnight"]:
            en += timedelta(days=1)
        if abs(hours_between(st, en) - tp["duration_hours"]) > 1e-9:
            bad.append(tp["template_id"])
    rep.add("arithmetic", "Shift IDs, times, durations and ISO weeks reconcile with templates", bad,
            len(t["shift"]) + len(t["shift_template"]))

    bad = []
    for lv in t["leave_request"]:
        if lv["employee_id"] not in ref.emp or not lv["start_date"] or not lv["end_date"]:
            bad.append(lv["leave_id"])
            continue
        region = ref.team[ref.emp[lv["employee_id"]]["team_id"]]["region_code"]
        expect = sum(1 for d in daterange(lv["start_date"], lv["end_date"])
                     if not ({"*", region} & ref.hol.get(d, set())))
        if abs(expect - lv["days_requested"]) > 1e-9:
            bad.append(lv["leave_id"])
    rep.add("arithmetic", "leave_request.days_requested = calendar days minus applicable holidays", bad, len(t["leave_request"]))

    bad = [b["employee_id"] for b in derived["leave_balance"]
           if abs(b["opening_balance_days"] - b["approved_annual_days"] - b["closing_balance_days"]) > 1e-9
           or b["closing_balance_days"] < 0]
    rep.add("arithmetic", "Leave balance: closing = opening - approved annual days, and never negative", bad,
            len(derived["leave_balance"]))

    total_sched = sum(ref.shift_hours(a["shift_id"]) for a in ref.active)
    weekly_sum = sum(w["scheduled_hours"] for w in derived["weekly_hours"])
    bad = [] if abs(total_sched - weekly_sum) < 1e-6 else [f"{weekly_sum} != {total_sched}"]
    bad += [f"{w['employee_id']}|{w['iso_week']}" for w in derived["weekly_hours"]
            if abs(w["overtime_scheduled_hours"] - max(0.0, w["scheduled_hours"] - w["contracted_weekly_hours"])) > 1e-6]
    rep.add("arithmetic", "Weekly hours sum to all active assignment hours; overtime = max(0, scheduled - contracted)",
            bad, len(derived["weekly_hours"]))

    bad = [r for r in derived["coverage_status"]
           if r["final_gap"] != max(0, r["required"] - r["final"]) or r["planned_gap"] != max(0, r["required"] - r["planned"])]
    rep.add("arithmetic", "Coverage gaps = max(0, required - staffed) at each stage", bad, len(derived["coverage_status"]))

    # ------------------------------------------------------------------ lifecycle / event history
    for txn, (log, fk) in EVENT_LOGS.items():
        lifecycle = TABLE_BY_NAME[log].lifecycle
        events = defaultdict(list)
        for e in t[log]:
            events[e[fk]].append(e)
        pk = TABLE_BY_NAME[txn].pk
        bad = []
        for row in t[txn]:
            evs = sorted(events.get(row[pk], []), key=lambda e: (e["event_ts"], e[TABLE_BY_NAME[log].pk]))
            state = ""
            for e in evs:
                if e["event_type"] not in lifecycle.get(state, ()):
                    bad.append(f"{row[pk]}: {state or 'START'} -> {e['event_type']}")
                    break
                state = e["event_type"]
            if not evs or STATUS_FROM_EVENT[txn].get(state) != row["status"]:
                bad.append(f"{row[pk]}: status {row['status']} vs last event {state}")
        rep.add("lifecycle", f"{txn}: event history follows the state machine and matches current status", bad, len(t[txn]))

    bad = []
    first = defaultdict(dict)
    for e in t["assignment_event"]:
        first[e["assignment_id"]].setdefault(e["event_type"], e["event_ts"])
    for a in t["shift_assignment"]:
        if first[a["assignment_id"]].get("CREATED") != a["created_at"]:
            bad.append(a["assignment_id"])
    lev = defaultdict(dict)
    for e in t["leave_request_event"]:
        lev[e["leave_id"]][e["event_type"]] = e["event_ts"]
    for lv in t["leave_request"]:
        if lev[lv["leave_id"]].get("SUBMITTED") != lv["submitted_at"]:
            bad.append(lv["leave_id"])
        if lv["cancelled_at"] and lev[lv["leave_id"]].get("CANCELLED") != lv["cancelled_at"]:
            bad.append(lv["leave_id"])
    sev = defaultdict(dict)
    for e in t["swap_request_event"]:
        sev[e["swap_id"]][e["event_type"]] = e["event_ts"]
    for s in t["swap_request"]:
        if sev[s["swap_id"]].get("REQUESTED") != s["requested_at"] or \
                (s["applied_at"] and sev[s["swap_id"]].get("APPLIED") != s["applied_at"]):
            bad.append(s["swap_id"])
    rep.add("lifecycle", "Row timestamps (created/submitted/requested/applied/cancelled) equal their event timestamps",
            bad, len(t["shift_assignment"]) + len(t["leave_request"]) + len(t["swap_request"]))

    # ------------------------------------------------------------------ duplicates
    bad = []
    for name, cols in (("shift_assignment", ("shift_id", "employee_id", "team_id", "status", "created_at")),
                       ("leave_request", ("employee_id", "leave_type", "start_date", "end_date", "submitted_at")),
                       ("swap_request", ("requester_assignment_id", "target_employee_id", "requested_at")),
                       ("attendance_event", ("employee_id", "event_type", "event_ts"))):
        c = Counter(tuple(r[x] for x in cols) for r in t[name])
        bad += [f"{name}{k}" for k, n in c.items() if n > 1]
    rep.add("duplicates", "No duplicate business records (same content under different IDs)", bad,
            sum(len(t[x]) for x in ("shift_assignment", "leave_request", "swap_request", "attendance_event")))

    # ------------------------------------------------------------------ acceptance criteria from the brief
    gap_keys = {(g["team_id"], g["shift_id"], g["requirement"]) for g in derived["coverage_gaps"]}
    missing = [(r["team_id"], r["shift_id"], r["requirement"]) for r in derived["coverage_status"]
               if (r["final_gap"] or r["attended_gap"]) and (r["team_id"], r["shift_id"], r["requirement"]) not in gap_keys]
    rep.add("acceptance", "AC1 Coverage requirements are met or the gap is reported (every shortfall is in coverage_gaps)",
            missing, len(derived["coverage_status"]))

    truth_keys = {(g["issue_type"], g["record_id"]) for g in truth}
    unexplained = [f"{f['issue_type']}:{f['record_id']}" for f in findings
                   if f["category"] == "GUARD" or (f["issue_type"], f["record_id"]) not in truth_keys]
    rep.add("acceptance", "AC2 Working-hour constraints hold: every rest/consecutive/overtime/booking violation is a labelled anomaly",
            unexplained, len(ref.active))

    bad = []
    att_by_asg = defaultdict(list)
    for e in t["attendance_event"]:
        a = ref.asg.get(e["assignment_id"])
        if a is None or a["status"] != "ACTIVE" or a["employee_id"] != e["employee_id"]:
            bad.append(e["attendance_event_id"])
        att_by_asg[e["assignment_id"]].append(e)
    for k, evs in att_by_asg.items():
        types = Counter(e["event_type"] for e in evs)
        if types["CLOCK_IN"] != 1 or types["CLOCK_OUT"] > 1:
            bad.append(k)
        ins = [e["event_ts"] for e in evs if e["event_type"] == "CLOCK_IN"]
        outs = [e["event_ts"] for e in evs if e["event_type"] == "CLOCK_OUT"]
        if ins and outs and outs[0] <= ins[0]:
            bad.append(k)
        if outs and not ins:
            bad.append(k)
    if len(derived["attendance_reconciliation"]) != sum(1 for a in t["shift_assignment"] if a["status"] == "ACTIVE"):
        bad.append("reconciliation does not cover every ACTIVE assignment")
    rep.add("acceptance", "AC3 Attendance reconciles with schedules (events only on ACTIVE assignments of the same "
                          "employee, one IN, at most one OUT, OUT after IN)", bad, len(t["attendance_event"]))

    bad = []
    for a in t["shift_assignment"]:
        if a["source"] == "SWAP":
            old = ref.asg.get(a["replaces_assignment_id"])
            if not old or old["status"] != "SUPERSEDED" or old["shift_id"] != a["shift_id"]:
                bad.append(a["assignment_id"])
    for s in t["swap_request"]:
        req = ref.asg.get(s["requester_assignment_id"])
        if req is None:
            bad.append(s["swap_id"])
            continue
        if req["employee_id"] != s["requester_employee_id"] or req["team_id"] != s["team_id"]:
            bad.append(s["swap_id"])
        if s["target_assignment_id"] and ref.asg.get(s["target_assignment_id"], {}).get("employee_id") != s["target_employee_id"]:
            bad.append(s["swap_id"])
    produced = defaultdict(int)
    for a in t["shift_assignment"]:
        if a["swap_id"]:
            produced[a["swap_id"]] += 1
    for s in t["swap_request"]:
        if s["status"] == "APPLIED" and produced[s["swap_id"]] != (2 if s["swap_type"] == "EXCHANGE" else 1):
            bad.append(s["swap_id"])
    rep.add("acceptance", "AC4 Swap history preserved: originals kept as SUPERSEDED, new rows link back, applied swaps "
                          "produced the right number of assignments", bad, len(t["swap_request"]))

    # ------------------------------------------------------------------ ground truth separation
    leaks = [f"{tb.name}.{c.name}" for tb in TABLES for c in tb.columns if c.name in FORBIDDEN_INPUT_COLUMNS]
    known = {"shift_assignment": index["shift_assignment"], "leave_request": index["leave_request"],
             "swap_request": index["swap_request"]}
    for g in truth:
        if g["record_type"] in known and g["record_id"] not in known[g["record_type"]]:
            leaks.append(f"ground truth refers to unknown {g['record_id']}")
        if g["record_type"] == "employee_week" and g["employee_id"] not in index["employee"]:
            leaks.append(f"ground truth refers to unknown {g['employee_id']}")
    rep.add("ground_truth", "Ground truth is separate (no label columns in inputs) and every label points at a real record",
            leaks, len(truth))

    # ------------------------------------------------------------------ SQL round trip
    if sql_paths:
        schema_sql, seed_sql = sql_paths
        problems = []
        try:
            con = sqlite3.connect(":memory:")
            con.execute("PRAGMA foreign_keys = ON")
            con.executescript(schema_sql.read_text(encoding="utf-8"))
            con.executescript(seed_sql.read_text(encoding="utf-8"))
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            problems += [f"fk: {x}" for x in fk[:5]]
            for tb in TABLES:
                n = con.execute(f"SELECT COUNT(*) FROM {tb.name}").fetchone()[0]
                if n != len(t[tb.name]):
                    problems.append(f"{tb.name}: sqlite {n} rows vs csv {len(t[tb.name])}")
            con.close()
        except sqlite3.Error as exc:
            problems.append(f"sqlite error: {exc}")
        rep.add("sql", "schema.sql + seed.sql load into SQLite with FOREIGN KEYS ON; row counts match CSV", problems,
                sum(len(v) for v in t.values()))
    return rep


def render_markdown(rep: Report, title: str) -> str:
    lines = [f"# {title}", "", f"**Overall: {'PASS' if rep.ok else 'FAIL'}** — "
             f"{sum(c['status'] == 'PASS' for c in rep.checks)}/{len(rep.checks)} checks passed.", "",
             "| Category | Check | Status | Records checked | Failures |", "|---|---|---|---:|---:|"]
    for c in rep.checks:
        lines.append(f"| {c['category']} | {c['check']} | {c['status']} | {c['records_checked']:,} | {c['failures']} |")
    fails = [c for c in rep.checks if c["status"] == "FAIL"]
    if fails:
        lines += ["", "## Failure examples", ""]
        for c in fails:
            lines.append(f"- **{c['check']}**: {', '.join(c['examples'])}")
    return "\n".join(lines) + "\n"
