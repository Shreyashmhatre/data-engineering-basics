import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sales_etl.pipeline import FIELDS, run_pipeline, validate

ROOT = Path(__file__).resolve().parent.parent


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.db = self.directory / "sales.db"

    def test_sample_and_idempotent_rerun(self):
        source = ROOT / "data/sample_sales.csv"
        report = run_pipeline(source, self.db, self.directory / "report.json")
        self.assertEqual(
            (
                report["input_rows"],
                report["inserted"],
                report["duplicates"],
                report["rejected"],
            ),
            (8, 4, 1, 3),
        )
        self.assertEqual(report["database_revenue_paise"], 585000)
        second = run_pipeline(source, self.db)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["database_rows"], 4)
        self.assertEqual(second["duplicates"], 5)
        self.assertEqual(second["database_revenue_paise"], 585000)

    def test_conflicting_id_is_rejected_not_overwritten(self):
        run_pipeline(ROOT / "data/sample_sales.csv", self.db)
        source = self.directory / "conflict.csv"
        source.write_text(
            "sale_id,event_date,product,quantity,unit_price\n"
            "s001,2026-01-01,Sensor kit,99,1200.00\n"
        )
        result = run_pipeline(source, self.db)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["database_revenue_paise"], 585000)

    def test_bad_header_does_not_create_database(self):
        source = self.directory / "bad.csv"
        source.write_text("wrong,header\na,b\n")
        with self.assertRaises(ValueError):
            run_pipeline(source, self.db)
        self.assertFalse(self.db.exists())

    def test_validation_boundaries_and_exact_money(self):
        base = dict(zip(FIELDS, ["s1", "2026-01-01", "Widget", "2", "0.10"]))
        self.assertEqual(validate(base)[-1], 10)
        for key, value in [
            ("quantity", "0"),
            ("quantity", "2.5"),
            ("unit_price", "NaN"),
            ("unit_price", "1.001"),
            ("event_date", "20260101"),
            ("product", " "),
        ]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate({**base, key: value})

    def test_empty_valid_source(self):
        source = self.directory / "empty.csv"
        with source.open("w", newline="") as handle:
            csv.writer(handle).writerow(FIELDS)
        self.assertEqual(run_pipeline(source, self.db)["database_rows"], 0)

    def test_transaction_rolls_back_on_insert_failure(self):
        run_pipeline(ROOT / "data/sample_sales.csv", self.db)
        connection = sqlite3.connect(self.db)
        connection.execute(
            "CREATE TRIGGER reject_new BEFORE INSERT ON sales "
            "WHEN NEW.sale_id = 'fail' BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
        connection.commit()
        connection.close()
        source = self.directory / "rollback.csv"
        source.write_text(
            "sale_id,event_date,product,quantity,unit_price\n"
            "new,2026-01-01,Widget,1,1.00\nfail,2026-01-01,Widget,1,1.00\n"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            run_pipeline(source, self.db)
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 4
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
