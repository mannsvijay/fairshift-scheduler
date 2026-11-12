"""Clock-in/clock-out events generated from the final schedule.

Rules (generic — they do not know which rows are anomalies):
  * only ACTIVE assignments can be attended;
  * an employee on APPROVED leave that day does not come in;
  * if an employee has overlapping ACTIVE assignments, they attend only the one
    created first (a person cannot be in two places);
  * otherwise behaviour is sampled from a per-(employee, shift) random stream:
    no-show, late arrival, staying late (unplanned overtime), early departure,
    or a forgotten clock-out.
"""
from __future__ import annotations

from datetime import timedelta

from .core import attendance_id, daterange, rng_for


def generate_attendance(ctx, assignments, leaves):
    pol = ctx.policy
    on_leave = set()
    for r in leaves:
        if r["status"] == "APPROVED":
            for d in daterange(r["start_date"], r["end_date"]):
                on_leave.add((r["employee_id"], d))

    active = [a for a in assignments if a["status"] == "ACTIVE"]
    by_emp: dict[str, list] = {}
    for a in active:
        by_emp.setdefault(a["employee_id"], []).append(a)
    unattendable = set()
    for emp, rows in by_emp.items():
        rows.sort(key=lambda a: (ctx.shifts[a["shift_id"]].start, a["created_at"], a["assignment_id"]))
        for i in range(1, len(rows)):
            prev, cur = rows[i - 1], rows[i]
            if ctx.shifts[cur["shift_id"]].start < ctx.shifts[prev["shift_id"]].end:
                later = max(prev, cur, key=lambda a: (a["created_at"], a["assignment_id"]))
                unattendable.add(later["assignment_id"])

    events, used = [], set()

    def emit(emp, asg_id, etype, ts, rng):
        while attendance_id(emp, ts) in used:  # keep IDs unique per employee+second
            ts += timedelta(seconds=1)
        used.add(attendance_id(emp, ts))
        method = rng.choices(["BADGE", "MOBILE", "MANUAL"], weights=[85, 13, 2])[0]
        events.append({"attendance_event_id": attendance_id(emp, ts), "employee_id": emp, "assignment_id": asg_id,
                       "event_type": etype, "event_ts": ts, "capture_method": method})

    for a in sorted(active, key=lambda a: (ctx.shifts[a["shift_id"]].start, a["employee_id"], a["assignment_id"])):
        sh, emp = ctx.shifts[a["shift_id"]], a["employee_id"]
        if a["assignment_id"] in unattendable or (emp, sh.date) in on_leave:
            continue
        rng = rng_for(ctx.seed, "attendance", emp, sh.id)
        if rng.random() < pol.no_show_rate:
            continue
        if rng.random() < pol.late_rate:
            cin = sh.start + timedelta(minutes=rng.uniform(6, 45))
        else:
            cin = sh.start + timedelta(minutes=min(4.0, max(-25.0, rng.gauss(-6, 4))))
        emit(emp, a["assignment_id"], "CLOCK_IN", cin.replace(microsecond=0), rng)
        if rng.random() < pol.missing_clock_out_rate:
            continue
        r = rng.random()
        if r < pol.stay_late_rate:
            cout = sh.end + timedelta(minutes=rng.uniform(30, 120))
        elif r < pol.stay_late_rate + pol.early_departure_rate:
            cout = sh.end - timedelta(minutes=rng.uniform(30, 180))
        else:
            cout = sh.end + timedelta(minutes=min(20.0, max(-4.0, rng.gauss(5, 4))))
        emit(emp, a["assignment_id"], "CLOCK_OUT", cout.replace(microsecond=0), rng)
    events.sort(key=lambda e: (e["event_ts"], e["employee_id"], e["event_type"]))
    return events
