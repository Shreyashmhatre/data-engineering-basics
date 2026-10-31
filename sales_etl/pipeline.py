import csv
import json
import re
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ["sale_id", "event_date", "product", "quantity", "unit_price"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
    sale_id TEXT PRIMARY KEY,
    event_date TEXT NOT NULL,
    product TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_paise INTEGER NOT NULL CHECK (unit_price_paise > 0)
);
"""


def validate(row: dict) -> tuple:
    if None in row or any(value is None for value in row.values()):
        raise ValueError("row has missing or extra columns")
    sale_id, product = row["sale_id"].strip(), row["product"].strip()
    if not 1 <= len(sale_id) <= 100 or not 1 <= len(product) <= 200:
        raise ValueError("sale_id/product is empty or exceeds the length limit")
    raw_date = row["event_date"].strip()
    try:
        parsed_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ValueError("event_date must be a valid YYYY-MM-DD date") from exc
    if parsed_date.isoformat() != raw_date:
        raise ValueError("event_date must use YYYY-MM-DD")
    raw_quantity = row["quantity"].strip()
    if (
        not re.fullmatch(r"[0-9]{1,7}", raw_quantity)
        or not 1 <= int(raw_quantity) <= 1000000
    ):
        raise ValueError("quantity must be an integer from 1 to 1000000")
    raw_price = row["unit_price"].strip()
    if not re.fullmatch(r"[0-9]{1,7}(\.[0-9]{1,2})?", raw_price):
        raise ValueError(
            "unit_price must be a decimal with at most two fractional digits"
        )
    try:
        price = Decimal(raw_price)
    except InvalidOperation as exc:
        raise ValueError("unit_price must be a decimal") from exc
    if not price.is_finite() or not 0 < price <= 1000000:
        raise ValueError("unit_price must be positive and at most 1000000 INR")
    return sale_id, raw_date, product, int(raw_quantity), int(price * 100)


def read_source(source: Path) -> tuple[list, list, int]:
    accepted, rejected = [], []
    count = 0
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError("CSV header must be exactly: " + ",".join(FIELDS))
        for row_number, row in enumerate(reader, start=2):
            count += 1
            try:
                accepted.append((row_number, validate(row)))
            except ValueError as exc:
                rejected.append({"row": row_number, "reason": str(exc)})
    return accepted, rejected, count


def run_pipeline(source: Path, database: Path, report_path: Path | None = None) -> dict:
    accepted, rejected, input_rows = read_source(source)
    database.parent.mkdir(parents=True, exist_ok=True)
    inserted, duplicates = 0, 0
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(SCHEMA)
        # BEGIN IMMEDIATE serializes writers so conflict checks and inserts are atomic.
        connection.execute("BEGIN IMMEDIATE")
        try:
            for row_number, record in accepted:
                existing = connection.execute(
                    "SELECT sale_id, event_date, product, quantity, unit_price_paise "
                    "FROM sales WHERE sale_id = ?",
                    (record[0],),
                ).fetchone()
                if existing == record:
                    duplicates += 1
                elif existing is not None:
                    rejected.append(
                        {
                            "row": row_number,
                            "reason": "sale_id conflicts with existing data",
                        }
                    )
                else:
                    connection.execute(
                        "INSERT INTO sales VALUES (?, ?, ?, ?, ?)", record
                    )
                    inserted += 1
            rows, revenue = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(quantity * unit_price_paise), 0) FROM sales"
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    report = {
        "input_rows": input_rows,
        "inserted": inserted,
        "duplicates": duplicates,
        "rejected": len(rejected),
        "rejections": sorted(rejected, key=lambda r: r["row"]),
        "database_rows": rows,
        "database_revenue_paise": revenue,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
