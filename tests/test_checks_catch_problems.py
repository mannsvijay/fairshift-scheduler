"""Negative tests: the detector and the validator must catch problems introduced by hand."""
import copy
import unittest
from datetime import timedelta

from fairshift.config import Policy
from fairshift.derive import Reference, derive_all
from fairshift.detect import detect
from fairshift.io import load_dataset
from fairshift.validate import validate

from .helpers import starter_run


class CatchProblemsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out, _ = starter_run()
        cls.base, _ = load_dataset(out / "data" / "csv")

    def tables(self):
        return copy.deepcopy(self.base)

    def run_checks(self, t):
        ref = Reference(t)
        findings = detect(ref, Policy())
        rep = validate(t, derive_all(ref), [], findings, Policy(), [], None)
        return findings, {c["check"]: c for c in rep.checks}

    def test_detector_flags_a_new_double_booking(self):
        t = self.tables()
        a = next(x for x in t["shift_assignment"] if x["status"] == "ACTIVE" and x["source"] == "PLANNED")
        dup = dict(a, assignment_id="ASG-2026-9999999", created_at=a["created_at"] + timedelta(hours=1))
        t["shift_assignment"].append(dup)
        findings, _ = self.run_checks(t)
        self.assertIn(("DOUBLE_BOOKED", "ASG-2026-9999999"), {(f["issue_type"], f["record_id"]) for f in findings})

    def test_validator_rejects_broken_foreign_key(self):
        t = self.tables()
        t["shift_assignment"][0]["employee_id"] = "EMP-999999"
        _, checks = self.run_checks(t)
        self.assertEqual(checks["shift_assignment.employee_id -> employee.employee_id"]["status"], "FAIL")

    def test_validator_rejects_overwritten_history(self):
        t = self.tables()
        a = next(x for x in t["shift_assignment"] if x["status"] == "SUPERSEDED")
        a["status"] = "ACTIVE"  # pretend the change never happened
        _, checks = self.run_checks(t)
        name = "shift_assignment: event history follows the state machine and matches current status"
        self.assertEqual(checks[name]["status"], "FAIL")

    def test_validator_rejects_bad_enum_and_date_order(self):
        t = self.tables()
        t["leave_request"][0]["leave_type"] = "HOLIDAY"
        lv = t["leave_request"][1]
        lv["end_date"] = lv["start_date"] - timedelta(days=1)
        _, checks = self.run_checks(t)
        self.assertEqual(checks["leave_request: enum values allowed"]["status"], "FAIL")
        self.assertEqual(checks["start<=end, submitted<=decided<=cancelled/applied, published<start<end, "
                                "created before shift"]["status"], "FAIL")

    def test_unlabelled_violation_fails_acceptance(self):
        t = self.tables()  # with an empty ground truth, every real anomaly is "unexplained"
        _, checks = self.run_checks(t)
        ac2 = next(c for n, c in checks.items() if n.startswith("AC2"))
        self.assertEqual(ac2["status"], "FAIL")
