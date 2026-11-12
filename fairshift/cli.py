"""Command-line interface: python -m fairshift <command> --help"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import DEFAULT_SEED, SCALES, Policy, resolve_scale


def _policy_from_manifest(cfg: dict) -> Policy:
    p = dict(cfg["policy"])
    p.pop("peak_uplift_from", None)
    p["peak_uplift_departments"] = tuple(p["peak_uplift_departments"])
    return Policy(**p)


def cmd_generate(args) -> int:
    from .pipeline import run
    scale = resolve_scale(args.scale, employees=args.employees, teams=args.teams, days=args.days,
                          leave_requests=args.leave_requests, swap_requests=args.swap_requests,
                          anomalies_per_type=args.anomalies_per_type, start_date=args.start_date)
    out = Path(args.out or f"out/{scale.name}")
    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    command = "python -m fairshift " + " ".join(shlex.quote(a) for a in sys.argv[1:])
    result = run(scale, Policy(), args.seed, out, formats=formats, command=command)
    print(f"Outputs in {out}/  (open {out}/reports/report.html)")
    return 0 if result["ok"] else 1


def cmd_validate(args) -> int:
    """Re-validate an existing output folder from its files alone (useful after editing data by hand)."""
    from .derive import Reference, derive_all
    from .detect import detect, evaluate
    from .io import load_dataset
    from .schema import ISSUE_TYPES
    from .validate import render_markdown, validate
    out = Path(args.data)
    manifest = json.loads((out / "manifest" / "run_manifest.json").read_text(encoding="utf-8"))
    policy = _policy_from_manifest(manifest["config"])
    tables, errors = load_dataset(out / "data" / "csv")
    truth = []
    with open(out / "ground_truth" / "ground_truth.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["related_record_ids"] = [x for x in r["related_record_ids"].split("|") if x]
            truth.append(r)
    ref = Reference(tables)
    derived = derive_all(ref)
    findings = detect(ref, policy)
    ev = evaluate(findings, truth, ISSUE_TYPES)
    sql = out / "data" / "sql"
    rep = validate(tables, derived, truth, findings, policy, errors,
                   (sql / "schema.sql", sql / "seed.sql") if (sql / "seed.sql").exists() else None)
    print(render_markdown(rep, f"Validation of {out}"))
    print(f"Detector: precision {ev['overall']['precision']:.3f}, recall {ev['overall']['recall']:.3f}; "
          f"guard findings {ev['guard_rule_findings']}")
    return 0 if rep.ok else 1


def cmd_repro(args) -> int:
    """Generate twice in fresh processes (different PYTHONHASHSEED) and compare row counts and checksums."""
    runs = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, hashseed in enumerate(("1", "2")):
            out = Path(tmp) / f"run{i + 1}"
            env = dict(os.environ, PYTHONHASHSEED=hashseed)
            cmd = [sys.executable, "-m", "fairshift", "generate", "--scale", args.scale, "--seed", str(args.seed),
                   "--out", str(out), "--formats", args.formats]
            print(f"run {i + 1}: {' '.join(cmd[2:])}  (PYTHONHASHSEED={hashseed})")
            subprocess.run(cmd, check=True, env=env, stdout=subprocess.DEVNULL)
            runs.append(json.loads((out / "manifest" / "run_manifest.json").read_text(encoding="utf-8")))
    a, b = runs
    diffs = sorted(k for k in set(a["files"]) | set(b["files"])
                   if a["files"].get(k, {}).get("sha256") != b["files"].get(k, {}).get("sha256"))
    counts_equal = a["row_counts"] == b["row_counts"]
    ok = not diffs and counts_equal
    lines = [f"# Reproducibility check — scale `{args.scale}`, seed `{args.seed}`", "",

             "Two independent processes with different `PYTHONHASHSEED` values generated the dataset.", "",
             f"**Result: {'IDENTICAL' if ok else 'DIFFERENT'}** — {len(a['files'])} files compared by SHA-256, "
             f"{len(a['row_counts'])} row counts compared.", "",
             "| File | Bytes | SHA-256 (run 1) | Same in run 2 |", "|---|---:|---|---|"]
    for k in sorted(a["files"]):
        lines.append(f"| `{k}` | {a['files'][k]['bytes']:,} | `{a['files'][k]['sha256'][:16]}…` | "
                     f"{'yes' if k not in diffs else '**no**'} |")
    lines += ["", "| Table | Rows run 1 | Rows run 2 |", "|---|---:|---:|"]
    for k, v in a["row_counts"].items():
        lines.append(f"| {k} | {v:,} | {b['row_counts'].get(k, 0):,} |")
    text = "\n".join(x for x in lines if x is not None) + "\n"
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8", newline="\n")
        print(f"report written to {args.report}")
    print(f"Reproducibility: {'IDENTICAL' if ok else 'DIFFERENT: ' + ', '.join(diffs[:5])}")
    return 0 if ok else 1


def cmd_docs(args) -> int:
    from .docgen import write_docs
    for p in write_docs(Path(args.out)):
        print(f"wrote {p}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fairshift",
                                 description="Fair, feasible shift scheduling with synthetic data, exceptions and validation.")
    sub = ap.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate data, schedule, inject edge cases, derive, detect, validate, report")
    g.add_argument("--scale", choices=sorted(SCALES), default="starter")
    g.add_argument("--seed", type=int, default=DEFAULT_SEED)
    g.add_argument("--out", help="output folder (default out/<scale>)")
    g.add_argument("--formats", default="csv,json,sql", help="comma list from csv,json,sql (csv is always written)")
    for flag in ("employees", "teams", "days", "leave-requests", "swap-requests", "anomalies-per-type"):
        g.add_argument(f"--{flag}", type=int, help="override the scale preset")
    g.add_argument("--start-date", help="override the window start (YYYY-MM-DD)")
    g.set_defaults(func=cmd_generate)

    v = sub.add_parser("validate", help="re-validate an existing output folder from its files")
    v.add_argument("--data", default="out/starter")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("repro", help="generate twice and compare checksums")
    r.add_argument("--scale", choices=sorted(SCALES), default="starter")
    r.add_argument("--seed", type=int, default=DEFAULT_SEED)
    r.add_argument("--formats", default="csv,json,sql")
    r.add_argument("--report", help="write a markdown report here")
    r.set_defaults(func=cmd_repro)

    d = sub.add_parser("docs", help="regenerate docs/DATA_DICTIONARY.md and docs/ERD.md from the schema")
    d.add_argument("--out", default="docs")
    d.set_defaults(func=cmd_docs)

    args = ap.parse_args(argv)
    return args.func(args)
