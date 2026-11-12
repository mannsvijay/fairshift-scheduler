"""Event-driven simulation of how the schedule evolves over time.

All changes are processed in timestamp order against one live state, so every
decision only sees what was known at that moment:

  PUBLISH         week W is planned at (Mon W - 7d) 12:00 using leave approved so far
  TOPUP           1-3 days later a manager may manually cover remaining gaps (own or sister team)
  LEAVE_APPROVED  late/sick leave on a published day releases the assignment and
                  attempts a call-in replacement (>= callin notice before shift start)
  LEAVE_CANCELLED frees the days again (no automatic re-scheduling)
  SWAP_*          teammate swaps: request -> manager decision by rule -> applied
  REASSIGN        manager moves a shift to another qualified teammate

Nothing is overwritten: a change ends the old assignment (RELEASED/SUPERSEDED)
and creates a new one, and every transition is logged as an event.
"""
from __future__ import annotations

import heapq
from datetime import timedelta

from .core import at, daterange, random_ts_between, rng_for, week_monday
from .engine import CAP_CONTRACT, CAP_MAX, ScheduleState

PRIORITY = {"LEAVE_APPROVED": 0, "LEAVE_CANCELLED": 1, "PUBLISH": 2, "TOPUP": 3, "SWAP_REQUEST": 4,
            "SWAP_WITHDRAW": 5, "SWAP_DECISION": 6, "REASSIGN": 7, "REPLACE": 8}


