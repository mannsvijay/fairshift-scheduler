"""Serialisation. Formats are deterministic (fixed column order, fixed number
formatting, stable row order, LF line endings) so files can be checksummed."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

from .schema import (BOOLEAN, DATE, DATETIME, DECIMAL, INTEGER, TABLE_BY_NAME, TABLE_ORDER, TABLES)


# --------------------------------------------------------------------------- value formatting
def fmt_csv(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, (list, tuple)):
        return "|".join(str(x) for x in v)
    return str(v)


def fmt_json(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, tuple):
        return list(v)
    return v


def fmt_sql(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return fmt_csv(v)
    return "'" + fmt_csv(v).replace("'", "''") + "'"


# --------------------------------------------------------------------------- writers
def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([fmt_csv(r.get(c)) for c in columns])


def write_json(path: Path, columns: list[str], rows: list[dict]) -> None:
    """JSON array with one record per line (diff-friendly, still valid JSON)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("[\n")
        for i, r in enumerate(rows):
            rec = {c: fmt_json(r.get(c)) for c in columns}
            f.write(json.dumps(rec, ensure_ascii=False) + (",\n" if i < len(rows) - 1 else "\n"))
        f.write("]\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def ddl() -> str:
    sql_type = {INTEGER: "INTEGER", BOOLEAN: "INTEGER", DECIMAL: "REAL"}
    out = ["-- Generated from fairshift/schema.py. Portable SQL (tested on SQLite; PostgreSQL-compatible).",
           "-- All foreign keys are DEFERRABLE INITIALLY DEFERRED because team<->employee and",
           "-- shift_assignment<->swap_request reference each other.", ""]
    for t in TABLES:
        lines = []
        for c in t.columns:
            parts = [f"  {c.name} {sql_type.get(c.type, 'TEXT')}"]
            if c.name == t.pk:
                parts.append("PRIMARY KEY")
            elif c.required:
                parts.append("NOT NULL")
            if c.unique and c.name != t.pk:
                parts.append("UNIQUE")
            if c.enum:
                parts.append(f"CHECK ({c.name} IN ({', '.join(repr(e) for e in c.enum)}))")
            if c.type == BOOLEAN:
                parts.append(f"CHECK ({c.name} IN (0, 1))")
            lines.append(" ".join(parts))
        for c in t.columns:
            if c.fk:
                parent, pcol = c.fk.split(".")
                lines.append(f"  FOREIGN KEY ({c.name}) REFERENCES {parent}({pcol}) DEFERRABLE INITIALLY DEFERRED")
        for group in t.unique_together:
            lines.append(f"  UNIQUE ({', '.join(group)})")
        out.append(f"CREATE TABLE {t.name} (\n" + ",\n".join(lines) + "\n);\n")
    out.append("-- Index every foreign-key column: keeps joins fast and lets the database check\n"
               "-- referential integrity without scanning child tables.")
    for t in TABLES:
        for c in t.columns:
            if c.fk:
                out.append(f"CREATE INDEX idx_{t.name}_{c.name} ON {t.name}({c.name});")
    return "\n".join(out) + "\n"


def write_sql_seed(path: Path, tables: dict[str, list[dict]], batch: int = 500) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Seed data. Load after schema.sql. For SQLite run `PRAGMA foreign_keys = ON;` first.\n")
        f.write("BEGIN;\n")
        for name in TABLE_ORDER:
            cols = TABLE_BY_NAME[name].column_names
            rows = tables[name]
            for i in range(0, len(rows), batch):
                chunk = rows[i:i + batch]
                values = ",\n".join("(" + ", ".join(fmt_sql(r.get(c)) for c in cols) + ")" for r in chunk)
                f.write(f"INSERT INTO {name} ({', '.join(cols)}) VALUES\n{values};\n")
        f.write("COMMIT;\n")


# --------------------------------------------------------------------------- loading
def parse_value(raw: str, typ: str):
    if raw == "":
        return None
    if typ == INTEGER:
        return int(raw)
    if typ == DECIMAL:
        return float(raw)
    if typ == BOOLEAN:
        if raw not in ("true", "false"):
            raise ValueError(f"bad boolean {raw!r}")
        return raw == "true"
    if typ == DATE:
        return date.fromisoformat(raw)
    if typ == DATETIME:
        return datetime.fromisoformat(raw)
    return raw


def load_table_csv(path: Path, table_name: str) -> tuple[list[dict], list[str]]:
    """Load one exported table, parsing values by schema type. Returns (rows, parse errors)."""
    t = TABLE_BY_NAME[table_name]
    types = {c.name: c.type for c in t.columns}
    rows, errors = [], []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != t.column_names:
            errors.append(f"{table_name}: header {reader.fieldnames} != schema {t.column_names}")
        for i, raw in enumerate(reader, start=2):
            row = {}
            for c, v in raw.items():
                try:
                    row[c] = parse_value(v, types.get(c, "STRING"))
                except ValueError as exc:
                    errors.append(f"{table_name} line {i} column {c}: {exc}")
                    row[c] = None
            rows.append(row)
    return rows, errors


def load_dataset(csv_dir: Path) -> tuple[dict[str, list[dict]], list[str]]:
    tables, errors = {}, []
    for name in TABLE_ORDER:
        rows, errs = load_table_csv(csv_dir / f"{name}.csv", name)
        tables[name] = rows
        errors += errs
    return tables, errors
