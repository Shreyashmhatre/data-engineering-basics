import argparse
import json
import sqlite3
from pathlib import Path

from sales_etl.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Validate a sales CSV and load SQLite")
    parser.add_argument("--input", type=Path, default=Path("data/sample_sales.csv"))
    parser.add_argument("--database", type=Path, default=Path("output/sales.db"))
    parser.add_argument("--report", type=Path, default=Path("output/run_report.json"))
    args = parser.parse_args()
    paths = [p.resolve() for p in [args.input, args.database, args.report]]
    if len(set(paths)) != 3:
        parser.error("input, database, and report must be different files")
    try:
        result = run_pipeline(args.input, args.database, args.report)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Pipeline failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
