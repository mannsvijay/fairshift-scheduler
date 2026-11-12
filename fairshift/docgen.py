"""Generate docs/DATA_DICTIONARY.md and docs/ERD.md from fairshift/schema.py."""
from __future__ import annotations

from pathlib import Path

from .derive import DERIVED_COLUMNS
from .detect import FINDING_COLUMNS
from .schema import GROUND_TRUTH_COLUMNS, TABLES, relationships


def data_dictionary() -> str:
    L = ["# Data dictionary", "",
         "Generated from `fairshift/schema.py` by `python -m fairshift docs` — do not edit by hand.",
         "The same definitions drive the CSV column order, SQL DDL and the validator, so this document cannot drift from the data.", "",
         "Conventions: timestamps are local site time (Asia/Kolkata, no offset) at second precision; dates are ISO 8601;",
         "booleans are `true`/`false` in CSV and JSON, `1`/`0` in SQL; null is an empty CSV field.", "",
         "| Table | Kind | Primary key | Purpose |", "|---|---|---|---|"]
    for t in TABLES:
        L.append(f"| [`{t.name}`](#{t.name}) | {t.kind} | `{t.pk}` | {t.desc} |")
    for t in TABLES:
        L += ["", f"## {t.name}", "", t.desc, ""]
        L += ["| Column | Type | Req. | Unique | Allowed values / format | Unit | References | Validation rule | Description |",
              "|---|---|---|---|---|---|---|---|---|"]
        for c in t.columns:
            allowed = ", ".join(f"`{e}`" for e in c.enum) if c.enum else (f"`{c.pattern}`" if c.pattern else "")
            rng = []
            if c.min is not None:
                rng.append(f">= {c.min:g}")
            if c.max is not None:
                rng.append(f"<= {c.max:g}")
            rule = "; ".join(x for x in [c.rule or "", ", ".join(rng)] if x)
            pkfk = "PK" if c.name == t.pk else ""
            L.append(f"| `{c.name}` {pkfk} | {c.type} | {'yes' if c.required else 'no'} | {'yes' if c.unique or c.name == t.pk else ''} | "
                     f"{allowed} | {c.unit or ''} | {('`' + c.fk + '`') if c.fk else ''} | {rule} | {c.desc} |")
        for g in t.unique_together:
            L.append(f"\nComposite uniqueness: `({', '.join(g)})`.")
        for n in t.notes:
            L.append(f"\nNote: {n}")
        if t.lifecycle:
            trans = [f"`{a or 'START'}` → `{b}`" for a, bs in t.lifecycle.items() for b in bs]
            L.append("\nAllowed state transitions: " + ", ".join(trans) + ".")
    L += ["", "## Output files that are not input tables", "",
          "**`ground_truth/ground_truth.csv`** (kept outside `data/`, never joined into inputs): " +
          ", ".join(f"`{c}`" for c in GROUND_TRUTH_COLUMNS) + ". `record_id` uses the ID of the record type named in "
          "`record_type`; for `employee_week` it is `EMP-xxxxxx|YYYY-Www`.", "",
          "**`derived/`** — recomputed from the exported CSVs on every run:", ""]
    for name, cols in DERIVED_COLUMNS.items():
        L.append(f"- `{name}.csv`: " + ", ".join(f"`{c}`" for c in cols))
    L.append("- `exceptions.csv`: " + ", ".join(f"`{c}`" for c in FINDING_COLUMNS))
    return "\n".join(L) + "\n"


def erd() -> str:
    L = ["# Entity-relationship diagram", "",
         "Generated from `fairshift/schema.py`. Every relationship is 1:N from parent to child;",
         "`employee_skill` is the bridge table that resolves the N:M between `employee` and `skill`.", "",
         "```mermaid", "erDiagram"]
    for parent, child, col, _card, optional in relationships():
        left = "|o" if optional else "||"
        L.append(f'    {parent} {left}--o{{ {child} : "{col}"')
    for t in TABLES:
        L.append(f"    {t.name} {{")
        for c in t.columns:
            key = " PK" if c.name == t.pk else (" FK" if c.fk else "")
            L.append(f"        {c.type.lower()} {c.name}{key}")
        L.append("    }")
    L += ["```", "", "## Relationship list", "", "| Parent | Child | Foreign key | Cardinality | Optional |", "|---|---|---|---|---|"]
    for parent, child, col, card, optional in relationships():
        L.append(f"| {parent} | {child} | `{col}` | {card} | {'yes' if optional else 'no'} |")
    L += ["", "Many-to-many: `employee` N:M `skill` through `employee_skill` (effective-dated rows; a renewed "
          "certification is a new row).", "",
          "Circular references (`team.manager_employee_id` ↔ `employee.team_id`, `shift_assignment.swap_id` ↔ "
          "`swap_request.requester_assignment_id`) are why all FKs are declared `DEFERRABLE INITIALLY DEFERRED`."]
    return "\n".join(L) + "\n"


def write_docs(docs_dir: Path) -> list[Path]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name, text in (("DATA_DICTIONARY.md", data_dictionary()), ("ERD.md", erd())):
        p = docs_dir / name
        p.write_text(text, encoding="utf-8", newline="\n")
        out.append(p)
    return out
