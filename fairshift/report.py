"""Human-readable reports: a markdown summary and a self-contained HTML report."""
from __future__ import annotations

from .schema import TABLE_ORDER


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render_summary(cfg, tables, truth, evaluation, kpis, report) -> str:
    sc = cfg["scale"]
    L = [f"# Run summary — {sc['name']}", "",
         f"Seed `{cfg['seed']}` · window {sc['start_date']} → {sc['end_date']} ({sc['days']} days) · "
         f"generator v{cfg['generator_version']}", "",
         f"**Validation: {'PASS' if report.ok else 'FAIL'}** ({sum(c['status'] == 'PASS' for c in report.checks)}"
         f"/{len(report.checks)} checks). "
         f"**Exception detector: precision {evaluation['overall']['precision']:.3f}, recall "
         f"{evaluation['overall']['recall']:.3f}** on {len(truth)} labelled anomalies.", "",
         "## Volumes", "", "| Table | Rows |", "|---|---:|"]
    L += [f"| {n} | {len(tables[n]):,} |" for n in TABLE_ORDER]
    L += ["", "## Exception detection vs ground truth", "",
          "| Issue type | Labelled | Detected | TP | FP | FN | Precision | Recall |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for it, v in evaluation["per_issue_type"].items():
        L.append(f"| {it} | {v['ground_truth']} | {v['detected']} | {v['true_positive']} | {v['false_positive']} | "
                 f"{v['false_negative']} | {v['precision']:.3f} | {v['recall']:.3f} |")
    L += ["", "Guard rules (constraints the scheduler must never break; expected 0): " +
          ", ".join(f"{k}={v}" for k, v in evaluation["guard_rule_findings"].items()), "",
          "## Coverage", "",
          f"- Requirement checks (team × shift × requirement): {kpis['coverage_requirements_evaluated']:,}",
          f"- Met at publication: {_pct(kpis['coverage_met_rate']['at_publication'])} · final schedule: "
          f"{_pct(kpis['coverage_met_rate']['final_schedule'])} · attended: {_pct(kpis['coverage_met_rate']['attended'])}",
          f"- Planning gaps recovered by manager top-ups: {kpis['planning_gaps_recovered_by_topup']:,}",
          f"- Reported gaps by stage: {kpis['coverage_gaps_by_stage']}",
          f"- Cross-team cover assignments: {kpis['cross_team_cover_assignments']:,}", "",
          "## Working time", "",
          f"- Scheduled hours: {kpis['scheduled_hours_total']:,.0f} (overtime {kpis['overtime_scheduled_hours_total']:,.0f}); "
          f"actual overtime from late clock-outs: {kpis['overtime_actual_hours_total']:,.0f}",
          f"- Employee-weeks with scheduled overtime: {kpis['employee_weeks_with_scheduled_overtime']:,}; over the cap: "
          f"{kpis['employee_weeks_over_cap']:,} (all labelled anomalies)", "",
          "## Fairness", ""]
    f = kpis["fairness"]
    L += [f"- Mean Gini of utilisation within teams: {f['mean_gini_utilisation']} (worst team {f['worst_team_gini_utilisation']}); 0 = perfectly even",
          f"- Mean std-dev of night shifts per 4 weeks: {f['mean_night_shift_std_per_4_weeks']}; of weekend/holiday shifts: "
          f"{f['mean_unsocial_shift_std_per_4_weeks']}", "",
          "## Leave, swaps, attendance", "",
          f"- Leave outcomes: {kpis['leave_outcomes']}",
          f"- Leave decision reasons: {kpis['leave_decision_reasons']}",
          f"- Swap outcomes: {kpis['swap_outcomes']}",
          f"- Swap decision reasons: {kpis['swap_decision_reasons']}",
          f"- Attendance outcomes: {kpis['attendance_outcomes']}", ""]
    return "\n".join(L)


CATEGORY_LABELS = {"sql": "SQL round trip", "primary_keys": "Primary keys", "foreign_keys": "Foreign keys",
                   "ground_truth": "Ground-truth separation", "acceptance": "Acceptance criteria"}


def _esc(x) -> str:
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _heatmap(derived, t) -> str:
    """Team x day board: worst coverage state of each team on each day."""
    from collections import defaultdict
    worst = defaultdict(int)  # (team, date) -> 0 ok, 1 attendance gap, 2 schedule gap
    detail = defaultdict(list)
    for r in derived["coverage_status"]:
        key = (r["team_id"], r["shift_date"])
        lvl = 2 if r["final_gap"] else (1 if r["attended_gap"] else 0)
        if lvl:
            detail[key].append(f"{r['shift_id'][-1]} {r['requirement']}: -{r['final_gap'] or r['attended_gap']}")
        worst[key] = max(worst[key], lvl)
    teams = sorted({r["team_id"] for r in t["team"]})
    days = sorted({r["shift_date"] for r in t["shift"]})
    cw = max(4.0, min(22.0, 960 / len(days)))
    ch = 6.0 if len(teams) > 40 else 18.0
    left, top = 70, 22
    w, h = left + cw * len(days) + 4, top + ch * len(teams) + 4
    cls = {0: "ok", 1: "att", 2: "gap"}
    out = [f'<svg class="board" viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="Coverage by team and day">']
    for j, d in enumerate(days):
        if d.day == 1 or j == 0:
            out.append(f'<text x="{left + j * cw:.1f}" y="14" class="axis">{d.strftime("%b %d")}</text>')
    step = max(1, len(teams) // 10)
    for i, team in enumerate(teams):
        if i % step == 0:
            out.append(f'<text x="{left - 8}" y="{top + i * ch + ch * 0.8:.1f}" class="axis" text-anchor="end">{team}</text>')
        for j, d in enumerate(days):
            lvl = worst[(team, d)]
            tip = f"{team} {d.isoformat()}: " + ("fully covered" if not lvl else "; ".join(detail[(team, d)][:4]))
            out.append(f'<rect x="{left + j * cw:.1f}" y="{top + i * ch:.1f}" width="{cw - 1:.1f}" height="{ch - 1:.1f}" '
                       f'class="{cls[lvl]}"><title>{_esc(tip)}</title></rect>')
    out.append("</svg>")
    return "".join(out)


def _bars(rows, value_fmt=lambda v: f"{v:,}") -> str:
    """rows: [(label, value, css class)] -> horizontal bar list."""
    m = max((v for _l, v, _c in rows), default=0) or 1
    out = ['<div class="bars">']
    for label, v, c in rows:
        out.append(f'<div class="bar-row"><span class="bar-label">{_esc(label)}</span>'
                   f'<span class="bar-track"><span class="bar {c}" style="width:{100 * v / m:.1f}%"></span></span>'
                   f'<span class="bar-val">{value_fmt(v)}</span></div>')
    out.append("</div>")
    return "".join(out)


def _weekly_overtime(derived) -> str:
    from collections import defaultdict
    sched, actual = defaultdict(float), defaultdict(float)
    for w in derived["weekly_hours"]:
        sched[w["iso_week"]] += w["overtime_scheduled_hours"]
        actual[w["iso_week"]] += w["overtime_actual_hours"]
    weeks = sorted(sched)
    m = max(max(sched.values(), default=0), max(actual.values(), default=0)) or 1
    bw, gap, H, left = 26, 14, 150, 8
    W = left + len(weeks) * (2 * bw + gap)
    out = [f'<svg class="chart" viewBox="0 0 {W} {H + 34}" style="max-width:{min(760, W * 1.6):.0f}px" '
           f'role="img" aria-label="Overtime hours by ISO week">']
    for i, wk in enumerate(weeks):
        x = left + i * (2 * bw + gap)
        for k, (series, cls) in enumerate(((sched, "ot-s"), (actual, "ot-a"))):
            v = series[wk]
            bh = H * v / m
            out.append(f'<rect x="{x + k * bw}" y="{H - bh:.1f}" width="{bw - 3}" height="{bh:.1f}" class="{cls}">'
                       f'<title>{wk} {"scheduled" if k == 0 else "actual"} overtime: {v:,.0f}h</title></rect>')
        out.append(f'<text x="{x + bw}" y="{H + 16}" class="axis" text-anchor="middle">{wk[-3:]}</text>')
    out.append("</svg>")
    return "".join(out)


def render_html(cfg, t, derived, evaluation, kpis, report) -> str:
    sc = cfg["scale"]
    ev = evaluation
    cov = kpis["coverage_met_rate"]
    gaps = kpis["coverage_gaps_by_stage"]
    fair = kpis["fairness"]
    passed = sum(c["status"] == "PASS" for c in report.checks)

    det_rows = "".join(
        f"<tr><td>{it.replace('_', ' ').capitalize()}</td><td>{v['ground_truth']}</td><td>{v['detected']}</td>"
        f"<td>{v['false_positive']}</td><td>{v['false_negative']}</td><td>{v['precision']:.3f}</td><td>{v['recall']:.3f}</td></tr>"
        for it, v in ev["per_issue_type"].items())
    guard = ", ".join(f"{k.replace('_', ' ').lower()} {v}" for k, v in ev["guard_rule_findings"].items())

    cats = {}
    for c in report.checks:
        a = cats.setdefault(c["category"], [0, 0, []])
        a[0] += c["status"] == "PASS"
        a[1] += 1
        a[2].append(c)
    val_rows = []
    for cat, (p, n, checks) in cats.items():
        items = "".join(f'<li class="{c["status"].lower()}">{_esc(c["check"])} <span class="muted">'
                        f'({c["records_checked"]:,} records{", " + str(c["failures"]) + " failures" if c["failures"] else ""})</span></li>'
                        for c in checks)
        val_rows.append(f'<details><summary><span class="vcat">{CATEGORY_LABELS.get(cat, cat.replace("_", " ").capitalize())}</span>'
                        f'<span class="{"pass" if p == n else "fail"}">{p} of {n} passed</span></summary><ul>{items}</ul></details>')

    leave = kpis["leave_outcomes"]
    swaps = kpis["swap_outcomes"]
    att = kpis["attendance_outcomes"]
    fair_rows = sorted(derived["fairness_by_team"], key=lambda f: f["gini_utilisation"], reverse=True)[:8]
    fair_html = "".join(f"<tr><td>{f['team_id']}</td><td>{f['rota_members']}</td><td>{f['mean_utilisation']:.2f}</td>"
                        f"<td>{f['gini_utilisation']:.3f}</td><td>{f['night_shifts_std']:.2f}</td>"
                        f"<td>{f['overtime_hours_total']:,.0f}</td></tr>" for f in fair_rows)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Rota health report: {sc['name']} dataset</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{ --paper:#F5F7F6; --panel:#FFFFFF; --ink:#1E2A33; --muted:#5B6873; --rule:#D5DCDF;
  --ok:#CFE3DF; --ok-strong:#3E7C74; --att:#E8A317; --gap:#B5432F; --line:#2F5D8A;
  color-scheme: light; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --paper:#12181D; --panel:#1A2228; --ink:#E4E9EB;
  --muted:#9AA7B0; --rule:#2C3840; --ok:#24403C; --ok-strong:#6FB3A8; --att:#E8A317; --gap:#E06A52; --line:#7FA8D1; color-scheme: dark; }} }}
:root[data-theme="dark"] {{ --paper:#12181D; --panel:#1A2228; --ink:#E4E9EB; --muted:#9AA7B0; --rule:#2C3840; --ok:#24403C;
  --ok-strong:#6FB3A8; --att:#E8A317; --gap:#E06A52; --line:#7FA8D1; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
html {{ background: var(--paper); }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.55 "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  padding: env(safe-area-inset-top,0) 0 env(safe-area-inset-bottom,0); }}
main {{ max-width: 1120px; margin: 0 auto; padding: 40px 24px 80px; }}
h1, h2, .num {{ font-family: "Barlow Semi Condensed", "Arial Narrow", system-ui, sans-serif; letter-spacing: .005em; }}
h1 {{ font-size: clamp(30px, 4.5vw, 46px); line-height: 1.05; margin: 0 0 8px; font-weight: 700; max-width: 20ch; }}
h2 {{ font-size: 26px; margin: 56px 0 6px; font-weight: 600; }}
p {{ max-width: 70ch; margin: 0 0 12px; }}
.lede {{ color: var(--muted); font-size: 18px; }}
.muted {{ color: var(--muted); }}
.board-wrap {{ overflow-x: auto; margin: 28px 0 10px; background: var(--panel); border: 1px solid var(--rule); padding: 14px 10px; }}
svg.board {{ width: 100%; min-width: 640px; height: auto; display:block; }}
svg .ok {{ fill: var(--ok); }} svg .att {{ fill: var(--att); }} svg .gap {{ fill: var(--gap); }}
svg .axis {{ fill: var(--muted); font: 11px "Source Sans 3", system-ui, sans-serif; }}
.legend {{ display:flex; gap: 22px; flex-wrap: wrap; font-size: 14px; color: var(--muted); }}
.legend i {{ display:inline-block; width: 12px; height: 12px; margin-right: 6px; vertical-align: -1px; }}
.stats {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0; margin: 26px 0 0;
  border-top: 2px solid var(--ink); }}
.stat {{ padding: 14px 16px 6px 0; }}
.stat .num {{ font-size: 34px; font-weight: 600; line-height: 1.1; display:block; }}
.stat span:last-child {{ color: var(--muted); font-size: 14px; }}
.table-wrap {{ overflow-x:auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 15px; margin-top: 12px; }}
th, td {{ text-align: right; padding: 8px 10px; border-bottom: 1px solid var(--rule); white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ font-weight: 600; color: var(--muted); }}
.cols {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 32px; }}
.bars {{ margin-top: 10px; }}
.bar-row {{ display:grid; grid-template-columns: 150px 1fr 64px; gap: 10px; align-items:center; margin: 6px 0; font-size: 14px; }}
.bar-track {{ background: var(--rule); height: 10px; }}
.bar {{ display:block; height: 10px; background: var(--ok-strong); }}
.bar.warn {{ background: var(--att); }} .bar.bad {{ background: var(--gap); }} .bar.neutral {{ background: var(--muted); }}
.bar-val {{ text-align:right; font-variant-numeric: tabular-nums; }}
svg.chart {{ width: 100%; max-width: 760px; height:auto; }}
svg .ot-s {{ fill: var(--line); }} svg .ot-a {{ fill: var(--att); }}
details {{ border-bottom: 1px solid var(--rule); padding: 10px 0; }}
summary {{ cursor: pointer; display:flex; justify-content: space-between; gap: 12px; }}
summary:focus-visible {{ outline: 2px solid var(--line); outline-offset: 3px; }}
.vcat {{ font-weight: 600; }}
.pass {{ color: var(--ok-strong); }} .fail {{ color: var(--gap); font-weight:600; }}
details ul {{ margin: 8px 0 0; padding-left: 18px; font-size: 14px; }}
li.fail {{ color: var(--gap); }}
footer {{ margin-top: 64px; color: var(--muted); font-size: 14px; border-top: 1px solid var(--rule); padding-top: 14px; }}
</style></head>
<body><main>
<h1>Rota health for {sc['employees']:,} people across {sc['teams']} teams</h1>
<p class="lede">{sc['days']} days from {sc['start_date']} to {sc['end_date']}, generated with seed {cfg['seed']}.
Each row below is a team and each column a day. Hover a cell to see which shift and skill fell short.</p>
<div class="board-wrap">{_heatmap(derived, t)}</div>
<div class="legend"><span><i style="background:var(--ok)"></i>Every requirement met</span>
<span><i style="background:var(--att)"></i>Scheduled, but someone did not clock in</span>
<span><i style="background:var(--gap)"></i>Schedule itself short</span></div>

<div class="stats">
<div class="stat"><span class="num">{cov['final_schedule'] * 100:.1f}%</span><span>requirements met by the final schedule</span></div>
<div class="stat"><span class="num">{ev['overall']['precision']:.2f} / {ev['overall']['recall']:.2f}</span><span>detector precision / recall on {sum(v['ground_truth'] for v in ev['per_issue_type'].values())} labelled anomalies</span></div>
<div class="stat"><span class="num">{fair['mean_gini_utilisation']}</span><span>mean within-team Gini of utilisation (0 is perfectly even)</span></div>
<div class="stat"><span class="num">{passed}/{len(report.checks)}</span><span>validation checks passed</span></div>
</div>

<h2>Exceptions found versus ground truth</h2>
<p>The detector reads only the exported input tables. Each injected edge case is listed in a separate ground-truth file and
matched on issue type and record ID.</p>
<div class="table-wrap"><table><thead><tr><th>Issue</th><th>Labelled</th><th>Detected</th><th>False +</th><th>False −</th><th>Precision</th><th>Recall</th></tr></thead>
<tbody>{det_rows}</tbody></table></div>
<p class="muted" style="margin-top:12px">Constraints the scheduler must never break, re-checked independently: {guard}.</p>

<h2>Where coverage is lost</h2>
<p>Share of team-shift requirements met at each stage, then the reported gaps by the stage where they arose.
{kpis['planning_gaps_recovered_by_topup']:,} gaps found at publication were later closed by manager top-ups, and
{kpis['cross_team_cover_assignments']:,} active assignments are people lent from a sister team.</p>
<div class="cols"><div>{_bars([("At publication", round(cov['at_publication'] * 100, 1), ""),
                                ("Final schedule", round(cov['final_schedule'] * 100, 1), ""),
                                ("Attended", round(cov['attended'] * 100, 1), "warn")], lambda v: f"{v}%")}</div>
<div>{_bars([("Planning", gaps.get('PLANNING', 0), "bad"), ("After publication", gaps.get('POST_PUBLICATION', 0), "bad"),
            ("Attendance", gaps.get('ATTENDANCE', 0), "warn")])}</div></div>

<h2>Overtime by week</h2>
<p>Blue is overtime planned into the schedule (within each person's cap); amber is overtime that actually happened
because people stayed late. {kpis['employee_weeks_over_cap']} employee-weeks exceed the cap, all of them labelled anomalies.</p>
{_weekly_overtime(derived)}

<h2>Fairness</h2>
<p>Utilisation is scheduled hours divided by contracted hours for the time each person was employed. The teams with the
most uneven spread are listed first. Night shifts are counted per four weeks for night-eligible staff.</p>
<div class="table-wrap"><table><thead><tr><th>Team</th><th>Rota</th><th>Mean utilisation</th><th>Gini</th><th>Night shifts σ</th><th>Overtime h</th></tr></thead>
<tbody>{fair_html}</tbody></table></div>

<h2>Leave, swaps and attendance</h2>
<div class="cols">
<div><p class="muted">Leave requests</p>{_bars([(k.capitalize(), v, "" if k == "APPROVED" else ("bad" if k == "REJECTED" else "neutral")) for k, v in leave.items()])}</div>
<div><p class="muted">Swap requests</p>{_bars([(k.capitalize(), v, "" if k == "APPLIED" else ("bad" if k == "REJECTED" else "neutral")) for k, v in swaps.items()])}</div>
<div><p class="muted">Attended shifts</p>{_bars([(k.replace('_', ' ').capitalize(), v, "" if k == "ON_TIME" else "warn") for k, v in att.items()])}</div>
</div>

<h2>Validation</h2>
<p>Checks run on the exported CSV files, plus a load of the SQL seed into SQLite with foreign keys enforced.</p>
{''.join(val_rows)}
<footer>Generated by fairshift v{cfg['generator_version']}. All data is synthetic. Re-running with the same seed reproduces every file byte for byte.</footer>
</main></body></html>
"""
