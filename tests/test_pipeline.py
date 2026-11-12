"""End-to-end behaviour of the starter dataset."""
import csv
import json
import re
import unittest

from fairshift.config import SCALES
from fairshift.io import load_dataset

from .helpers import starter_run


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.result = starter_run()
        cls.tables, cls.errors = load_dataset(cls.out / "data" / "csv")

    def test_validation_passes(self):
        summary = json.loads((self.out / "reports" / "validation_summary.json").read_text())
        failed = [c["check"] for c in summary["checks"] if c["status"] != "PASS"]
        self.assertEqual(failed, [])
        self.assertEqual(self.errors, [])

    def test_detector_finds_every_label_and_nothing_else(self):
        ev = self.result["evaluation"]
        self.assertEqual(ev["overall"]["precision"], 1.0)
        self.assertEqual(ev["overall"]["recall"], 1.0)
        self.assertTrue(all(v == 0 for v in ev["guard_rule_findings"].values()))

    def test_each_required_edge_case_is_present(self):
        with open(self.out / "ground_truth" / "ground_truth.csv", newline="") as f:
            types = {r["issue_type"] for r in csv.DictReader(f)}
        self.assertEqual(types, {"DOUBLE_BOOKED", "LEAVE_OVERLAPS_ASSIGNMENT", "REQUIRED_SKILL_ABSENT",
                                 "OVERTIME_CAP_EXCEEDED", "SWAP_APPLIED_WITHOUT_APPROVAL"})

    def test_volumes_match_configuration(self):
        sc = SCALES["starter"]
        self.assertEqual(len(self.tables["employee"]), sc.employees)
        self.assertEqual(len(self.tables["team"]), sc.teams)
        self.assertEqual(len(self.tables["shift"]), sc.days * 3)
        self.assertEqual(len(self.tables["leave_request"]), sc.leave_requests)

    def test_id_conventions_from_brief(self):
        t = self.tables
        self.assertEqual(t["employee"][0]["employee_id"], "EMP-000001")
        self.assertIn("SHIFT-2026-01-01-A", {s["shift_id"] for s in t["shift"]})
        self.assertTrue(all(re.fullmatch(r"LVE-2026-\d{6}", r["leave_id"]) for r in t["leave_request"]))
        self.assertTrue(all(re.fullmatch(r"SWP-2026-\d{6}", r["swap_id"]) for r in t["swap_request"]))
        for e in t["attendance_event"]:
            self.assertEqual(e["attendance_event_id"], f"ATT-{e['employee_id']}-{e['event_ts']:%Y%m%dT%H%M%S}")

    def test_ids_are_chronological_so_they_do_not_reveal_injections(self):
        for table, ts in (("shift_assignment", "created_at"), ("leave_request", "submitted_at"),
                          ("swap_request", "requested_at")):
            stamps = [r[ts] for r in self.tables[table]]  # tables are sorted by ID
            self.assertEqual(stamps, sorted(stamps), table)

    def test_no_label_columns_in_inputs(self):
        for name, rows in self.tables.items():
            for col in rows[0]:
                self.assertNotIn(col, ("issue_type", "ground_truth", "is_anomaly", "label"), name)

    def test_history_is_preserved(self):
        statuses = {a["status"] for a in self.tables["shift_assignment"]}
        self.assertTrue({"RELEASED", "SUPERSEDED"} <= statuses, "changes must end old rows, not overwrite them")
        events_per_asg = {}
        for e in self.tables["assignment_event"]:
            events_per_asg.setdefault(e["assignment_id"], []).append(e["event_type"])
        for a in self.tables["shift_assignment"]:
            self.assertEqual(events_per_asg[a["assignment_id"]][0], "CREATED")
