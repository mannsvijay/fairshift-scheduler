"""Derived values, computed only from the exported source tables.

This module deliberately does not import the scheduling engine: it rebuilds its
own lookups from the CSV data, so every derived number is an independent
recomputation from source records (and a cross-check on the generator).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .core import daterange, hours_between


class Reference:
    """Lookups over a loaded dataset."""

    def __init__(self, t: dict[str, list[dict]]):
        self.t = t
        self.emp = {r["employee_id"]: r for r in t["employee"]}
        self.team = {r["team_id"]: r for r in t["team"]}
        self.tpl = {r["template_id"]: r for r in t["shift_template"]}
        self.shift = {r["shift_id"]: r for r in t["shift"]}
        self.asg = {r["assignment_id"]: r for r in t["shift_assignment"]}
        self.swap = {r["swap_id"]: r for r in t["swap_request"]}
        self.window = (min(r["shift_date"] for r in t["shift"]), max(r["shift_date"] for r in t["shift"]))
        self.hol = defaultdict(set)
        for h in t["holiday_calendar"]:
            self.hol[h["holiday_date"]].add(h["region_code"] or "*")
        self.holdings = defaultdict(list)
        for h in t["employee_skill"]:
            self.holdings[(h["employee_id"], h["skill_id"])].append((h["valid_from"], h["valid_to"]))
        self.req = defaultdict(list)
        for r in t["coverage_requirement"]:
            self.req[(r["team_id"], r["template_id"], r["day_type"])].append(r)
        self.approved_leave = {}
        for lv in t["leave_request"]:
            if lv["status"] == "APPROVED" and lv["start_date"] and lv["end_date"]:
                for d in daterange(lv["start_date"], lv["end_date"]):
                    self.approved_leave[(lv["employee_id"], d)] = lv["leave_id"]
        self.swap_events = defaultdict(list)
        for e in t["swap_request_event"]:
            self.swap_events[e["swap_id"]].append(e)
        self.att = defaultdict(list)
        for e in t["attendance_event"]:
            self.att[e["assignment_id"]].append(e)
        # Rows with broken references are reported by the validator; analysis skips them rather than crash.
        self.active = [a for a in t["shift_assignment"] if a["status"] == "ACTIVE"
                       and a["employee_id"] in self.emp and a["shift_id"] in self.shift and a["team_id"] in self.team]

    def day_type(self, team_id: str, d: date) -> str:
        regions = self.hol.get(d, ())
        if "*" in regions or self.team[team_id]["region_code"] in regions:
            return "HOLIDAY"
        return "WEEKEND" if d.weekday() >= 5 else "WEEKDAY"

    def has_skill(self, emp: str, skill: str, d: date) -> bool:
        return any(f <= d and (to is None or d <= to) for f, to in self.holdings.get((emp, skill), ()))

    def requirements(self, team_id: str, shift: dict) -> tuple[int, dict]:
        rows = self.req.get((team_id, shift["template_id"], self.day_type(team_id, shift["shift_date"])), ())
        total, skills = 0, {}
        for r in rows:
            if r["effective_from"] <= shift["shift_date"] and (r["effective_to"] is None or shift["shift_date"] <= r["effective_to"]):
                if r["skill_id"] is None:
                    total = r["min_headcount"]
                else:
                    skills[r["skill_id"]] = r["min_headcount"]
        return total, skills

    def shift_hours(self, shift_id: str) -> float:
        s = self.shift[shift_id]
        return hours_between(s["start_datetime"], s["end_datetime"])

    def clock_pair(self, asg_id: str):
        ins = [e["event_ts"] for e in self.att.get(asg_id, ()) if e["event_type"] == "CLOCK_IN"]
        outs = [e["event_ts"] for e in self.att.get(asg_id, ()) if e["event_type"] == "CLOCK_OUT"]
        return (min(ins) if ins else None), (max(outs) if outs else None)


# ---------------------------------------------------------------------------- derived tables
DERIVED_COLUMNS = {
    "weekly_hours": ["employee_id", "iso_week", "employment_type", "contracted_weekly_hours", "max_weekly_hours",
                     "scheduled_shifts", "scheduled_hours", "overtime_scheduled_hours", "attended_shifts",
                     "actual_hours", "overtime_actual_hours", "missing_clock_outs", "cap_exceeded"],
    "coverage_status": ["team_id", "shift_id", "shift_date", "template_id", "day_type", "requirement",
                        "required", "planned", "final", "attended", "planned_gap", "final_gap", "attended_gap"],
    "coverage_gaps": ["team_id", "shift_id", "shift_date", "template_id", "day_type", "requirement", "required",
                      "planned", "final", "attended", "final_gap", "attended_gap", "gap_stage", "explanation"],
    "attendance_reconciliation": ["assignment_id", "employee_id", "team_id", "shift_id", "scheduled_start",
                                  "scheduled_end", "clock_in", "clock_out", "scheduled_hours", "actual_hours",
                                  "start_variance_min", "end_variance_min", "outcome", "stayed_late",
                                  "on_approved_leave"],
    "leave_balance": ["employee_id", "opening_balance_days", "approved_annual_days", "closing_balance_days",
                      "approved_sick_days", "approved_personal_days", "approved_unpaid_days", "requests_total",
                      "requests_rejected"],
    "fairness_by_team": ["team_id", "rota_members", "mean_utilisation", "gini_utilisation", "min_utilisation",
                         "max_utilisation", "night_shifts_mean", "night_shifts_std", "unsocial_shifts_mean",
                         "unsocial_shifts_std", "overtime_hours_total"],
}


def gini(values: list[float]) -> float:
    xs = sorted(v for v in values if v is not None)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * cum) / (n * sum(xs)) - (n + 1) / n


def _std(xs):
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def derive_all(ref: Reference) -> dict[str, list[dict]]:
    out = {}
    t = ref.t

    # ---- attendance reconciliation (one row per ACTIVE assignment)
    recon = []
    for a in sorted(ref.active, key=lambda a: a["assignment_id"]):
        s = ref.shift[a["shift_id"]]
        cin, cout = ref.clock_pair(a["assignment_id"])
        sched = ref.shift_hours(a["shift_id"])
        actual = round(hours_between(cin, cout), 2) if cin and cout else None
        sv = round((cin - s["start_datetime"]).total_seconds() / 60, 1) if cin else None
        ev = round((cout - s["end_datetime"]).total_seconds() / 60, 1) if cout else None
        if cin is None:
            outcome = "NO_SHOW"
        elif cout is None:
            outcome = "MISSING_CLOCK_OUT"
        elif sv > 5:
            outcome = "LATE"
        elif ev < -15:
            outcome = "EARLY_DEPARTURE"
        else:
            outcome = "ON_TIME"
        recon.append({"assignment_id": a["assignment_id"], "employee_id": a["employee_id"], "team_id": a["team_id"],
                      "shift_id": a["shift_id"], "scheduled_start": s["start_datetime"],
                      "scheduled_end": s["end_datetime"], "clock_in": cin, "clock_out": cout,
                      "scheduled_hours": sched, "actual_hours": actual, "start_variance_min": sv,
                      "end_variance_min": ev, "outcome": outcome, "stayed_late": bool(ev is not None and ev > 15),
                      "on_approved_leave": (a["employee_id"], s["shift_date"]) in ref.approved_leave})
    out["attendance_reconciliation"] = recon
    recon_by_asg = {r["assignment_id"]: r for r in recon}

    # ---- weekly hours and overtime
    wk = defaultdict(lambda: {"shifts": 0, "sched": 0.0, "att": 0, "actual": 0.0, "missing": 0})
    for a in ref.active:
        s = ref.shift[a["shift_id"]]
        w = wk[(a["employee_id"], s["iso_week"])]
        w["shifts"] += 1
        w["sched"] += ref.shift_hours(a["shift_id"])
        r = recon_by_asg[a["assignment_id"]]
        if r["clock_in"]:
            w["att"] += 1
        if r["actual_hours"] is not None:
            w["actual"] += r["actual_hours"]
        elif r["clock_in"]:
            w["missing"] += 1
    weekly = []
    for (emp, week), w in sorted(wk.items()):
        e = ref.emp[emp]
        c, cap = e["contracted_weekly_hours"], e["max_weekly_hours"]
        weekly.append({"employee_id": emp, "iso_week": week, "employment_type": e["employment_type"],
                       "contracted_weekly_hours": c, "max_weekly_hours": cap, "scheduled_shifts": w["shifts"],
                       "scheduled_hours": round(w["sched"], 2), "overtime_scheduled_hours": round(max(0.0, w["sched"] - c), 2),
                       "attended_shifts": w["att"], "actual_hours": round(w["actual"], 2),
                       "overtime_actual_hours": round(max(0.0, w["actual"] - c), 2), "missing_clock_outs": w["missing"],
                       "cap_exceeded": w["sched"] > cap + 1e-9})
    out["weekly_hours"] = weekly

    # ---- coverage status per team x shift x requirement
    people = defaultdict(lambda: {"planned": set(), "final": set(), "attended": set()})
    for a in t["shift_assignment"]:
        p = people[(a["team_id"], a["shift_id"])]
        if a["source"] == "PLANNED":
            p["planned"].add(a["employee_id"])
        if a["assignment_id"] in recon_by_asg:
            p["final"].add(a["employee_id"])
            if recon_by_asg[a["assignment_id"]]["clock_in"]:
                p["attended"].add(a["employee_id"])
    cov, gaps = [], []
    for team_id in sorted(ref.team):
        for s in sorted(t["shift"], key=lambda s: s["start_datetime"]):
            total, skills = ref.requirements(team_id, s)
            p = people[(team_id, s["shift_id"])]
            d = s["shift_date"]
            dtype = ref.day_type(team_id, d)
            reqs = [("TOTAL", total, lambda grp: len(grp))]
            for sk in sorted(skills):
                reqs.append((sk, skills[sk], lambda grp, sk=sk: sum(1 for x in grp if ref.has_skill(x, sk, d))))
            for name, need, count in reqs:
                if need <= 0:
                    continue
                pl, fi, at_ = count(p["planned"]), count(p["final"]), count(p["attended"])
                row = {"team_id": team_id, "shift_id": s["shift_id"], "shift_date": d,
                       "template_id": s["template_id"], "day_type": dtype, "requirement": name, "required": need,
                       "planned": pl, "final": fi, "attended": at_, "planned_gap": max(0, need - pl),
                       "final_gap": max(0, need - fi), "attended_gap": max(0, need - at_)}
                cov.append(row)
                if row["final_gap"] or row["attended_gap"]:
                    if row["final_gap"] and row["planned_gap"]:
                        stage, why = "PLANNING", "Not enough eligible staff when the schedule was published and not recovered by top-ups."
                    elif row["final_gap"]:
                        stage, why = "POST_PUBLICATION", "Covered at publication; lost to late leave, a reassignment or a swap and not refilled."
                    else:
                        stage, why = "ATTENDANCE", "Schedule met the requirement but people did not clock in (no-show / on leave)."
                    gaps.append({**{k: row[k] for k in DERIVED_COLUMNS["coverage_gaps"] if k in row},
                                 "gap_stage": stage, "explanation": why})
    out["coverage_status"] = cov
    out["coverage_gaps"] = gaps

    # ---- leave balance
    agg = defaultdict(lambda: defaultdict(float, {"n": 0, "rej": 0}))
    for lv in t["leave_request"]:
        g = agg[lv["employee_id"]]
        g["n"] += 1
        if lv["status"] == "APPROVED":
            g[lv["leave_type"]] += lv["days_requested"]
        if lv["status"] == "REJECTED":
            g["rej"] += 1
    bal = []
    for e in t["employee"]:
        if e["role"] == "MANAGER":
            continue
        g = agg[e["employee_id"]]
        o = e["annual_leave_opening_balance_days"]
        bal.append({"employee_id": e["employee_id"], "opening_balance_days": o, "approved_annual_days": g["ANNUAL"],
                    "closing_balance_days": round(o - g["ANNUAL"], 2), "approved_sick_days": g["SICK"],
                    "approved_personal_days": g["PERSONAL"], "approved_unpaid_days": g["UNPAID"],
                    "requests_total": g["n"], "requests_rejected": g["rej"]})
    out["leave_balance"] = bal

    # ---- fairness per team (home-team members, normalised by employed time in window)
    start, end = ref.window
    hours, nights, unsocial = defaultdict(float), defaultdict(int), defaultdict(int)
    night_tpl = {k for k, v in ref.tpl.items() if v["is_night"]}
    for a in ref.active:
        s = ref.shift[a["shift_id"]]
        hours[a["employee_id"]] += ref.shift_hours(a["shift_id"])
        if s["template_id"] in night_tpl:
            nights[a["employee_id"]] += 1
        if ref.day_type(ref.emp[a["employee_id"]]["team_id"], s["shift_date"]) != "WEEKDAY":
            unsocial[a["employee_id"]] += 1
    ot = defaultdict(float)
    for w in weekly:
        ot[w["employee_id"]] += w["overtime_scheduled_hours"]
    fair = []
    for team_id in sorted(ref.team):
        members = [e for e in t["employee"] if e["team_id"] == team_id and e["role"] != "MANAGER"]
        utils, nts, uns = [], [], []
        for e in members:
            f = max(e["hire_date"], start)
            to = min(e["termination_date"] or end, end)
            days = (to - f).days + 1
            if days < 14:
                continue  # too little time in the window to judge fairness
            utils.append(hours[e["employee_id"]] / (e["contracted_weekly_hours"] * days / 7))
            if e["night_shift_eligible"]:
                nts.append(nights[e["employee_id"]] * 28 / days)  # per 4 weeks
            uns.append(unsocial[e["employee_id"]] * 28 / days)
        fair.append({"team_id": team_id, "rota_members": len(members),
                     "mean_utilisation": round(sum(utils) / len(utils), 3) if utils else None,
                     "gini_utilisation": round(gini(utils), 4), "min_utilisation": round(min(utils), 3) if utils else None,
                     "max_utilisation": round(max(utils), 3) if utils else None,
                     "night_shifts_mean": round(sum(nts) / len(nts), 2) if nts else 0.0,
                     "night_shifts_std": round(_std(nts), 2), "unsocial_shifts_mean": round(sum(uns) / len(uns), 2) if uns else 0.0,
                     "unsocial_shifts_std": round(_std(uns), 2),
                     "overtime_hours_total": round(sum(ot[e["employee_id"]] for e in members), 2)})
    out["fairness_by_team"] = fair
    return out
