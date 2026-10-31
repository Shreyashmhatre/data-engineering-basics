# Design notes

## Why this scope?

A tiny local pipeline makes ETL contracts visible without requiring infrastructure.
The source CSV is immutable input; the normalized SQLite table is the destination.
Validation and database constraints serve different purposes and are both tested.

## Reruns and conflicts

`sale_id` is a source-system identifier, not a generated row number. Exact duplicate
records are skipped; different content under the same identifier is rejected for review.
This is an append-only load, not a general change-data-capture implementation.

`BEGIN IMMEDIATE` protects the compare/insert sequence against concurrent SQLite writers.
An unexpected insert failure rolls back all valid inserts in the current batch. Rejected
source rows do not prevent unrelated valid rows from loading.

## Reporting and failure boundaries

The report has batch-specific `input_rows`, `inserted`, `duplicates`, and `rejected`
counts, plus database-wide row and revenue totals. Counts reconcile to input rows.
The report file is written **after** the database commits. A filesystem failure can
therefore leave a committed load without a new report. Rerunning the input is safe,
but will correctly report the prior rows as duplicates rather than new inserts.

This implementation materializes the small input in memory. It is unsuitable for large
files without bounded streaming batches. There is no scheduler, retry orchestrator,
schema migration system, data lineage catalog, encryption, or event-time watermarking.

## Next experiments

- Add source checksums and a durable run-history table.
- Introduce chunked extraction while preserving a documented transaction boundary.
- Add a PostgreSQL destination and compare transaction behavior.
- Schedule a proven local job only after its failure/retry semantics are understood.
