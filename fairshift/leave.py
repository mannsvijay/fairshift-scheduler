"""Leave requests: generation and decisions.

Outcomes are *not* drawn at random. Requests are generated with realistic
timing, then decided by the documented rules below, replayed in decision-time
order so that balances and team concurrency reflect earlier decisions:

  1. Submitted before the leave starts, but the manager decision would land
     on/after the first day of leave                             -> EXPIRED (MANAGER_NO_RESPONSE)
  2. Overlaps the employee's own approved leave                -> REJECTED (DUPLICATE_OVERLAP)
  3. SICK                                                        -> APPROVED automatically
  4. Notice < min_leave_notice_days                              -> REJECTED (INSUFFICIENT_NOTICE)
  5. ANNUAL days > remaining balance                             -> REJECTED (INSUFFICIENT_BALANCE)
  6. PERSONAL beyond allowance / UNPAID beyond per-request max   -> REJECTED (ALLOWANCE_EXCEEDED)
  7. Any day already at the team's planned-leave concurrency cap -> REJECTED (TEAM_CAPACITY)
  8. Otherwise                                                   -> APPROVED (POLICY_COMPLIANT)
Approved ANNUAL/PERSONAL leave may later be CANCELLED by the employee, which
restores balance and concurrency.
"""
from __future__ import annotations

import heapq
import math
from datetime import date, datetime, timedelta

from .core import at, daterange, rng_for

LEAVE_TYPE_WEIGHTS = [("ANNUAL", 0.55), ("SICK", 0.27), ("PERSONAL", 0.12), ("UNPAID", 0.06)]


def leave_days(ctx, emp_id: str, start: date, end: date) -> float:
    """Chargeable days: calendar days excluding holidays that apply to the employee's region."""
    return float(sum(1 for d in daterange(start, end) if not ctx.is_holiday_for_emp(emp_id, d)))


def _duration(rng, ltype: str) -> int:
    if ltype == "ANNUAL":
        return rng.choices([1, 2, 3, 4, 5, 7, 10], weights=[22, 22, 18, 12, 14, 8, 4])[0]
    if ltype == "SICK":
        return rng.choices([1, 2, 3, 5], weights=[55, 25, 14, 6])[0]
    if ltype == "PERSONAL":
        return rng.choices([1, 2, 3], weights=[60, 30, 10])[0]
    return rng.choices([2, 5, 8, 12], weights=[30, 35, 25, 10])[0]


