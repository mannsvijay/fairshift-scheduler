"""Scheduling engine: live schedule state, hard-constraint checks and shift filling.

Hard constraints (never violated by the engine; the detector re-checks them independently):
  * employed on the shift date, on the rota (not a manager), not on approved leave
  * night shifts only for night-eligible employees
  * at most one shift per calendar day (no double booking)
  * >= min_rest_hours between consecutive shifts
  * <= max_consecutive_days working days in a row
  * weekly scheduled hours <= contracted hours (regular pass) or <= max_weekly_hours (overtime pass)
  * a skill slot is only filled by someone holding a *valid* (unexpired) holding of that skill

Soft objective (fairness): among eligible candidates, prefer the person with the
lowest load score — weekly utilisation first, then cumulative hours, then
night / weekend / holiday burden. Overtime is only used when nobody can cover
within contracted hours.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from .core import rng_for

CAP_CONTRACT, CAP_MAX, CAP_NONE = "contract", "max", None


class ScheduleState:
    def __init__(self, ctx):
        self.ctx = ctx
        self.rest = timedelta(hours=ctx.policy.min_rest_hours)
        self.asg: dict[str, dict] = {}
        self.asg_events: list[dict] = []
        self.emp_day = defaultdict(dict)        # emp -> date -> active assignment key
        self.team_shift = defaultdict(dict)     # (team, shift id) -> {key: None} (ordered set)
        self.week_hours = defaultdict(float)    # (emp, iso week) -> scheduled hours
        self.leave_days = defaultdict(dict)     # emp -> date -> approved leave key
        self.hours_total = defaultdict(float)
        self.nights = defaultdict(int)
        self.unsocial = defaultdict(int)        # weekend or holiday shifts
        self.holidays = defaultdict(int)

    # ------------------------------------------------------------------ lookups
    def shift_of(self, key):
        return self.ctx.shifts[self.asg[key]["shift_id"]]

    def active_keys(self, team, shift_id):
        return list(self.team_shift.get((team, shift_id), {}))

    def check(self, emp_id, shift, cap=CAP_CONTRACT, ignore=()):
        """Return None if emp_id may take `shift`, else the violated rule code."""
        ctx = self.ctx
        e = ctx.emp[emp_id]
        d = shift.date
        if not e.rota:
            return "NOT_ROTA"
        if not e.employed_on(d):
            return "NOT_EMPLOYED"
        if d in self.leave_days[emp_id]:
            return "ON_LEAVE"
        if shift.is_night and not e.night_ok:
            return "NIGHT_INELIGIBLE"
        days = self.emp_day[emp_id]
        k = days.get(d)
        if k is not None and k not in ignore:
            return "DOUBLE_BOOKING"
        one = timedelta(days=1)
        prev = days.get(d - one)
        if prev is not None and prev not in ignore and self.shift_of(prev).end + self.rest > shift.start:
            return "REST_RULE"
        nxt = days.get(d + one)
        if nxt is not None and nxt not in ignore and shift.end + self.rest > self.shift_of(nxt).start:
            return "REST_RULE"
        run, x = 1, d - one
        while x in days and days[x] not in ignore:
            run, x = run + 1, x - one
        x = d + one
        while x in days and days[x] not in ignore:
            run, x = run + 1, x + one
        if run > ctx.policy.max_consecutive_days:
            return "CONSECUTIVE_DAYS"
        if cap is not None:
            hours = self.week_hours[(emp_id, shift.week)] + shift.hours
            for ik in ignore:
                a = self.asg.get(ik)
                if a and a["employee_id"] == emp_id and self.shift_of(ik).week == shift.week:
                    hours -= self.shift_of(ik).hours
            limit = e.contract if cap == CAP_CONTRACT else e.max_hours
            if hours > limit + 1e-9:
                return "WEEKLY_HOURS_CAP"
        return None

    def coverage(self, team, shift, swap_out=None, swap_in=None):
        """(headcount, {skill: holders}) for a team on a shift, optionally simulating one person swap."""
        people = [self.asg[k]["employee_id"] for k in self.active_keys(team, shift.id)]
        if swap_out is not None:
            people = [swap_in if p == swap_out else p for p in people]
        _total, skills = self.ctx.requirements(team, shift)
        return len(people), {s: sum(1 for p in people if self.ctx.has_skill(p, s, shift.date)) for s in skills}

    def shortfall(self, team, shift):
        total, skills = self.ctx.requirements(team, shift)
        n, held = self.coverage(team, shift)
        return max(0, total - n), {s: max(0, need - held.get(s, 0)) for s, need in skills.items() if held.get(s, 0) < need}

    def coverage_preserved(self, team, shift, out_emp, in_emp) -> bool:
        """A person change must not push any skill requirement that is currently met below its minimum."""
        _t, skills = self.ctx.requirements(team, shift)
        _n, before = self.coverage(team, shift)
        _n, after = self.coverage(team, shift, out_emp, in_emp)
        return all(not (before[s] >= need and after[s] < need) for s, need in skills.items())

    # ------------------------------------------------------------------ mutations
    def _event(self, key, etype, ts, reason, actor, leave=None, swap=None, related=None):
        self.asg_events.append({"assignment_event_id": f"AE:{len(self.asg_events) + 1}", "assignment_id": key,
                                "event_type": etype, "event_ts": ts, "reason": reason,
                                "actor_employee_id": actor, "related_leave_id": leave,
                                "related_swap_id": swap, "related_assignment_id": related})

    def assign(self, emp_id, shift, team, slot, source, ts, actor, reason, swap=None, replaces=None,
               index_emp=True):
        key = f"A:{len(self.asg) + 1}"
        self.asg[key] = {"assignment_id": key, "shift_id": shift.id, "employee_id": emp_id, "team_id": team,
                         "slot_skill_id": slot, "source": source, "status": "ACTIVE", "created_at": ts,
                         "created_by_employee_id": actor, "swap_id": swap, "replaces_assignment_id": replaces}
        self._event(key, "CREATED", ts, reason, actor, swap=swap, related=replaces)
        if index_emp:
            self.emp_day[emp_id][shift.date] = key
        self.team_shift[(team, shift.id)][key] = None
        self._account(emp_id, shift, +1)
        return key

    def end(self, key, etype, ts, reason, actor, leave=None, swap=None, related=None):
        a = self.asg[key]
        assert a["status"] == "ACTIVE", (key, a["status"])
        a["status"] = "RELEASED" if etype == "RELEASED" else "SUPERSEDED"
        self._event(key, etype, ts, reason, actor, leave=leave, swap=swap, related=related)
        shift = self.shift_of(key)
        if self.emp_day[a["employee_id"]].get(shift.date) == key:
            del self.emp_day[a["employee_id"]][shift.date]
        self.team_shift[(a["team_id"], shift.id)].pop(key, None)
        self._account(a["employee_id"], shift, -1)

    def _account(self, emp_id, shift, sign):
        self.week_hours[(emp_id, shift.week)] += sign * shift.hours
        self.hours_total[emp_id] += sign * shift.hours
        if shift.is_night:
            self.nights[emp_id] += sign
        dtype = self.ctx.day_type(self.ctx.emp[emp_id].team, shift.date)
        if dtype != "WEEKDAY":
            self.unsocial[emp_id] += sign
        if dtype == "HOLIDAY":
            self.holidays[emp_id] += sign

    # ------------------------------------------------------------------ fairness
    def load_score(self, emp_id, shift, dtype, tiebreak, general=False):
        e = self.ctx.emp[emp_id]
        s = 2.0 * self.week_hours[(emp_id, shift.week)] / e.contract + self.hours_total[emp_id] / e.contract
        if shift.is_night:
            s += 0.35 * self.nights[emp_id]
        if dtype != "WEEKDAY":
            s += 0.35 * self.unsocial[emp_id]
        if dtype == "HOLIDAY":
            s += 0.5 * self.holidays[emp_id]
        if general:  # keep scarce-skill holders available for skill slots
            s += 0.15 * self.ctx.scarce_count.get(emp_id, 0)
        return s + 0.05 * tiebreak

    def ranked_candidates(self, team, shift, pools, rng_tag, exclude=()):
        """Eligible candidates in preference order.

        pools: list of member lists, in priority order (e.g. own team, then sister teams).
        Within each pool, people who fit within contracted hours come before overtime candidates.
        Returns (skill_order, general_order) lists of emp ids.
        """
        dtype = self.ctx.day_type(team, shift.date)
        rng = rng_for(self.ctx.seed, "tiebreak", rng_tag, team, shift.id)
        skill_order, general_order = [], []
        seen = set(exclude)
        for pool in pools:
            tb = {m: rng.random() for m in pool}
            for cap in (CAP_CONTRACT, CAP_MAX):
                tier = [m for m in pool if m not in seen and self.check(m, shift, cap) is None]
                seen.update(tier)
                skill_order += sorted(tier, key=lambda m: (self.load_score(m, shift, dtype, tb[m]), m))
                general_order += sorted(tier, key=lambda m: (self.load_score(m, shift, dtype, tb[m], True), m))
        return skill_order, general_order

    def fill(self, team, shift, *, ts, source, reason, actor, pools, rng_tag):
        """Fill skill minimums (scarcest skill first), then total headcount. Returns keys created."""
        ctx = self.ctx
        total, skills = ctx.requirements(team, shift)
        current = [self.asg[k]["employee_id"] for k in self.active_keys(team, shift.id)]
        skill_order, general_order = self.ranked_candidates(team, shift, pools, rng_tag, exclude=current)
        on_shift = list(current)
        created = []
        scarcity = ctx.skill_scarcity.get(team, {})
        for sid, need in sorted(skills.items(), key=lambda kv: (scarcity.get(kv[0], 0), kv[0])):
            have = sum(1 for p in on_shift if ctx.has_skill(p, sid, shift.date))
            for m in skill_order:
                if have >= need:
                    break
                if m in on_shift or not ctx.has_skill(m, sid, shift.date):
                    continue
                created.append(self.assign(m, shift, team, sid, source, ts, actor, reason))
                on_shift.append(m)
                have += 1
        for m in general_order:
            if len(on_shift) >= total:
                break
            if m in on_shift:
                continue
            created.append(self.assign(m, shift, team, None, source, ts, actor, reason))
            on_shift.append(m)
        return created
