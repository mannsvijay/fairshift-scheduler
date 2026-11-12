"""End-to-end pipeline.

  master data -> leave decisions -> event-driven scheduling -> labelled anomalies
  -> chronological ID assignment -> attendance -> export (CSV/JSON/SQL)
  -> reload exported CSV -> derive -> detect -> evaluate -> validate -> reports

Everything after export is computed from the exported files, so the outputs
describe exactly what is shipped.
"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import time
from pathlib import Path

from .anomalies import Injector
from .attendance import generate_attendance
from .config import Policy, Scale, config_snapshot
from .core import sequenced_id
from .derive import DERIVED_COLUMNS, Reference, derive_all
from .detect import FINDING_COLUMNS, detect, evaluate
from .io import (ddl, load_dataset, write_csv, write_json, write_sql_seed, write_text)
from .leave import generate_leave
from .master import build_master
from .report import render_html, render_summary
from .schema import GROUND_TRUTH_COLUMNS, ISSUE_TYPES, TABLE_BY_NAME, TABLE_ORDER
from .simulate import Simulation
from .validate import render_markdown, validate

ALL_FORMATS = ("csv", "json", "sql")


# --------------------------------------------------------------------------- ID finalisation
def finalize_ids(tables: dict, truth: list, year: int) -> None:
    """Replace provisional keys ('A:12', 'L:7', ...) with final, chronologically sequenced IDs.

    IDs are numbered in order of each record's own creation timestamp. Injected records
    therefore interleave naturally with baseline records instead of sitting at the end
    of the sequence, where their position alone would reveal them.
    """
    specs = {  # kind: (table, pk, timestamp column)
        "A": ("shift_assignment", "assignment_id", "created_at"),
        "AE": ("assignment_event", "assignment_event_id", "event_ts"),
        "L": ("leave_request", "leave_id", "submitted_at"),
        "LE": ("leave_request_event", "leave_event_id", "event_ts"),
        "S": ("swap_request", "swap_id", "requested_at"),
        "SE": ("swap_request_event", "swap_event_id", "event_ts"),
    }
    maps = {}
    for kind, (table, pk, ts) in specs.items():
        order = sorted(tables[table], key=lambda r: (r[ts], int(r[pk].split(":")[1])))
        maps[kind] = {r[pk]: sequenced_id(kind, year, i) for i, r in enumerate(order, start=1)}

    def remap(v):
        if isinstance(v, str) and ":" in v:
            kind = v.split(":")[0]
            if kind in maps:
                return maps[kind][v]
        return v

    refs = {"shift_assignment": ("assignment_id", "swap_id", "replaces_assignment_id"),
            "assignment_event": ("assignment_event_id", "assignment_id", "related_leave_id", "related_swap_id",
                                 "related_assignment_id"),
            "leave_request": ("leave_id",), "leave_request_event": ("leave_event_id", "leave_id"),
            "swap_request": ("swap_id", "requester_assignment_id", "target_assignment_id"),
            "swap_request_event": ("swap_event_id", "swap_id")}
    for table, cols in refs.items():
        for r in tables[table]:
            for c in cols:
                r[c] = remap(r[c])
        tables[table].sort(key=lambda r: r[TABLE_BY_NAME[table].pk])
    for g in truth:
        g["record_id"] = remap(g["record_id"])
        g["related_record_ids"] = sorted(remap(x) for x in g["related_record_ids"])


# --------------------------------------------------------------------------- generation
def generate_tables(scale: Scale, policy: Policy, seed: int, log=print):
    t0 = time.time()
    ctx = build_master(scale, policy, seed)
    log(f"  master data           {sum(len(v) for v in ctx.tables.values()):>9,} rows  ({time.time() - t0:.1f}s)")
    n_leave_anomalies = scale.anomalies_per_type
    leave_rows, leave_events = generate_leave(ctx, scale.leave_requests - n_leave_anomalies)
    log(f"  leave decisions       {len(leave_rows):>9,} requests ({time.time() - t0:.1f}s)")
    sim = Simulation(ctx, leave_rows).run()
    log(f"  scheduling timeline   {len(sim.state.asg):>9,} assignments, {len(sim.swaps):,} swaps ({time.time() - t0:.1f}s)")
    inj = Injector(sim, leave_rows, leave_events)
    counts = inj.inject_all(scale.anomalies_per_type)
    log(f"  labelled anomalies    {sum(counts.values()):>9,} ({', '.join(f'{k}={v}' for k, v in counts.items())})")

    tables = dict(ctx.tables)
    tables["shift_assignment"] = list(sim.state.asg.values())
    tables["assignment_event"] = sim.state.asg_events
    tables["leave_request"] = leave_rows
    tables["leave_request_event"] = leave_events
    tables["swap_request"] = sim.swaps
    tables["swap_request_event"] = sim.swap_events
    truth = inj.truth
    finalize_ids(tables, truth, scale.start_date.year)
    tables["attendance_event"] = generate_attendance(ctx, tables["shift_assignment"], tables["leave_request"])
    log(f"  attendance            {len(tables['attendance_event']):>9,} clock events ({time.time() - t0:.1f}s)")

    truth.sort(key=lambda g: (g["issue_type"], g["record_id"]))
    for i, g in enumerate(truth, start=1):
        g["anomaly_id"] = f"GT-{i:05d}"
    for name in ("employee", "employee_skill", "team", "skill", "coverage_requirement", "holiday_calendar", "shift"):
        tables[name].sort(key=lambda r: r[TABLE_BY_NAME[name].pk])
    return tables, truth


# --------------------------------------------------------------------------- outputs
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(scale: Scale, policy: Policy, seed: int, out_dir: Path, formats=ALL_FORMATS, command: str = "",
        log=print) -> dict:
    t0 = time.time()
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    log(f"Generating '{scale.name}' (seed {seed}) -> {out_dir}")
    tables, truth = generate_tables(scale, policy, seed, log)

    data = out_dir / "data"
    for name in TABLE_ORDER:  # CSV is always written: it is what everything downstream reads back
        cols = TABLE_BY_NAME[name].column_names
        write_csv(data / "csv" / f"{name}.csv", cols, tables[name])
        if "json" in formats:
            write_json(data / "json" / f"{name}.json", cols, tables[name])
    sql_paths = None
    if "sql" in formats:
        write_text(data / "sql" / "schema.sql", ddl())
        write_sql_seed(data / "sql" / "seed.sql", tables)
        sql_paths = (data / "sql" / "schema.sql", data / "sql" / "seed.sql")
    gt_dir = out_dir / "ground_truth"
    write_csv(gt_dir / "ground_truth.csv", GROUND_TRUTH_COLUMNS, truth)
    write_json(gt_dir / "ground_truth.json", GROUND_TRUTH_COLUMNS, truth)
    log(f"  exported              ({time.time() - t0:.1f}s)")

    # ---- everything below reads the exported files back
    loaded, parse_errors = load_dataset(data / "csv")
    ref = Reference(loaded)
    derived = derive_all(ref)
    for name, cols in DERIVED_COLUMNS.items():
        write_csv(out_dir / "derived" / f"{name}.csv", cols, derived[name])
    findings = detect(ref, policy)
    write_csv(out_dir / "derived" / "exceptions.csv", FINDING_COLUMNS, findings)
    evaluation = evaluate(findings, truth, ISSUE_TYPES)
    report = validate(loaded, derived, truth, findings, policy, parse_errors, sql_paths)
    log(f"  derived/detected/validated ({time.time() - t0:.1f}s): validation "
        f"{'PASS' if report.ok else 'FAIL'}, detector P={evaluation['overall']['precision']:.3f} "
        f"R={evaluation['overall']['recall']:.3f}")

    reports = out_dir / "reports"
    cfg = config_snapshot(scale, policy, seed)
    kpis = compute_kpis(loaded, derived, findings)
    write_text(reports / "validation_summary.json", json.dumps({"overall": "PASS" if report.ok else "FAIL",
                                                                "checks": report.checks}, indent=2) + "\n")
    write_text(reports / "validation_summary.md", render_markdown(report, f"Validation summary — {scale.name}"))
    write_text(reports / "evaluation.json", json.dumps({"detector": evaluation, "kpis": kpis}, indent=2, default=str) + "\n")
    write_text(reports / "summary.md", render_summary(cfg, tables, truth, evaluation, kpis, report))
    write_text(reports / "report.html", render_html(cfg, loaded, derived, evaluation, kpis, report))

    manifest_dir = out_dir / "manifest"
    write_text(manifest_dir / "source_manifest.json", json.dumps(source_manifest(), indent=2) + "\n")
    files = sorted(p for p in out_dir.rglob("*") if p.is_file() and "manifest" not in p.parts)
    row_counts = {name: len(tables[name]) for name in TABLE_ORDER}
    row_counts.update({f"derived/{k}": len(v) for k, v in derived.items()})
    row_counts["derived/exceptions"] = len(findings)
    row_counts["ground_truth"] = len(truth)
    run_manifest = {
        "generator_command": command, "config": cfg, "row_counts": row_counts,
        "files": {str(p.relative_to(out_dir)).replace("\\", "/"): {"sha256": sha256(p), "bytes": p.stat().st_size}
                  for p in files},
        "validation_overall": "PASS" if report.ok else "FAIL",
        "environment_note": "Checksums depend only on seed + config; generation uses no wall-clock time.",
    }
    write_text(manifest_dir / "run_manifest.json", json.dumps(run_manifest, indent=2) + "\n")
    log(f"Done in {time.time() - t0:.1f}s. Validation: {'PASS' if report.ok else 'FAIL'}. "
        f"Python {platform.python_version()}.")
    return {"ok": report.ok, "evaluation": evaluation, "manifest": run_manifest, "kpis": kpis}


def compute_kpis(t, derived, findings) -> dict:
    from collections import Counter
    cov = derived["coverage_status"]

    def rate(stage):
        return round(sum(1 for r in cov if r[f"{stage}_gap"] == 0) / len(cov), 4) if cov else 1.0
    gaps = Counter(g["gap_stage"] for g in derived["coverage_gaps"])
    recon = Counter(r["outcome"] for r in derived["attendance_reconciliation"])
    weekly = derived["weekly_hours"]
    leave = t["leave_request"]
    by_type = {}
    for lt in ("ANNUAL", "SICK", "PERSONAL", "UNPAID"):
        rows = [r for r in leave if r["leave_type"] == lt]
        by_type[lt] = {"requests": len(rows), "approved": sum(r["status"] == "APPROVED" for r in rows),
                       "approval_rate": round(sum(r["decision_reason"] in ("POLICY_COMPLIANT", "SICK_AUTO_APPROVED")
                                                  for r in rows) / len(rows), 4) if rows else None}
    fair = [f for f in derived["fairness_by_team"] if f["mean_utilisation"] is not None]
    asg = t["shift_assignment"]
    home_team = {e["employee_id"]: e["team_id"] for e in t["employee"]}
    return {
        "coverage_requirements_evaluated": len(cov),
        "coverage_met_rate": {"at_publication": rate("planned"), "final_schedule": rate("final"),
                              "attended": rate("attended")},
        "coverage_gaps_by_stage": dict(sorted(gaps.items())),
        "planning_gaps_recovered_by_topup": sum(1 for r in cov if r["planned_gap"] > 0 and r["final_gap"] == 0),
        "assignments_by_source": dict(sorted(Counter(a["source"] for a in asg).items())),
        "assignments_by_status": dict(sorted(Counter(a["status"] for a in asg).items())),
        "cross_team_cover_assignments": sum(1 for a in asg if a["status"] == "ACTIVE"
                                            and a["team_id"] != home_team[a["employee_id"]]),
        "scheduled_hours_total": round(sum(w["scheduled_hours"] for w in weekly), 1),
        "overtime_scheduled_hours_total": round(sum(w["overtime_scheduled_hours"] for w in weekly), 1),
        "overtime_actual_hours_total": round(sum(w["overtime_actual_hours"] for w in weekly), 1),
        "employee_weeks_with_scheduled_overtime": sum(1 for w in weekly if w["overtime_scheduled_hours"] > 0),
        "employee_weeks_over_cap": sum(1 for w in weekly if w["cap_exceeded"]),
        "attendance_outcomes": dict(sorted(recon.items())),
        "leave_outcomes": dict(sorted(Counter(r["status"] for r in leave).items())),
        "leave_decision_reasons": dict(sorted(Counter(r["decision_reason"] or "PENDING" for r in leave).items())),
        "leave_by_type": by_type,
        "swap_outcomes": dict(sorted(Counter(s["status"] for s in t["swap_request"]).items())),
        "swap_decision_reasons": dict(sorted(Counter(s["decision_reason"] or "PENDING" for s in t["swap_request"]).items())),
        "fairness": {
            "teams": len(fair),
            "mean_gini_utilisation": round(sum(f["gini_utilisation"] for f in fair) / len(fair), 4) if fair else None,
            "worst_team_gini_utilisation": max((f["gini_utilisation"] for f in fair), default=None),
            "mean_night_shift_std_per_4_weeks": round(sum(f["night_shifts_std"] for f in fair) / len(fair), 3) if fair else None,
            "mean_unsocial_shift_std_per_4_weeks": round(sum(f["unsocial_shifts_std"] for f in fair) / len(fair), 3) if fair else None,
        },
        "exceptions_by_type": dict(sorted(Counter(f["issue_type"] for f in findings).items())),
    }


def source_manifest() -> dict:
    return {
        "external_data_used": False,
        "summary": "All records are synthetic, produced by this repository's generator from a fixed seed. "
                   "No personal, confidential or third-party datasets were accessed, downloaded or redistributed.",
        "sources": [
            {"name": "Holiday calendar (fairshift/master.py: HOLIDAYS)", "type": "synthetic reference data",
             "basis": "General public knowledge of Indian national/regional holiday patterns, used for schema "
                      "realism only. Lunar-festival dates are marked APPROXIMATE and must be confirmed against the "
                      "official notification before any real use.",
             "license": "Facts; authored by the project author.", "retrieved": None, "transformations": "none"},
            {"name": "Given/family name lists (fairshift/master.py)", "type": "synthetic",
             "basis": "Author-curated lists of common names, combined at random. No real person's record.",
             "license": "Authored by the project author.", "retrieved": None,
             "transformations": "random combination; emails use the reserved example.com domain"},
            {"name": "Skill catalogue, departments, staffing ratios, policies", "type": "synthetic",
             "basis": "Author-defined to model a multi-site warehouse and support operation.",
             "license": "Authored by the project author.", "retrieved": None, "transformations": "none"},
        ],
        "fields_discarded": [],
    }
