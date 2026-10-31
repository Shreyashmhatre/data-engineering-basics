# Data Engineering Basics

A small **CSV → validation → SQLite** batch pipeline for learning ETL fundamentals.
It rejects malformed records, loads valid sales transactionally, detects duplicate
identifiers, and produces a machine-readable run report.

## Run

Python 3.12+; standard library only.

```bash
python -m sales_etl --input data/sample_sales.csv
python -m sales_etl --input data/sample_sales.csv  # safe to rerun
python -m unittest discover -s tests -v
```

Default outputs (ignored by Git): `output/sales.db` and `output/run_report.json`.
The first run on a fresh database inserts **4** rows, skips **1** exact duplicate,
and rejects **3** invalid rows. Revenue is **585,000 paise (₹5,850)**. An unchanged
second run inserts zero rows and leaves the total unchanged.

```text
CSV source → validate each record → compare sale IDs → SQLite transaction
                    ↓                       ↓                 ↓
              rejection reasons       duplicate counts    revenue summary
                    └───────────────────────┴─────────────────┘
                                      run_report.json
```

## Validation and load contract

| Field | Rule |
| --- | --- |
| `sale_id` | Nonempty, at most 100 characters; unique logical sale ID |
| `event_date` | Exact ISO date: `YYYY-MM-DD` |
| `product` | Nonempty, at most 200 characters; surrounding whitespace removed |
| `quantity` | Integer from 1 to 1,000,000 |
| `unit_price` | Positive INR decimal, at most two fractional digits and ₹1,000,000 |

- Money is parsed with `Decimal`, then stored as integer paise.
- The CSV header must match the documented schema; missing/extra columns fail early.
- An existing ID with identical normalized data is a duplicate, not a new sale.
- An existing ID with different data is rejected as a conflict; it is **not overwritten**.
- Valid inserts are committed together. SQLite constraints provide a second layer of checks.
- Rejections include row numbers and reasons, not raw source rows.
- The run report distinguishes this batch's counts from database-wide totals.

See [`docs/design.md`](docs/design.md) for failure semantics and extension ideas.
The tiny sample dataset is fictional and intentionally dirty.

## What this demonstrates

Schema validation, reproducible fixtures, explicit error handling, parameterized SQL,
idempotent batch loading, transactional writes, and tests for reruns and conflicts.

It does **not** demonstrate distributed processing, streaming, orchestration, or production
scale. Spark, Airflow, and cloud storage are future learning topics, not dependencies
or completed capabilities in this repository.