def generate_leave(ctx, count: int):
    """Return (leave rows, leave event rows). Keys are provisional ('L:n'); final IDs come later."""
    sc, pol = ctx.scale, ctx.policy
    rng = rng_for(ctx.seed, "leave")
    rota = [e for e in sorted(ctx.emp) if ctx.emp[e].rota]
    days = list(daterange(sc.start_date, sc.end_date))
    # demand is higher around holidays (long weekends) and on Mondays/Fridays
    weights = []
    for d in days:
        w = 1.0
        if any(abs((d - h).days) <= 2 for hs in ctx.holiday_dates.values() for h in hs):
            w *= 2.2
        if d.weekday() in (0, 4):
            w *= 1.3
        weights.append(w)

    requests = []
    while len(requests) < count:
        emp_id = rng.choice(rota)
        e = ctx.emp[emp_id]
        ltype = rng.choices([t for t, _ in LEAVE_TYPE_WEIGHTS], weights=[w for _, w in LEAVE_TYPE_WEIGHTS])[0]
        start = rng.choices(days, weights=weights)[0]
        end = min(start + timedelta(days=_duration(rng, ltype) - 1), sc.end_date)
        if not (e.employed_on(start) and e.employed_on(end)):
            continue
        if ltype == "SICK":
            if rng.random() < 0.75:  # calls in early on the day
                sub = at(start, rng.randint(4, 7), rng.randint(0, 59), rng.randint(0, 59))
            else:                    # evening before
                sub = at(start - timedelta(days=1), rng.randint(18, 21), rng.randint(0, 59), rng.randint(0, 59))
            lag = timedelta(minutes=rng.randint(2, 20))  # automatic decision
        else:
            if rng.random() < 0.05:
                lead = rng.randint(0, 2)
            elif ltype == "UNPAID":
                lead = rng.randint(7, 45)
            elif ltype == "PERSONAL":
                lead = rng.randint(3, 14)
            else:
                lead = int(rng.triangular(3, 60, 12))
            sub = at(start - timedelta(days=lead), rng.randint(8, 18), rng.randint(0, 59), rng.randint(0, 59))
            lag = timedelta(hours=rng.uniform(1, 72) if rng.random() < 0.9 else rng.uniform(72, 200))
        lag = timedelta(seconds=int(lag.total_seconds()))
        requests.append({"emp": emp_id, "type": ltype, "start": start, "end": end, "submitted_at": sub,
                         "decide_at": sub + lag, "cancel_draw": rng.random(), "cancel_frac": rng.random()})

    # provisional keys in submission order
    requests.sort(key=lambda r: (r["submitted_at"], r["emp"], r["start"]))
    rows, events = [], []
    for i, r in enumerate(requests, start=1):
        r["key"] = f"L:{i}"
        rows.append({"leave_id": r["key"], "employee_id": r["emp"], "leave_type": r["type"],
                     "start_date": r["start"], "end_date": r["end"],
                     "days_requested": leave_days(ctx, r["emp"], r["start"], r["end"]),
                     "submitted_at": r["submitted_at"], "status": "SUBMITTED", "decided_at": None,
                     "decided_by_employee_id": None, "decision_channel": None, "decision_reason": None,
                     "cancelled_at": None})
        events.append(_event(events, r["key"], "SUBMITTED", r["submitted_at"], r["emp"], None))
    row_by_key = {r["leave_id"]: r for r in rows}

    # ---- replay decisions and cancellations in time order
    opening = {e["employee_id"]: e["annual_leave_opening_balance_days"] for e in ctx.tables["employee"]}
    balance = {e: opening[e] for e in rota}
    personal_used = {e: 0.0 for e in rota}
    approved_by_emp: dict[str, list] = {}
    team_load: dict[tuple, int] = {}  # (team, date) -> planned leaves approved
    cap = {t: max(1, math.floor(len(m) * pol.team_leave_concurrency_ratio)) for t, m in ctx.rota.items()}

    heap = []
    for r in requests:
        heapq.heappush(heap, (r["decide_at"], 0, r["key"]))
    req_by_key = {r["key"]: r for r in requests}

    while heap:
        ts, kind, key = heapq.heappop(heap)
        r, row = req_by_key[key], row_by_key[key]
        emp_id, team = r["emp"], ctx.emp[r["emp"]].team
        dates = list(daterange(r["start"], r["end"]))
        if kind == 1:  # cancellation
            row.update(status="CANCELLED", cancelled_at=ts)
            events.append(_event(events, key, "CANCELLED", ts, emp_id, "EMPLOYEE_CANCELLED"))
            approved_by_emp[emp_id].remove(key)
            if r["type"] == "ANNUAL":
                balance[emp_id] += row["days_requested"]
            if r["type"] == "PERSONAL":
                personal_used[emp_id] -= row["days_requested"]
            for d in dates:
                team_load[(team, d)] -= 1
            continue

        manager = ctx.team[team]["manager_employee_id"]
        start_ts = at(r["start"])
        reason, status, channel, actor = None, None, "MANAGER", manager
        own = [req_by_key[k] for k in approved_by_emp.get(emp_id, [])]
        overlaps = any(o["start"] <= r["end"] and r["start"] <= o["end"] for o in own)
        if r["type"] != "SICK" and ts >= start_ts and r["submitted_at"] < start_ts:
            status, reason, channel, actor, ts = "EXPIRED", "MANAGER_NO_RESPONSE", "AUTO", None, start_ts
        elif overlaps:
            status, reason = "REJECTED", "DUPLICATE_OVERLAP"
            if r["type"] == "SICK":
                channel, actor = "AUTO", None
        elif r["type"] == "SICK":
            status, reason, channel, actor = "APPROVED", "SICK_AUTO_APPROVED", "AUTO", None
        elif (r["start"] - r["submitted_at"].date()).days < pol.min_leave_notice_days:
            status, reason = "REJECTED", "INSUFFICIENT_NOTICE"
        elif r["type"] == "ANNUAL" and row["days_requested"] > balance[emp_id]:
            status, reason = "REJECTED", "INSUFFICIENT_BALANCE"
        elif r["type"] == "PERSONAL" and personal_used[emp_id] + row["days_requested"] > pol.max_personal_days:
            status, reason = "REJECTED", "ALLOWANCE_EXCEEDED"
        elif r["type"] == "UNPAID" and row["days_requested"] > pol.max_unpaid_days:
            status, reason = "REJECTED", "ALLOWANCE_EXCEEDED"
        elif any(team_load.get((team, d), 0) >= cap[team] for d in dates):
            status, reason = "REJECTED", "TEAM_CAPACITY"
        else:
            status, reason = "APPROVED", "POLICY_COMPLIANT"

        row.update(status=status, decided_at=ts, decided_by_employee_id=actor, decision_channel=channel,
                   decision_reason=reason)
        events.append(_event(events, key, status, ts, actor, reason))
        if status == "APPROVED":
            approved_by_emp.setdefault(emp_id, []).append(key)
            for d in dates:
                team_load[(team, d)] = team_load.get((team, d), 0) + 1
            if r["type"] == "ANNUAL":
                balance[emp_id] -= row["days_requested"]
            if r["type"] == "PERSONAL":
                personal_used[emp_id] += row["days_requested"]
            if r["type"] in ("ANNUAL", "PERSONAL") and r["cancel_draw"] < pol.leave_cancel_rate:
                window = (start_ts - ts).total_seconds()
                if window > 3600:
                    cts = ts + timedelta(seconds=int(window * (0.1 + 0.85 * r["cancel_frac"])))
                    heapq.heappush(heap, (cts, 1, key))
    return rows, events


def _event(events: list, leave_key: str, etype: str, ts: datetime, actor, reason) -> dict:
    return {"leave_event_id": f"LE:{len(events) + 1}", "leave_id": leave_key, "event_type": etype,
            "event_ts": ts, "actor_employee_id": actor, "reason": reason}
