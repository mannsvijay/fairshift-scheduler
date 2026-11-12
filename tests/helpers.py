"""Shared fixture: one starter run per test session (cached in a temp folder)."""
import atexit
import shutil
import tempfile
from pathlib import Path

from fairshift.config import DEFAULT_SEED, Policy, resolve_scale
from fairshift.pipeline import run

_CACHE = {}


def starter_run():
    if "run" not in _CACHE:
        tmp = Path(tempfile.mkdtemp(prefix="fairshift-test-"))
        atexit.register(shutil.rmtree, tmp, True)
        result = run(resolve_scale("starter"), Policy(), DEFAULT_SEED, tmp / "out", log=lambda *a: None)
        _CACHE["run"] = (tmp / "out", result)
    return _CACHE["run"]
