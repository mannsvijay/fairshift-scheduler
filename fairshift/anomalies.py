"""Injection of labelled edge cases into an otherwise valid baseline.

Five issue types from the brief. Each injection:
  * is a plausible *event* (a manual edit, a self-service change, a late approval),
    recorded through the normal append-only mechanisms — never an in-place edit;
  * violates exactly one rule (candidates are chosen so no other detector fires);
  * touches a fresh employee (and team-shift), so injections never interact;
  * is recorded in ground truth only. Nothing in the input tables marks it,
    and final IDs are assigned chronologically afterwards, so the ID sequence
    does not reveal injected rows either.
"""
from __future__ import annotations

import math
from datetime import timedelta

from .core import at, daterange, random_ts_between, rng_for
from .engine import CAP_MAX, CAP_NONE
from .leave import leave_days


class Injector:
    def __init__(self, sim, leave_rows, leave_events):
        self.sim = sim
        self.ctx = sim.ctx
        self.st = sim.state
        self.leave_rows = leave_rows
        self.leave_events = leave_events
        self.tainted_emps: set[str] = set()
        self.tainted_team_shifts: set[tuple] = set()
        self.truth: list[dict] = []
        self.as_of = sim.as_of

    # ------------------------------------------------------------------ helpers
    def _rng(self, tag):
        return rng_for(self.ctx.seed, "anomaly", tag)

    def _active_keys(self, rng, sources=("PLANNED",)):
        keys = [k for k, a in self.st.asg.items() if a["status"] == "ACTIVE" and a["source"] in sources]
        rng.shuffle(keys)
        return keys

    def _edit_time(self, rng, shift, not_before=None):
        lo = shift.publish_ts + timedelta(hours=2)
        if not_before is not None:
            lo = max(lo, not_before + timedelta(minutes=5))
        hi = min(shift.start - timedelta(hours=26), self.as_of)
        return None if hi <= lo else random_ts_between(rng, lo, hi)

    def _taint(self, *emps, team_shift=None):
        self.tainted_emps.update(emps)
        if team_shift:
            self.tainted_team_shifts.add(team_shift)

    def _label(self, issue, record_type, record_id, related, emp, team, shift, week, rule, desc):
        self.truth.append({"issue_type": issue, "record_type": record_type, "record_id": record_id,
                           "related_record_ids": list(related), "employee_id": emp, "team_id": team,
                           "shift_id": shift.id if shift else None,
                           "business_date": shift.date if shift else None,
                           "iso_week": week or (shift.week if shift else None),
                           "expected_rule": rule, "description": desc})

    def _manager(self, team):
        return self.ctx.team[team]["manager_employee_id"]

    # ------------------------------------------------------------------ issue types
    def double_booked(self, n):
        rng, ctx, st = self._rng("double"), self.ctx, self.st
        done = 0
        for k in self._active_keys(rng):
            if done >= n:
                break
            a = st.asg[k]
            emp, sh = a["employee_id"], st.shift_of(k)
            if emp in self.tainted_emps or st.week_hours[(emp, sh.week)] + sh.hours > ctx.emp[emp].max_hours:
                continue
            others = ctx.sisters[a["team_id"]] or [t for t in sorted(ctx.team) if t != a["team_id"]]
            team2 = rng.choice(others)
            if (team2, sh.id) in self.tainted_team_shifts:
                continue
            ts = self._edit_time(rng, sh, not_before=a["created_at"])
            if ts is None:
                continue
            nk = st.assign(emp, sh, team2, None, "MANUAL", ts, self._manager(team2), "MANUAL_TOPUP", index_emp=False)
            self._taint(emp, team_shift=(team2, sh.id))
            self._label("DOUBLE_BOOKED", "shift_assignment", nk, [k], emp, team2, sh, None,
                        "Two ACTIVE assignments of one employee overlap in time",
                        f"Borrowed by {team2} for a shift the employee already works for {a['team_id']}.")
            done += 1
        return done

    def leave_overlaps_assignment(self, n):
        rng, ctx, st, pol = self._rng("leave"), self.ctx, self.st, self.ctx.policy
        cover = {}
        personal = {}
        team_load = {}
        for r in self.leave_rows:
            for d in daterange(r["start_date"], r["end_date"]):
                cover.setdefault((r["employee_id"], d), []).append(r)
            if r["status"] == "APPROVED":
                team = ctx.emp[r["employee_id"]].team
                for d in daterange(r["start_date"], r["end_date"]):
                    team_load[(team, d)] = team_load.get((team, d), 0) + 1
                if r["leave_type"] == "PERSONAL":
                    personal[r["employee_id"]] = personal.get(r["employee_id"], 0) + r["days_requested"]
        cap = {t: max(1, math.floor(len(m) * pol.team_leave_concurrency_ratio)) for t, m in ctx.rota.items()}
        done = 0
        for k in self._active_keys(rng):
            if done >= n:
                break
            a = st.asg[k]
            emp, sh = a["employee_id"], st.shift_of(k)
            team, d = ctx.emp[emp].team, sh.date
            if emp in self.tainted_emps or (emp, d) in cover or ctx.is_holiday_for_emp(emp, d):
                continue
            if personal.get(emp, 0) + 1 > pol.max_personal_days or team_load.get((team, d), 0) >= cap[team]:
                continue
            sub = at(d - timedelta(days=rng.randint(5, 12)), rng.randint(9, 17), rng.randint(0, 59), rng.randint(0, 59))
            dec = sub + timedelta(minutes=rng.randint(4 * 60, 48 * 60))
            if dec >= at(d) or dec > self.as_of:
                continue
            key = f"L:{len(self.leave_rows) + 1}"
            mgr = self._manager(team)
            self.leave_rows.append({"leave_id": key, "employee_id": emp, "leave_type": "PERSONAL", "start_date": d,
                                    "end_date": d, "days_requested": leave_days(ctx, emp, d, d), "submitted_at": sub,
                                    "status": "APPROVED", "decided_at": dec, "decided_by_employee_id": mgr,
                                    "decision_channel": "MANAGER", "decision_reason": "POLICY_COMPLIANT",
                                    "cancelled_at": None})
            for et, ts, actor, reason in (("SUBMITTED", sub, emp, None), ("APPROVED", dec, mgr, "POLICY_COMPLIANT")):
                self.leave_events.append({"leave_event_id": f"LE:{len(self.leave_events) + 1}", "leave_id": key,
                                          "event_type": et, "event_ts": ts, "actor_employee_id": actor, "reason": reason})
            self._taint(emp)
            self._label("LEAVE_OVERLAPS_ASSIGNMENT", "leave_request", key, [k], emp, a["team_id"], sh, None,
                        "APPROVED leave covers the date of an ACTIVE assignment",
                        "Leave approved but the published assignment was never released.")
            done += 1
        return done

    def required_skill_absent(self, n):
        rng, ctx, st = self._rng("skill"), self.ctx, self.st
        done = 0
        for k in self._active_keys(rng, sources=("PLANNED", "REPLACEMENT")):
            if done >= n:
                break
            a = st.asg[k]
            skill, team, sh = a["slot_skill_id"], a["team_id"], st.shift_of(k)
            if not skill or a["employee_id"] in self.tainted_emps or (team, sh.id) in self.tainted_team_shifts:
                continue
            _t, needs = ctx.requirements(team, sh)
            _n, held = st.coverage(team, sh)
            if held.get(skill, 0) != needs.get(skill):  # only where the requirement is exactly met
                continue
            on_shift = {st.asg[x]["employee_id"] for x in st.active_keys(team, sh.id)}
            pool = [m for m in ctx.rota[team] if m not in on_shift and m not in self.tainted_emps
                    and not ctx.has_skill(m, skill, sh.date) and st.check(m, sh, CAP_MAX) is None]
            if not pool:
                continue
            # boundary case: prefer someone whose certification for this skill has just expired
            expired = [m for m in pool if any(t is not None and t < sh.date
                                              for _f, t in ctx.holdings.get(m, {}).get(skill, []))]
            emp = rng.choice(expired) if expired and rng.random() < 0.6 else rng.choice(pool)
            ts = self._edit_time(rng, sh, not_before=a["created_at"])
            if ts is None:
                continue
            mgr = self._manager(team)
            st.end(k, "SUPERSEDED", ts, "MANUAL_REASSIGNMENT", mgr)
            nk = st.assign(emp, sh, team, skill, "MANUAL", ts, mgr, "MANUAL_REASSIGNMENT", replaces=k)
            st.asg_events[-2]["related_assignment_id"] = nk
            self._taint(emp, a["employee_id"], team_shift=(team, sh.id))
            note = "expired certification" if emp in expired else "never held the skill"
            self._label("REQUIRED_SKILL_ABSENT", "shift_assignment", nk, [k], emp, team, sh, None,
                        "Skill slot filled by an employee without a valid holding of that skill",
                        f"Manual reassignment put an employee into a {skill} slot ({note}); the shift now lacks it.")
            done += 1
        return done

    def overtime_cap_exceeded(self, n):
        rng, ctx, st, sc = self._rng("overtime"), self.ctx, self.st, self.ctx.scale
        weeks = sorted({sh.week for sh in ctx.shifts.values()
                        if all(sc.start_date <= x.date <= sc.end_date
                               for x in ctx.shifts.values() if x.week == sh.week)
                        and sum(1 for x in ctx.shifts.values() if x.week == sh.week) == 21})
        emps = sorted(e for e in ctx.emp if ctx.emp[e].part_time and ctx.emp[e].rota)
        rng.shuffle(emps)
        done = 0
        for emp in emps:
            if done >= n:
                break
            if emp in self.tainted_emps:
                continue
            e, team = ctx.emp[emp], ctx.emp[emp].team
            for week in rng.sample(weeks, len(weeks)):
                shifts = [s for s in ctx.shifts.values() if s.week == week]
                rng.shuffle(shifts)
                added = []
                for sh in shifts:
                    if st.week_hours[(emp, week)] > e.max_hours:
                        break
                    if (team, sh.id) in self.tainted_team_shifts or st.check(emp, sh, CAP_NONE) is not None:
                        continue
                    ts = self._edit_time(rng, sh)
                    if ts is None:
                        continue
                    added.append(st.assign(emp, sh, team, None, "MANUAL", ts, self._manager(team), "MANUAL_TOPUP"))
                if st.week_hours[(emp, week)] > e.max_hours:
                    for k in added:
                        self.tainted_team_shifts.add((team, st.asg[k]["shift_id"]))
                    self._taint(emp)
                    hours = st.week_hours[(emp, week)]
                    self._label("OVERTIME_CAP_EXCEEDED", "employee_week", f"{emp}|{week}", added, emp, team, None,
                                week, "Scheduled hours in an ISO week exceed max_weekly_hours",
                                f"Manual top-ups scheduled {hours:.0f}h against a {e.max_hours:.0f}h cap.")
                    done += 1
                    break
                self._rollback(added)
        return done

    def _rollback(self, keys):
        """Undo assignments created in this attempt (they were never published or exported)."""
        st = self.st
        for k in reversed(keys):
            a = st.asg.pop(k)
            sh = self.ctx.shifts[a["shift_id"]]
            del st.emp_day[a["employee_id"]][sh.date]
            st.team_shift[(a["team_id"], sh.id)].pop(k)
            st._account(a["employee_id"], sh, -1)
            assert st.asg_events[-1]["assignment_id"] == k
            st.asg_events.pop()

    def swap_applied_without_approval(self, n):
        rng, ctx, st, sim = self._rng("swap"), self.ctx, self.st, self.sim
        done = 0
        for k in self._active_keys(rng):
            if done >= n:
                break
            a = st.asg[k]
            req, team, sh = a["employee_id"], a["team_id"], st.shift_of(k)
            if req in self.tainted_emps or ctx.emp[req].team != team or (team, sh.id) in self.tainted_team_shifts:
                continue
            mates = [m for m in ctx.rota[team] if m != req and m not in self.tainted_emps
                     and st.check(m, sh, CAP_MAX) is None
                     and (a["slot_skill_id"] is None or ctx.has_skill(m, a["slot_skill_id"], sh.date))
                     and st.coverage_preserved(team, sh, req, m)]
            if not mates:
                continue
            target = rng.choice(mates)
            requested = self._edit_time(rng, sh, not_before=a["created_at"])
            if requested is None:
                continue
            applied = requested + timedelta(minutes=rng.randint(30, 600))
            if applied > sh.start - timedelta(hours=2):
                continue
            withdrawn = rng.random() < 0.3
            key = f"S:{len(sim.swaps) + 1}"
            sim.swaps.append({"swap_id": key, "swap_type": "GIVEAWAY", "team_id": team,
                              "requester_employee_id": req, "requester_assignment_id": k,
                              "target_employee_id": target, "target_assignment_id": None,
                              "requested_at": requested, "status": "WITHDRAWN" if withdrawn else "REQUESTED",
                              "decided_at": None, "decided_by_employee_id": None, "decision_reason": None,
                              "applied_at": None})
            sim._swap_event(key, "REQUESTED", requested, req, None)
            if withdrawn:
                wts = requested + timedelta(minutes=rng.randint(10, 25))
                sim.swaps[-1].update(decided_at=wts, decision_reason="REQUESTER_WITHDREW")
                sim._swap_event(key, "WITHDRAWN", wts, req, "REQUESTER_WITHDREW")
            st.end(k, "SUPERSEDED", applied, "SWAP_APPLIED", req, swap=key)
            nk = st.assign(target, sh, team, a["slot_skill_id"], "SWAP", applied, req, "SWAP_APPLIED",
                           swap=key, replaces=k)
            st.asg_events[-2]["related_assignment_id"] = nk
            self._taint(req, target, team_shift=(team, sh.id))
            self._label("SWAP_APPLIED_WITHOUT_APPROVAL", "swap_request", key, [k, nk], req, team, sh, None,
                        "Assignment changed by a swap that has no APPROVED decision",
                        "Self-service change applied while the swap was " + ("withdrawn." if withdrawn else "still pending."))
            done += 1
        return done

    # ------------------------------------------------------------------ orchestrate
    def inject_all(self, n_per_type):
        counts = {
            "LEAVE_OVERLAPS_ASSIGNMENT": self.leave_overlaps_assignment(n_per_type),
            "REQUIRED_SKILL_ABSENT": self.required_skill_absent(n_per_type),
            "SWAP_APPLIED_WITHOUT_APPROVAL": self.swap_applied_without_approval(n_per_type),
            "OVERTIME_CAP_EXCEEDED": self.overtime_cap_exceeded(n_per_type),
            "DOUBLE_BOOKED": self.double_booked(n_per_type),
        }
        short = {k: v for k, v in counts.items() if v < n_per_type}
        if short:
            raise RuntimeError(f"could not place all requested anomalies: {short}")
        return counts
