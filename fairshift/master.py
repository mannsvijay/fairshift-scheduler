"""Master (parent) data: teams, skills, employees, skill holdings, shift templates,
holiday calendar, dated shifts and coverage requirements.

Generated first; every later table references these IDs. Also builds the
in-memory `Context` (lookups and indexes) used by the scheduling engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .config import Policy, Scale
from .core import (at, daterange, employee_id, iso_week_label, rng_for, shift_id, skill_id,
                   team_id, week_monday)
from .schema import DEPARTMENTS, REGIONS

# --------------------------------------------------------------------------- reference data
# Skill catalogue: code, name, category, certification validity in days (None = no expiry)
SKILLS = [
    ("FIRST_AID", "First Aid Responder", "SAFETY", 365),
    ("FORKLIFT", "Forklift Operation", "OPERATIONAL", 730),
    ("RECEIVING", "Receiving & Put-away", "OPERATIONAL", None),
    ("HAZMAT", "Hazardous Goods Handling", "SAFETY", 365),
    ("PICK_PACK", "Picking & Packing", "OPERATIONAL", None),
    ("DISPATCH", "Dispatch Coordination", "OPERATIONAL", None),
    ("CYCLE_COUNT", "Cycle Counting", "OPERATIONAL", None),
    ("WMS", "Warehouse Management System", "SYSTEMS", None),
    ("QUALITY", "Quality Inspection", "OPERATIONAL", None),
    ("RETURNS_GRADING", "Returns Grading", "OPERATIONAL", None),
    ("ESCALATIONS", "Customer Escalations", "CUSTOMER", None),
    ("MULTILINGUAL", "Multilingual Support", "CUSTOMER", None),
    ("TECH_TIER2", "Tier-2 Technical Support", "SYSTEMS", None),
]

# Department -> (core skill, secondary skill, specialist skill)
DEPARTMENT_SKILLS = {
    "INBOUND": ("RECEIVING", "FORKLIFT", "HAZMAT"),
    "OUTBOUND": ("PICK_PACK", "FORKLIFT", "DISPATCH"),
    "INVENTORY": ("CYCLE_COUNT", "WMS", "QUALITY"),
    "RETURNS": ("RETURNS_GRADING", "QUALITY", "WMS"),
    "CUSTOMER_SUPPORT": ("ESCALATIONS", "MULTILINGUAL", "TECH_TIER2"),
}

REGION_CITY = {"IN-RJ": "Jaipur", "IN-MH": "Pune", "IN-KA": "Bengaluru", "IN-TG": "Hyderabad", "IN-DL": "Delhi"}

TEMPLATES = [  # code, name, start, duration, is_night
    ("A", "Early", time(6, 0), 8.0, False),
    ("B", "Late", time(14, 0), 8.0, False),
    ("C", "Night", time(22, 0), 8.0, True),
]

# Synthetic holiday calendar modelled on Indian public-holiday patterns.
# Lunar festivals are flagged APPROXIMATE: confirm against the official notification before real use.
HOLIDAYS = [
    ("2026-01-14", "Makar Sankranti", "REGIONAL", "IN-RJ", "EXACT"),
    ("2026-01-14", "Makar Sankranti", "REGIONAL", "IN-KA", "EXACT"),
    ("2026-01-26", "Republic Day", "NATIONAL", None, "EXACT"),
    ("2026-02-15", "Maha Shivaratri", "REGIONAL", "IN-KA", "APPROXIMATE"),
    ("2026-02-15", "Maha Shivaratri", "REGIONAL", "IN-TG", "APPROXIMATE"),
    ("2026-02-19", "Chhatrapati Shivaji Maharaj Jayanti", "REGIONAL", "IN-MH", "EXACT"),
    ("2026-03-04", "Holi", "NATIONAL", None, "APPROXIMATE"),
    ("2026-03-19", "Gudi Padwa", "REGIONAL", "IN-MH", "APPROXIMATE"),
    ("2026-03-19", "Ugadi", "REGIONAL", "IN-KA", "APPROXIMATE"),
    ("2026-03-19", "Ugadi", "REGIONAL", "IN-TG", "APPROXIMATE"),
    ("2026-03-20", "Id-ul-Fitr", "NATIONAL", None, "APPROXIMATE"),
]

# Author-curated lists of common given/family names. Combinations are random;
# no real person's record is used.
FIRST_NAMES = ["Aarav", "Aditi", "Akash", "Ananya", "Arjun", "Diya", "Farhan", "Gauri", "Harsh", "Ishita",
               "Jaya", "Kabir", "Kavya", "Lakshmi", "Manav", "Meera", "Nikhil", "Nisha", "Omkar", "Pooja",
               "Pranav", "Priya", "Rahul", "Riya", "Rohan", "Sanya", "Siddharth", "Sneha", "Tanvi", "Uday",
               "Varun", "Vidya", "Yash", "Zoya", "Aman", "Bhavna", "Chirag", "Deepa", "Eshan", "Fatima",
               "Gaurav", "Heena", "Imran", "Jasleen", "Karan", "Lavanya", "Mohit", "Neha", "Parth", "Ruchi",
               "Sahil", "Tara", "Vikram", "Anjali", "Dev", "Kiran", "Naveen", "Rekha", "Suresh", "Asha"]
LAST_NAMES = ["Sharma", "Verma", "Gupta", "Mehta", "Iyer", "Nair", "Reddy", "Rao", "Patel", "Shah",
              "Singh", "Kaur", "Khan", "Joshi", "Kulkarni", "Desai", "Menon", "Pillai", "Das", "Bose",
              "Chopra", "Malhotra", "Agarwal", "Jain", "Saxena", "Mishra", "Pandey", "Yadav", "Chauhan", "Rathore",
              "Shekhawat", "Naidu", "Hegde", "Gowda", "Fernandes", "DSouza", "Banerjee", "Mukherjee", "Ali", "Qureshi"]


# --------------------------------------------------------------------------- runtime objects
@dataclass
class Emp:
    id: str
    team: str
    role: str
    contract: float
    max_hours: float
    night_ok: bool
    hire: date
    term: date | None
    part_time: bool

    @property
    def rota(self) -> bool:
        return self.role != "MANAGER"

    def employed_on(self, d: date) -> bool:
        return self.hire <= d and (self.term is None or d <= self.term)


@dataclass
class Shift:
    id: str
    date: date
    code: str
    template_id: str
    start: datetime
    end: datetime
    hours: float
    is_night: bool
    is_weekend: bool
    week: str
    publish_ts: datetime


@dataclass
class Context:
    scale: Scale
    policy: Policy
    seed: int
    tables: dict = field(default_factory=dict)
    emp: dict = field(default_factory=dict)            # id -> Emp
    team: dict = field(default_factory=dict)           # id -> team row
    rota: dict = field(default_factory=dict)           # team id -> [emp ids]
    sisters: dict = field(default_factory=dict)        # team id -> [team ids]
    skill_code_to_id: dict = field(default_factory=dict)
    holdings: dict = field(default_factory=dict)       # emp id -> skill id -> [(from, to)]
    shifts: dict = field(default_factory=dict)         # shift id -> Shift
    shifts_by_date: dict = field(default_factory=dict) # date -> [Shift] (A, B, C)
    holiday_dates: dict = field(default_factory=dict)  # region -> set(date)
    req_index: dict = field(default_factory=dict)      # (team, template, day_type) -> [rows]
    skill_scarcity: dict = field(default_factory=dict) # team -> skill -> holder count
    scarce_count: dict = field(default_factory=dict)   # emp -> number of team-required skills held

    # ---- lookups
    def has_skill(self, emp_id: str, sid: str, d: date) -> bool:
        for f, t in self.holdings.get(emp_id, {}).get(sid, ()):
            if f <= d and (t is None or d <= t):
                return True
        return False

    def day_type(self, team_id_: str, d: date) -> str:
        region = self.team[team_id_]["region_code"]
        if d in self.holiday_dates.get(region, ()) or d in self.holiday_dates.get("*", ()):
            return "HOLIDAY"
        return "WEEKEND" if d.weekday() >= 5 else "WEEKDAY"

    def is_holiday_for_emp(self, emp_id: str, d: date) -> bool:
        return self.day_type(self.emp[emp_id].team, d) == "HOLIDAY"

    def requirements(self, team_id_: str, shift: Shift) -> tuple[int, dict]:
        """Effective (total headcount, {skill_id: min holders}) for a team on a shift."""
        rows = self.req_index.get((team_id_, shift.template_id, self.day_type(team_id_, shift.date)), ())
        total, skills = 0, {}
        for r in rows:
            if r["effective_from"] <= shift.date and (r["effective_to"] is None or shift.date <= r["effective_to"]):
                if r["skill_id"] is None:
                    total = r["min_headcount"]
                else:
                    skills[r["skill_id"]] = r["min_headcount"]
        return total, skills


# --------------------------------------------------------------------------- generation
def _allocate_team_sizes(rng, employees: int, teams: int) -> list[int]:
    weights = [rng.uniform(0.7, 1.3) for _ in range(teams)]
    total_w = sum(weights)
    raw = [employees * w / total_w for w in weights]
    sizes = [max(10, int(x)) for x in raw]
    # largest-remainder adjustment to hit the exact total
    diff = employees - sum(sizes)
    order = sorted(range(teams), key=lambda i: (raw[i] - int(raw[i]), -i), reverse=True)
    i = 0
    while diff != 0:
        idx = order[i % teams]
        if diff > 0:
            sizes[idx] += 1
            diff -= 1
        elif sizes[idx] > 10:
            sizes[idx] -= 1
            diff += 1
        i += 1
    return sizes


def build_master(scale: Scale, policy: Policy, seed: int) -> Context:
    ctx = Context(scale=scale, policy=policy, seed=seed)
    start, end = scale.start_date, scale.end_date

    # ---- skills
    skill_rows = []
    for i, (code, name, cat, validity) in enumerate(SKILLS, start=1):
        sid = skill_id(i)
        ctx.skill_code_to_id[code] = sid
        skill_rows.append({"skill_id": sid, "skill_code": code, "skill_name": name, "category": cat,
                           "requires_certification": validity is not None,
                           "certification_validity_days": validity})
    validity_by_id = {r["skill_id"]: r["certification_validity_days"] for r in skill_rows}

    # ---- teams (department cycles every 2 teams, region every 10 -> sister teams come in pairs+)
    rng = rng_for(seed, "teams")
    team_rows = []
    for i in range(scale.teams):
        dept = DEPARTMENTS[(i // 2) % len(DEPARTMENTS)]
        region = REGIONS[(i // 10) % len(REGIONS)]
        tid = team_id(i + 1)
        team_rows.append({"team_id": tid,
                          "team_name": f"{dept.replace('_', ' ').title()} {REGION_CITY[region]} {i + 1:03d}",
                          "department": dept, "region_code": region, "manager_employee_id": None,
                          "created_date": date(2015, 1, 1) + timedelta(days=rng.randint(0, 2900))})
    for r in team_rows:
        ctx.team[r["team_id"]] = r
    for r in team_rows:
        ctx.sisters[r["team_id"]] = [o["team_id"] for o in team_rows if o["team_id"] != r["team_id"]
                                     and o["department"] == r["department"] and o["region_code"] == r["region_code"]]

    # ---- employees
    rng = rng_for(seed, "employees")
    sizes = _allocate_team_sizes(rng, scale.employees, scale.teams)
    drafts = []
    for t, size in zip(team_rows, sizes):
        for k in range(size):
            if k == 0:
                role = "MANAGER"
            elif k <= 2:
                role = "SHIFT_LEAD"
            else:
                role = "SENIOR_ASSOCIATE" if rng.random() < 0.25 else "ASSOCIATE"
            part_time = role in ("ASSOCIATE", "SENIOR_ASSOCIATE") and rng.random() < policy.part_time_share / 0.85
            if role == "MANAGER":
                hire = date(2015, 1, 1) + timedelta(days=rng.randint(0, 3000))
            elif rng.random() < 0.03:  # joins during the window
                hire = start + timedelta(days=rng.randint(7, max(8, scale.days - 14)))
            else:  # skewed toward recent hires
                span = (start - timedelta(days=30) - date(2016, 1, 1)).days
                hire = date(2016, 1, 1) + timedelta(days=int(span * rng.betavariate(2.2, 1.0)))
            term = None
            if role != "MANAGER" and hire < start and rng.random() < 0.02:
                term = start + timedelta(days=rng.randint(14, scale.days - 7))
            drafts.append({"team_id": t["team_id"], "role": role, "part_time": part_time, "hire": hire,
                           "term": term, "k": k,
                           "first": rng.choice(FIRST_NAMES), "last": rng.choice(LAST_NAMES),
                           "night_ok": role == "MANAGER" or rng.random() >= policy.night_ineligible_share,
                           "balance": round(rng.uniform(4, 24) * 2) / 2})
    drafts.sort(key=lambda x: (x["hire"], x["team_id"], x["k"]))  # employee numbers follow hire order
    emp_rows = []
    for n, dft in enumerate(drafts, start=1):
        eid = employee_id(n)
        pt = dft["part_time"]
        contract = policy.pt_contract_hours if pt else policy.ft_contract_hours
        cap = policy.pt_max_hours if pt else policy.ft_max_hours
        balance = round(dft["balance"] * (0.6 if pt else 1.0) * 2) / 2
        row = {"employee_id": eid, "first_name": dft["first"], "last_name": dft["last"],
               "email": f"{dft['first'].lower()}.{dft['last'].lower()}.{n:06d}@example.com",
               "team_id": dft["team_id"], "role": dft["role"],
               "employment_type": "PART_TIME" if pt else "FULL_TIME",
               "contracted_weekly_hours": contract, "max_weekly_hours": cap,
               "night_shift_eligible": dft["night_ok"], "hire_date": dft["hire"],
               "termination_date": dft["term"],
               "employment_status": "TERMINATED" if dft["term"] and dft["term"] <= end else "ACTIVE",
               "annual_leave_opening_balance_days": balance}
        emp_rows.append(row)
        ctx.emp[eid] = Emp(eid, dft["team_id"], dft["role"], contract, cap, dft["night_ok"],
                           dft["hire"], dft["term"], pt)
        if dft["role"] == "MANAGER":
            ctx.team[dft["team_id"]]["manager_employee_id"] = eid
    for t in team_rows:
        ctx.rota[t["team_id"]] = [e["employee_id"] for e in emp_rows
                                  if e["team_id"] == t["team_id"] and e["role"] != "MANAGER"]

    # ---- skill holdings (bridge table, effective dated)
    rng = rng_for(seed, "skills")
    holdings: dict[str, dict[str, list]] = {}
    plan: list[tuple[str, str]] = []  # (emp, skill) pairs to create
    for t in team_rows:
        core, second, spec = DEPARTMENT_SKILLS[t["department"]]
        members = ctx.rota[t["team_id"]]
        probs = {"FIRST_AID": 0.35, core: 0.7, second: 0.45, spec: 0.3}
        minimum = {"FIRST_AID": max(6, math.ceil(0.32 * len(members))), core: math.ceil(0.55 * len(members)),
                   spec: max(5, math.ceil(0.25 * len(members)))}
        chosen = {c: [m for m in members if rng.random() < p] for c, p in probs.items()}
        for c, need in minimum.items():
            pool = [m for m in members if m not in chosen[c]]
            rng.shuffle(pool)
            while len(chosen[c]) < need and pool:
                chosen[c].append(pool.pop())
        for c in probs:
            for m in chosen[c]:
                plan.append((m, c))
        for m in members:  # occasional cross-skill from other departments
            if rng.random() < 0.08:
                other = rng.choice([s[0] for s in SKILLS if s[0] not in probs])
                plan.append((m, other))
    plan = sorted(set(plan))
    es_rows = []

    def add_holding(m, sid, f, t_, prof):
        es_rows.append({"employee_skill_id": f"ESK-{len(es_rows) + 1:07d}", "employee_id": m, "skill_id": sid,
                        "proficiency_level": prof, "valid_from": f, "valid_to": t_})
        holdings.setdefault(m, {}).setdefault(sid, []).append((f, t_))

    for m, code in plan:
        sid = ctx.skill_code_to_id[code]
        validity = validity_by_id[sid]
        prof = rng.choices([1, 2, 3], weights=[0.35, 0.45, 0.2])[0]
        hire = ctx.emp[m].hire
        if validity is None:
            add_holding(m, sid, hire, None, prof)
            continue
        f = start - timedelta(days=rng.randint(0, validity - 1))
        f = max(f, hire)
        t_ = f + timedelta(days=validity - 1)
        add_holding(m, sid, f, t_, prof)
        if t_ <= end:
            # certification expires inside the window: usually renewed, sometimes after a lapse
            if rng.random() < 0.8:
                gap = 0 if rng.random() < 0.6 else rng.randint(1, 10)
                nf = t_ + timedelta(days=1 + gap)
                add_holding(m, sid, nf, nf + timedelta(days=validity - 1), prof)
    ctx.holdings = holdings

    # ---- shift templates
    tpl_rows = []
    for code, name, st, dur, night in TEMPLATES:
        end_t = (datetime.combine(date(2000, 1, 1), st) + timedelta(hours=dur)).time()
        tpl_rows.append({"template_id": f"TPL-{code}", "template_code": code, "template_name": name,
                         "start_time": st.strftime("%H:%M"), "end_time": end_t.strftime("%H:%M"),
                         "duration_hours": dur, "crosses_midnight": end_t <= st, "is_night": night})

    # ---- holiday calendar
    hol_rows = []
    for i, (ds, name, scope, region, precision) in enumerate(HOLIDAYS, start=1):
        d = date.fromisoformat(ds)
        hol_rows.append({"holiday_id": f"HOL-{d.year}-{i:03d}", "calendar_id": f"CAL-IN-{d.year}",
                         "holiday_date": d, "holiday_name": name, "scope": scope, "region_code": region,
                         "date_precision": precision})
        ctx.holiday_dates.setdefault(region or "*", set()).add(d)

    # ---- dated shifts
    shift_rows = []
    for d in daterange(start, end):
        day_shifts = []
        for code, name, st, dur, night in TEMPLATES:
            s_dt = datetime.combine(d, st)
            pub = at(week_monday(d) - timedelta(days=policy.publication_lead_days), 12)
            sh = Shift(shift_id(d, code), d, code, f"TPL-{code}", s_dt, s_dt + timedelta(hours=dur), dur,
                       night, d.weekday() >= 5, iso_week_label(d), pub)
            ctx.shifts[sh.id] = sh
            day_shifts.append(sh)
            shift_rows.append({"shift_id": sh.id, "shift_date": d, "template_id": sh.template_id,
                               "start_datetime": sh.start, "end_datetime": sh.end, "iso_week": sh.week,
                               "is_weekend": sh.is_weekend, "publication_datetime": pub})
        ctx.shifts_by_date[d] = day_shifts

    # ---- coverage requirements (effective dated; peak-season uplift for some departments)
    uplift_from = policy.peak_uplift_from(scale)
    cov_rows = []

    def add_req(tid, tpl, dtype, sid, n, f, t_):
        row = {"coverage_requirement_id": f"COV-{len(cov_rows) + 1:06d}", "team_id": tid, "template_id": tpl,
               "day_type": dtype, "skill_id": sid, "min_headcount": n, "effective_from": f, "effective_to": t_}
        cov_rows.append(row)
        ctx.req_index.setdefault((tid, tpl, dtype), []).append(row)

    for t in team_rows:
        tid = t["team_id"]
        n = len(ctx.rota[tid])
        core, _second, spec = (ctx.skill_code_to_id[c] for c in DEPARTMENT_SKILLS[t["department"]])
        uplift = t["department"] in policy.peak_uplift_departments and uplift_from <= end
        for dtype, ratios in policy.staffing_ratio.items():
            for code in ("A", "B", "C"):
                tpl = f"TPL-{code}"
                total = max(policy.min_total_headcount, round(n * ratios[code]))
                bump = uplift and dtype == "WEEKDAY" and code in ("A", "B")
                versions = [(start, uplift_from - timedelta(days=1), total), (uplift_from, None, total + policy.peak_uplift_headcount)] \
                    if bump else [(start, None, total)]
                for f, t_, tot in versions:
                    add_req(tid, tpl, dtype, None, tot, f, t_)
                    add_req(tid, tpl, dtype, ctx.skill_code_to_id["FIRST_AID"], 1, f, t_)
                    add_req(tid, tpl, dtype, core, max(1, round(tot * policy.core_skill_share)), f, t_)
                    if dtype == "WEEKDAY" and code in ("A", "B"):
                        add_req(tid, tpl, dtype, spec, 1, f, t_)

    # ---- scarcity: how many holders each required skill has per team (used for fill order)
    for t in team_rows:
        tid = t["team_id"]
        req_skills = sorted({r["skill_id"] for r in cov_rows if r["team_id"] == tid and r["skill_id"]})
        ctx.skill_scarcity[tid] = {s: sum(1 for m in ctx.rota[tid] if s in holdings.get(m, {})) for s in req_skills}
        for m in ctx.rota[tid]:
            ctx.scarce_count[m] = sum(1 for s in req_skills if s in holdings.get(m, {}))

    ctx.tables = {"team": team_rows, "skill": skill_rows, "employee": emp_rows, "employee_skill": es_rows,
                  "shift_template": tpl_rows, "holiday_calendar": hol_rows, "shift": shift_rows,
                  "coverage_requirement": cov_rows}
    return ctx
