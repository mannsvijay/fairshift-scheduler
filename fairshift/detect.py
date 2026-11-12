"""Business-rule exception detector + evaluation against ground truth.

The detector only reads the exported input tables (never ground truth) and
re-implements each rule independently of the scheduling engine.

EVALUATED rules correspond to the five required edge cases and are scored for
precision/recall against ground_truth. GUARD rules are constraints the engine
promises never to break; any finding there is an engine bug (expected count 0).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from .core import hours_between
from .derive import Reference

FINDING_COLUMNS = ["finding_id", "issue_type", "category", "severity", "record_type", "record_id",
                   "related_record_ids", "employee_id", "team_id", "shift_id", "business_date", "iso_week",
                   "rule", "detail"]

GUARD_TYPES = ("REST_RULE_VIOLATION", "CONSECUTIVE_DAYS_EXCEEDED", "NIGHT_INELIGIBLE_ASSIGNED",
               "ASSIGNED_OUTSIDE_EMPLOYMENT", "MANAGER_ON_ROTA")


def detect(ref: Reference, policy) -> list[dict]:
    t = ref.t
    findings = []

    def add(issue, cat, sev, rtype, rid, related, emp, team, shift, week, rule, detail):
        s = ref.shift.get(shift) if shift else None
        findings.append({"issue_type": issue, "category": cat, "severity": sev, "record_type": rtype,
                         "record_id": rid, "related_record_ids": sorted(related), "employee_id": emp,
                         "team_id": team, "shift_id": shift, "business_date": s["shift_date"] if s else None,
                         "iso_week": week or (s["iso_week"] if s else None), "rule": rule, "detail": detail})

    by_emp = defaultdict(list)
    for a in ref.active:
        by_emp[a["employee_id"]].append(a)

    # ---- DOUBLE_BOOKED: overlapping ACTIVE assignments of one employee
    for emp, rows in by_emp.items():
        rows.sort(key=lambda a: (ref.shift[a["shift_id"]]["start_datetime"], a["created_at"], a["assignment_id"]))
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                si, sj = ref.shift[rows[i]["shift_id"]], ref.shift[rows[j]["shift_id"]]
                if sj["start_datetime"] >= si["end_datetime"]:
                    break
                later = max(rows[i], rows[j], key=lambda a: (a["created_at"], a["assignment_id"]))
                other = rows[i] if later is rows[j] else rows[j]
                add("DOUBLE_BOOKED", "EVALUATED", "HIGH", "shift_assignment", later["assignment_id"],
                    [other["assignment_id"]], emp, later["team_id"], later["shift_id"], None,
                    "No two ACTIVE assignments of one employee may overlap",
                    f"Overlaps {other['assignment_id']} ({other['team_id']}).")

    # ---- LEAVE_OVERLAPS_ASSIGNMENT
    for a in ref.active:
        s = ref.shift[a["shift_id"]]
        leave = ref.approved_leave.get((a["employee_id"], s["shift_date"]))
        if leave:
            add("LEAVE_OVERLAPS_ASSIGNMENT", "EVALUATED", "HIGH", "leave_request", leave, [a["assignment_id"]],
                a["employee_id"], a["team_id"], a["shift_id"], None,
                "An employee on APPROVED leave must not hold an ACTIVE assignment that day",
                f"{a['assignment_id']} was not released.")

    # ---- REQUIRED_SKILL_ABSENT: skill slot held without a valid holding
    for a in ref.active:
        if a["slot_skill_id"]:
            s = ref.shift[a["shift_id"]]
            if not ref.has_skill(a["employee_id"], a["slot_skill_id"], s["shift_date"]):
                expired = any(to is not None and to < s["shift_date"]
                              for _f, to in ref.holdings.get((a["employee_id"], a["slot_skill_id"]), ()))
                add("REQUIRED_SKILL_ABSENT", "EVALUATED", "HIGH", "shift_assignment", a["assignment_id"], [],
                    a["employee_id"], a["team_id"], a["shift_id"], None,
                    "A skill slot must be filled by a valid holder of that skill",
                    f"{a['slot_skill_id']}: " + ("certification expired" if expired else "skill not held"))

    # ---- OVERTIME_CAP_EXCEEDED (scheduled hours per ISO week)
    week_hours = defaultdict(float)
    week_asg = defaultdict(list)
    for a in ref.active:
        s = ref.shift[a["shift_id"]]
        week_hours[(a["employee_id"], s["iso_week"])] += ref.shift_hours(a["shift_id"])
        week_asg[(a["employee_id"], s["iso_week"])].append(a["assignment_id"])
    for (emp, week), h in sorted(week_hours.items()):
        cap = ref.emp[emp]["max_weekly_hours"]
        if h > cap + 1e-9:
            add("OVERTIME_CAP_EXCEEDED", "EVALUATED", "HIGH", "employee_week", f"{emp}|{week}", week_asg[(emp, week)],
                emp, ref.emp[emp]["team_id"], None, week, "Weekly scheduled hours must not exceed max_weekly_hours",
                f"{h:.0f}h scheduled vs {cap:.0f}h cap.")

    # ---- SWAP_APPLIED_WITHOUT_APPROVAL
    flagged = set()
    for a in t["shift_assignment"]:
        if a["source"] != "SWAP":
            continue
        sid = a["swap_id"]
        if sid not in ref.swap:
            continue  # broken reference: reported by the validator
        approved = [e for e in ref.swap_events.get(sid, ()) if e["event_type"] == "APPROVED"
                    and e["event_ts"] <= a["created_at"]]
        if not approved and sid not in flagged:
            flagged.add(sid)
            sw = ref.swap[sid]
            related = [x["assignment_id"] for x in t["shift_assignment"] if x["swap_id"] == sid]
            related.append(sw["requester_assignment_id"])
            add("SWAP_APPLIED_WITHOUT_APPROVAL", "EVALUATED", "HIGH", "swap_request", sid, set(related),
                sw["requester_employee_id"], sw["team_id"], a["shift_id"], None,
                "Assignments may only change through a swap after an APPROVED decision",
                f"Swap status is {sw['status']} but {a['assignment_id']} was created from it.")

    # ---- GUARD rules (engine promises these never happen)
    rest = timedelta(hours=policy.min_rest_hours)
    for emp, rows in by_emp.items():
        rows = sorted(rows, key=lambda a: ref.shift[a["shift_id"]]["start_datetime"])
        e = ref.emp[emp]
        if e["role"] == "MANAGER":
            add("MANAGER_ON_ROTA", "GUARD", "MEDIUM", "employee", emp, [r["assignment_id"] for r in rows], emp,
                e["team_id"], None, None, "Managers are not on the shift rota", f"{len(rows)} assignments")
        for a, b in zip(rows, rows[1:]):
            sa, sb = ref.shift[a["shift_id"]], ref.shift[b["shift_id"]]
            if sb["start_datetime"] < sa["end_datetime"]:
                continue  # overlap is DOUBLE_BOOKED, not a rest problem
            if sb["start_datetime"] - sa["end_datetime"] < rest:
                add("REST_RULE_VIOLATION", "GUARD", "MEDIUM", "shift_assignment", b["assignment_id"], [a["assignment_id"]],
                    emp, b["team_id"], b["shift_id"], None, f"At least {policy.min_rest_hours:.0f}h rest between shifts",
                    f"{hours_between(sa['end_datetime'], sb['start_datetime']):.1f}h rest")
        dates = sorted({ref.shift[a["shift_id"]]["shift_date"] for a in rows})
        run = 1
        for x, y in zip(dates, dates[1:]):
            run = run + 1 if (y - x).days == 1 else 1
            if run == policy.max_consecutive_days + 1:
                add("CONSECUTIVE_DAYS_EXCEEDED", "GUARD", "MEDIUM", "employee", f"{emp}|{y.isoformat()}", [], emp,
                    e["team_id"], None, None, f"At most {policy.max_consecutive_days} consecutive working days",
                    f"run reaches {run} days on {y}")
        for a in rows:
            s = ref.shift[a["shift_id"]]
            if ref.tpl[s["template_id"]]["is_night"] and not e["night_shift_eligible"]:
                add("NIGHT_INELIGIBLE_ASSIGNED", "GUARD", "MEDIUM", "shift_assignment", a["assignment_id"], [], emp,
                    a["team_id"], a["shift_id"], None, "Night shifts need night_shift_eligible", "")
            d = s["shift_date"]
            if d < e["hire_date"] or (e["termination_date"] and d > e["termination_date"]):
                add("ASSIGNED_OUTSIDE_EMPLOYMENT", "GUARD", "HIGH", "shift_assignment", a["assignment_id"], [], emp,
                    a["team_id"], a["shift_id"], None, "Assignments only within employment dates", str(d))

    findings.sort(key=lambda f: (f["category"], f["issue_type"], str(f["business_date"] or ""), f["record_id"]))
    for i, f in enumerate(findings, start=1):
        f["finding_id"] = f"EXC-{i:06d}"
    return findings


def evaluate(findings: list[dict], truth: list[dict], issue_types) -> dict:
    """Precision / recall / F1 per issue type, matching on (issue_type, record_id)."""
    per_type = {}
    found = {(f["issue_type"], f["record_id"]) for f in findings if f["category"] == "EVALUATED"}
    expected = {(g["issue_type"], g["record_id"]) for g in truth}
    for it in issue_types:
        f = {x for x in found if x[0] == it}
        g = {x for x in expected if x[0] == it}
        tp, fp, fn = len(f & g), len(f - g), len(g - f)
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        per_type[it] = {"ground_truth": len(g), "detected": len(f), "true_positive": tp, "false_positive": fp,
                        "false_negative": fn, "precision": round(p, 4), "recall": round(r, 4),
                        "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
                        "false_positive_ids": sorted(x[1] for x in f - g)[:20],
                        "false_negative_ids": sorted(x[1] for x in g - f)[:20]}
    tp = sum(v["true_positive"] for v in per_type.values())
    fp = sum(v["false_positive"] for v in per_type.values())
    fn = sum(v["false_negative"] for v in per_type.values())
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    guard = defaultdict(int)
    for x in findings:
        if x["category"] == "GUARD":
            guard[x["issue_type"]] += 1
    return {"per_issue_type": per_type,
            "overall": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "precision": round(p, 4),
                        "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0},
            "guard_rule_findings": {g: guard.get(g, 0) for g in GUARD_TYPES}}
