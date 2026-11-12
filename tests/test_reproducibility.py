import tempfile
import unittest
from pathlib import Path

from fairshift.config import DEFAULT_SEED, Policy, resolve_scale
from fairshift.pipeline import run

from .helpers import starter_run


class ReproducibilityTest(unittest.TestCase):
    def test_same_seed_identical_files_different_seed_differs(self):
        _, first = starter_run()
        with tempfile.TemporaryDirectory() as tmp:
            again = run(resolve_scale("starter"), Policy(), DEFAULT_SEED, Path(tmp) / "a", log=lambda *a: None)
            other = run(resolve_scale("starter"), Policy(), DEFAULT_SEED + 1, Path(tmp) / "b", log=lambda *a: None)
        f1, f2, f3 = (r["manifest"]["files"] for r in (first, again, other))
        self.assertEqual({k: v["sha256"] for k, v in f1.items()}, {k: v["sha256"] for k, v in f2.items()})
        self.assertNotEqual(f1["data/csv/shift_assignment.csv"]["sha256"], f3["data/csv/shift_assignment.csv"]["sha256"])
        self.assertEqual(first["manifest"]["row_counts"], again["manifest"]["row_counts"])

    def test_scale_is_parameterised(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run(resolve_scale("starter", employees=150, teams=6, days=21, leave_requests=80),
                    Policy(), DEFAULT_SEED, Path(tmp) / "c", log=lambda *a: None)
        self.assertTrue(r["ok"])
        self.assertEqual(r["manifest"]["row_counts"]["employee"], 150)
        self.assertEqual(r["manifest"]["row_counts"]["leave_request"], 80)