class Simulation:
    def __init__(self, ctx, leave_rows):
        self.ctx = ctx
        self.state = ScheduleState(ctx)
        self.leave_rows = leave_rows
        self.swaps: list[dict] = []
        self.swap_events: list[dict] = []
        self.heap = []
        self.seq = 0
        sc = ctx.scale
        self.as_of = at(sc.end_date, 23, 59, 59)
        self.teams = sorted(ctx.team)

    def push(self, ts, kind, payload):
        self.seq += 1
        heapq.heappush(self.heap, (ts, PRIORITY[kind], self.seq, kind, payload))

    def manager(self, team):
        return self.ctx.team[team]["manager_employee_id"]

    # ------------------------------------------------------------------ setup
    def schedule_events(self):
        ctx, sc, pol = self.ctx, self.ctx.scale, self.ctx.policy
        for r in self.leave_rows:
            if r["decision_reason"] in ("POLICY_COMPLIANT", "SICK_AUTO_APPROVED"):  # approved at some point
                self.push(r["decided_at"], "LEAVE_APPROVED", r)
                if r["cancelled_at"]:
                    self.push(r["cancelled_at"], "LEAVE_CANCELLED", r)
        rng = rng_for(ctx.seed, "topup-timing")
        mon = week_monday(sc.start_date)
        first_pub = None
        while mon <= sc.end_date:
            pub = at(mon - timedelta(days=pol.publication_lead_days), 12)
            first_pub = first_pub or pub
            self.push(pub, "PUBLISH", mon)
            for t in self.teams:
                self.push(pub + timedelta(minutes=rng.randint(20 * 60, 72 * 60)), "TOPUP", (t, mon))
            mon += timedelta(days=7)
        lo, hi = first_pub + timedelta(days=1), at(sc.end_date - timedelta(days=1), 20)
        rng = rng_for(ctx.seed, "swap-intents")
        for _ in range(sc.swap_requests):
            self.push(self._office_hours(rng, lo, hi), "SWAP_REQUEST", rng.random())
        rng = rng_for(ctx.seed, "reassign-intents")
        for _ in range(sc.manual_reassignments):
            self.push(self._office_hours(rng, lo, hi), "REASSIGN", rng.random())

    @staticmethod
    def _office_hours(rng, lo, hi):
        ts = random_ts_between(rng, lo, hi)
        return ts.replace(hour=rng.randint(7, 21))

    # ------------------------------------------------------------------ run
    def run(self):
        self.schedule_events()
        handlers = {"PUBLISH": self.on_publish, "TOPUP": self.on_topup, "LEAVE_APPROVED": self.on_leave_approved,
                    "LEAVE_CANCELLED": self.on_leave_cancelled, "SWAP_REQUEST": self.on_swap_request,
                    "SWAP_WITHDRAW": self.on_swap_withdraw, "SWAP_DECISION": self.on_swap_decision,
                    "REASSIGN": self.on_reassign, "REPLACE": self.on_replace}
        while self.heap:
            ts, _p, _s, kind, payload = heapq.heappop(self.heap)
            if ts > self.as_of:
                continue  # decisions after the as-of horizon stay pending
            handlers[kind](ts, payload)
        return self

    def window_dates(self, mon):
        sc = self.ctx.scale
        return [d for d in daterange(mon, mon + timedelta(days=6)) if sc.start_date <= d <= sc.end_date]

    # ------------------------------------------------------------------ handlers
    def on_publish(self, ts, mon):
        ctx, st = self.ctx, self.state
        for team in self.teams:
            for d in self.window_dates(mon):
                by_code = {s.code: s for s in ctx.shifts_by_date[d]}
                for code in ("C", "A", "B"):  # night first: fewest eligible people
                    st.fill(team, by_code[code], ts=ts, source="PLANNED", reason="SCHEDULE_PUBLISHED", actor=None,
                            pools=[ctx.rota[team]], rng_tag="plan")

    def on_topup(self, ts, payload):
        team, mon = payload
        ctx, st = self.ctx, self.state
        for d in self.window_dates(mon):
            for shift in ctx.shifts_by_date[d]:
                if shift.start - ts < timedelta(hours=12):
                    continue
                short_total, short_skills = st.shortfall(team, shift)
                if not short_total and not short_skills:
                    continue
                if rng_for(ctx.seed, "topup", team, shift.id).random() >= ctx.policy.topup_probability:
                    continue
                pools = [ctx.rota[team]] + [ctx.rota[s] for s in ctx.sisters[team]]
                st.fill(team, shift, ts=ts, source="MANUAL", reason="MANUAL_TOPUP", actor=self.manager(team),
                        pools=pools, rng_tag="topup")

    def on_leave_approved(self, ts, leave):
        ctx, st = self.ctx, self.state
        emp, key = leave["employee_id"], leave["leave_id"]
        dates = list(daterange(leave["start_date"], leave["end_date"]))
        for d in dates:
            st.leave_days[emp][d] = key
        for d in dates:
            k = st.emp_day[emp].get(d)
            if k is None:
                continue
            a, shift = st.asg[k], st.shift_of(k)
            team = a["team_id"]
            st.end(k, "RELEASED", ts, "LEAVE_APPROVED", leave["decided_by_employee_id"], leave=key)
            rts = ts + timedelta(minutes=rng_for(ctx.seed, "replacement", k).randint(10, 90))
            if rts < shift.start - timedelta(hours=ctx.policy.callin_min_notice_hours):
                self.push(rts, "REPLACE", k)
            # otherwise it is too late to call anyone in: becomes a reported coverage gap

    def on_replace(self, ts, released_key):
        """Manager calls in a replacement for an assignment released because of leave."""
        ctx, st = self.ctx, self.state
        a, shift = st.asg[released_key], st.shift_of(released_key)
        team, slot = a["team_id"], a["slot_skill_id"]
        if shift.start - ts < timedelta(hours=ctx.policy.callin_min_notice_hours):
            return
        skill_order, general_order = st.ranked_candidates(team, shift, [ctx.rota[team]], "replace",
                                                          exclude=[a["employee_id"]])
        for m in (skill_order if slot else general_order):
            if slot and not ctx.has_skill(m, slot, shift.date):
                continue
            st.assign(m, shift, team, slot, "REPLACEMENT", ts, self.manager(team), "LEAVE_REPLACEMENT",
                      replaces=released_key)
            return

    def on_leave_cancelled(self, ts, leave):
        days = self.state.leave_days[leave["employee_id"]]
        for d in [d for d, k in days.items() if k == leave["leave_id"]]:
            del days[d]

    # ---- swaps
    def _swap_event(self, swap_key, etype, ts, actor, reason):
        self.swap_events.append({"swap_event_id": f"SE:{len(self.swap_events) + 1}", "swap_id": swap_key,
                                 "event_type": etype, "event_ts": ts, "actor_employee_id": actor, "reason": reason})

    def _team_assignments(self, team, ts, d_from, d_to, home_only=True):
        ctx, st, sc = self.ctx, self.state, self.ctx.scale
        out = []
        for d in daterange(max(d_from, sc.start_date), min(d_to, sc.end_date)):
            for shift in ctx.shifts_by_date[d]:
                if shift.publish_ts > ts or shift.start - ts < timedelta(hours=1):
                    continue
                for k in st.active_keys(team, shift.id):
                    if not home_only or ctx.emp[st.asg[k]["employee_id"]].team == team:
                        out.append(k)
        return out

    def on_swap_request(self, ts, draw):
        ctx, st = self.ctx, self.state
        rng = rng_for(ctx.seed, "swap", ts.isoformat(), draw)
        # most requests target a shift 2-12 days out; a minority are last-minute (exercise LATE_REQUEST)
        lo_days, hi_days = (0, 1) if rng.random() < 0.08 else (2, 12)
        pool = []
        for attempt in range(20):
            team = rng.choice(self.teams)
            if attempt >= 10:  # near the end of the window fall back to whatever is still ahead
                lo_days, hi_days = 0, 3
            pool = self._team_assignments(team, ts, ts.date() + timedelta(days=lo_days), ts.date() + timedelta(days=hi_days))
            if pool:
                break
        if not pool:
            return
        a_key = rng.choice(pool)
        a = st.asg[a_key]
        requester, sa = a["employee_id"], st.shift_of(a_key)
        mates = [m for m in ctx.rota[team] if m != requester and ctx.emp[m].employed_on(sa.date)]

        def qualified(person, assignment, shift):
            slot = assignment["slot_skill_id"]
            return slot is None or ctx.has_skill(person, slot, shift.date)
        if not mates:
            return
        # Employees usually pre-arrange a swap with a colleague who can take it ("feasible" pick);
        # some ask regardless, which exercises the manager's rejection rules.
        prearranged = rng.random() < 0.7
        swap_type, target, b_key = "GIVEAWAY", None, None
        if rng.random() < 0.55:  # try an exchange
            options = []
            for k in self._team_assignments(team, ts, sa.date - timedelta(days=5), sa.date + timedelta(days=5)):
                b = st.asg[k]
                if b["employee_id"] == requester or b["employee_id"] not in mates:
                    continue
                if st.shift_of(k).date in st.emp_day[requester]:
                    continue
                if prearranged and (st.check(b["employee_id"], sa, CAP_MAX, ignore=(k,)) is not None
                                    or st.check(requester, st.shift_of(k), CAP_MAX, ignore=(a_key,)) is not None
                                    or not qualified(b["employee_id"], a, sa)
                                    or not qualified(requester, b, st.shift_of(k))):
                    continue
                options.append(k)
            if options:
                b_key = rng.choice(options)
                swap_type, target = "EXCHANGE", st.asg[b_key]["employee_id"]
        if target is None:
            feasible = [m for m in mates if st.check(m, sa, CAP_MAX) is None and qualified(m, a, sa)]
            target = rng.choice(feasible if prearranged and feasible else mates)
        key = f"S:{len(self.swaps) + 1}"
        self.swaps.append({"swap_id": key, "swap_type": swap_type, "team_id": team,
                           "requester_employee_id": requester, "requester_assignment_id": a_key,
                           "target_employee_id": target, "target_assignment_id": b_key, "requested_at": ts,
                           "status": "REQUESTED", "decided_at": None, "decided_by_employee_id": None,
                           "decision_reason": None, "applied_at": None})
        self._swap_event(key, "REQUESTED", ts, requester, None)
        lag = timedelta(minutes=rng.randint(60, 48 * 60))
        if rng.random() < ctx.policy.swap_withdraw_rate:
            self.push(ts + lag * rng.uniform(0.1, 0.9), "SWAP_WITHDRAW", key)
        else:
            self.push(ts + lag, "SWAP_DECISION", key)

    def _swap(self, key):
        return self.swaps[int(key.split(":")[1]) - 1]

    def on_swap_withdraw(self, ts, key):
        s = self._swap(key)
        ts = ts.replace(microsecond=0)
        s.update(status="WITHDRAWN", decided_at=ts, decision_reason="REQUESTER_WITHDREW")
        self._swap_event(key, "WITHDRAWN", ts, s["requester_employee_id"], "REQUESTER_WITHDREW")

    def evaluate_swap(self, s, ts):
        """Manager approval rule. Returns (approved, reason)."""
        ctx, st = self.ctx, self.state
        a_key, b_key = s["requester_assignment_id"], s["target_assignment_id"]
        a = st.asg[a_key]
        b = st.asg[b_key] if b_key else None
        if a["status"] != "ACTIVE" or (b and b["status"] != "ACTIVE"):
            return False, "ASSIGNMENT_CHANGED"
        sa = st.shift_of(a_key)
        sb = st.shift_of(b_key) if b_key else None
        # requests must be submitted >= swap_min_notice_hours before every shift involved,
        # and a decision after a shift has started can no longer apply
        notice = timedelta(hours=ctx.policy.swap_min_notice_hours)
        req = s["requested_at"]
        if any(sh.start - req < notice or sh.start <= ts for sh in (sa, sb) if sh):
            return False, "LATE_REQUEST"
        R, T = s["requester_employee_id"], s["target_employee_id"]
        reason = st.check(T, sa, CAP_MAX, ignore=(b_key,) if b_key else ())
        if reason is None and sb:
            reason = st.check(R, sb, CAP_MAX, ignore=(a_key,))
        if reason:
            return False, reason
        if a["slot_skill_id"] and not ctx.has_skill(T, a["slot_skill_id"], sa.date):
            return False, "SKILL_MISMATCH"
        if b and b["slot_skill_id"] and not ctx.has_skill(R, b["slot_skill_id"], sb.date):
            return False, "SKILL_MISMATCH"
        if not st.coverage_preserved(a["team_id"], sa, R, T):
            return False, "SKILL_COVERAGE"
        if sb and not st.coverage_preserved(b["team_id"], sb, T, R):
            return False, "SKILL_COVERAGE"
        return True, "CONSTRAINTS_SATISFIED"

    def apply_swap(self, s, ts, actor):
        st = self.state
        a_key, b_key = s["requester_assignment_id"], s["target_assignment_id"]
        moves = [(a_key, s["target_employee_id"])] + ([(b_key, s["requester_employee_id"])] if b_key else [])
        olds = [(k, st.asg[k], st.shift_of(k)) for k, _ in moves]
        for k, _a, _sh in olds:  # end both first so an exchange does not collide with itself
            st.end(k, "SUPERSEDED", ts, "SWAP_APPLIED", actor, swap=s["swap_id"])
        for (k, a, sh), (_k, new_emp) in zip(olds, moves):
            nk = st.assign(new_emp, sh, a["team_id"], a["slot_skill_id"], "SWAP", ts, actor, "SWAP_APPLIED",
                           swap=s["swap_id"], replaces=k)
            st.asg_events[-1]["related_assignment_id"] = k
            # link the supersede event to its successor
            for ev in reversed(st.asg_events):
                if ev["assignment_id"] == k and ev["event_type"] == "SUPERSEDED":
                    ev["related_assignment_id"] = nk
                    break

    def on_swap_decision(self, ts, key):
        s = self._swap(key)
        if s["status"] != "REQUESTED":
            return
        ts = ts.replace(microsecond=0)
        manager = self.manager(s["team_id"])
        ok, reason = self.evaluate_swap(s, ts)
        s.update(decided_at=ts, decided_by_employee_id=manager, decision_reason=reason)
        if not ok:
            s["status"] = "REJECTED"
            self._swap_event(key, "REJECTED", ts, manager, reason)
            return
        self._swap_event(key, "APPROVED", ts, manager, reason)
        applied = ts  # applied atomically with the approval so no other change can interleave
        self.apply_swap(s, applied, manager)
        s.update(status="APPLIED", applied_at=applied)
        self._swap_event(key, "APPLIED", applied, manager, reason)

    # ---- manual reassignment by a manager (legitimate, constraint-checked)
    def on_reassign(self, ts, draw):
        ctx, st = self.ctx, self.state
        rng = rng_for(ctx.seed, "reassign", ts.isoformat(), draw)
        team = rng.choice(self.teams)
        pool = self._team_assignments(team, ts, ts.date() + timedelta(days=1), ts.date() + timedelta(days=7))
        if not pool:
            return
        a_key = rng.choice(pool)
        a, shift = st.asg[a_key], st.shift_of(a_key)
        old = a["employee_id"]
        skill_order, general_order = st.ranked_candidates(team, shift, [ctx.rota[team]], "reassign", exclude=[old])
        for m in (skill_order if a["slot_skill_id"] else general_order):
            if a["slot_skill_id"] and not ctx.has_skill(m, a["slot_skill_id"], shift.date):
                continue
            if not st.coverage_preserved(team, shift, old, m):
                continue
            actor = self.manager(team)
            st.end(a_key, "SUPERSEDED", ts, "MANUAL_REASSIGNMENT", actor)
            nk = st.assign(m, shift, team, a["slot_skill_id"], "MANUAL", ts, actor, "MANUAL_REASSIGNMENT",
                           replaces=a_key)
            for ev in reversed(st.asg_events):
                if ev["assignment_id"] == a_key and ev["event_type"] == "SUPERSEDED":
                    ev["related_assignment_id"] = nk
                    break
            return
