"""Unit tests for the hard scheduling constraints and the leave decision rules."""
import unittest
from datetime import timedelta

from fairshift.config import DEFAULT_SEED, Policy, resolve_scale
from fairshift.engine import CAP_CONTRACT, CAP_MAX, ScheduleState
from fairshift.leave import generate_leave
from fairshift.master import build_master


class ConstraintTest(unittest.TestCase):
    def setUp(self):
        self.ctx = build_master(resolve_scale("starter"), Policy(), DEFAULT_SEED)
        self.st = ScheduleState(self.ctx)
        self.emp = next(e for e in sorted(self.ctx.emp) if self.ctx.emp[e].rota and self.ctx.emp[e].night_ok
                        and not self.ctx.emp[e].part_time and self.ctx.emp[e].hire < self.ctx.scale.start_date
                        and self.ctx.emp[e].term is None)
        self.team = self.ctx.emp[self.emp].team
        self.d = self.ctx.scale.start_date + timedelta(days=4)  # a Monday

    def shift(self, d, code):
        return {s.code: s for s in self.ctx.shifts_by_date[d]}[code]

    def give(self, d, code):
        s = self.shift(d, code)
        return self.st.assign(self.emp, s, self.team, None, "PLANNED", s.publish_ts, None, "SCHEDULE_PUBLISHED")

    def test_free_employee_is_eligible(self):
        self.assertIsNone(self.st.check(self.emp, self.shift(self.d, "A")))

    def test_double_booking_rejected(self):
        self.give(self.d, "A")
        self.assertEqual(self.st.check(self.emp, self.shift(self.d, "B")), "DOUBLE_BOOKING")

    def test_rest_rule_after_night(self):
        self.give(self.d, "C")  # 22:00 -> 06:00 next day
        nxt = self.d + timedelta(days=1)
        self.assertEqual(self.st.check(self.emp, self.shift(nxt, "A")), "REST_RULE")   # 0h rest
        self.assertEqual(self.st.check(self.emp, self.shift(nxt, "B")), "REST_RULE")   # 8h rest
        self.assertIsNone(self.st.check(self.emp, self.shift(nxt, "C")))               # 16h rest

    def test_consecutive_days_limit(self):
        for i in range(6):
            self.give(self.d + timedelta(days=i), "A")
        self.assertEqual(self.st.check(self.emp, self.shift(self.d + timedelta(days=6), "A"), CAP_MAX),
                         "CONSECUTIVE_DAYS")

    def test_weekly_contract_then_overtime_cap(self):
        for i in range(5):  # Mon-Fri = 40h = full-time contract
            self.give(self.d + timedelta(days=i), "A")
        sat = self.shift(self.d + timedelta(days=5), "A")
        self.assertEqual(self.st.check(self.emp, sat, CAP_CONTRACT), "WEEKLY_HOURS_CAP")
        self.assertIsNone(self.st.check(self.emp, sat, CAP_MAX))  # 48h allowed as overtime

    def test_approved_leave_blocks_assignment(self):
        self.st.leave_days[self.emp][self.d] = "L:1"
        self.assertEqual(self.st.check(self.emp, self.shift(self.d, "A")), "ON_LEAVE")

    def test_night_ineligible(self):
        e = next(x for x in sorted(self.ctx.emp) if self.ctx.emp[x].rota and not self.ctx.emp[x].night_ok)
        self.assertEqual(self.st.check(e, self.shift(self.d, "C")), "NIGHT_INELIGIBLE")

    def test_managers_are_not_on_the_rota(self):
        mgr = self.ctx.team[self.team]["manager_employee_id"]
        self.assertEqual(self.st.check(mgr, self.shift(self.d, "A")), "NOT_ROTA")

    def test_release_frees_the_slot_and_keeps_history(self):
        k = self.give(self.d, "A")
        self.st.end(k, "RELEASED", self.shift(self.d, "A").publish_ts, "LEAVE_APPROVED", None)
        self.assertIsNone(self.st.check(self.emp, self.shift(self.d, "B")))
        self.assertEqual(self.st.asg[k]["status"], "RELEASED")
        self.assertEqual([e["event_type"] for e in self.st.asg_events], ["CREATED", "RELEASED"])


class LeaveRuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = build_master(resolve_scale("full"), Policy(), DEFAULT_SEED)
        cls.rows, cls.events = generate_leave(cls.ctx, 3000)

    def test_decisions_follow_the_documented_rules(self):
        pol = self.ctx.policy
        for r in self.rows:
            notice = (r["start_date"] - r["submitted_at"].date()).days
            if r["decision_reason"] == "POLICY_COMPLIANT":
                self.assertGreaterEqual(notice, pol.min_leave_notice_days)
                self.assertNotEqual(r["leave_type"], "SICK")
            if r["decision_reason"] == "SICK_AUTO_APPROVED":
                self.assertEqual(r["decision_channel"], "AUTO")
            if r["decision_reason"] == "INSUFFICIENT_NOTICE":
                self.assertLess(notice, pol.min_leave_notice_days)

    def test_every_outcome_is_explained(self):
        for r in self.rows:
            self.assertIsNotNone(r["decision_reason"], r["leave_id"])
            self.assertGreaterEqual(r["decided_at"], r["submitted_at"])

    def test_all_rejection_paths_are_exercised(self):
        reasons = {r["decision_reason"] for r in self.rows}
        for expected in ("TEAM_CAPACITY", "INSUFFICIENT_BALANCE", "INSUFFICIENT_NOTICE", "DUPLICATE_OVERLAP",
                         "MANAGER_NO_RESPONSE", "ALLOWANCE_EXCEEDED"):
            self.assertIn(expected, reasons)
