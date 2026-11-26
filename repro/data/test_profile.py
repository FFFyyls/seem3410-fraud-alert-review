"""Boundary and published-aggregate checks, requiring no network or raw records."""
import csv
import json
import math
import unittest
from pathlib import Path

from build_hourly_profile import EXPECTED_COLUMNS, aggregate_rows, summarize


def row(time, label="0"):
    record = dict.fromkeys(EXPECTED_COLUMNS, "0")
    record["Time"] = str(time)
    record["Class"] = label
    return record


class AggregationTests(unittest.TestCase):
    def test_half_open_hour_and_day_boundaries_and_duplicates(self):
        records = [row(t) for t in [0, 3599, 3600, 3600, 86399, 86400, 172792]]
        profile, controls = aggregate_rows(records, EXPECTED_COLUMNS)
        counts = {(r["day"], r["hour"]): r["count"] for r in profile}
        self.assertEqual(counts[0, 0], 2)
        self.assertEqual(counts[0, 1], 2)
        self.assertEqual(counts[0, 23], 1)
        self.assertEqual(counts[1, 0], 1)
        self.assertEqual(counts[1, 23], 1)
        self.assertEqual(sum(counts.values()), 7)
        self.assertEqual(profile[-1]["exposure_seconds"], 3592)
        self.assertEqual(controls["time_max_seconds"], 172792)

    def test_unordered_rows_still_count_correctly(self):
        a, meta = aggregate_rows([row(86400), row(0), row(172792)], EXPECTED_COLUMNS)
        b, _ = aggregate_rows([row(0), row(86400), row(172792)], EXPECTED_COLUMNS)
        self.assertEqual(a, b)
        self.assertEqual(meta["nonmonotonic_steps"], 1)

    def test_invalid_times_fail(self):
        for t in [-1, 172800, "nan", "inf", 0.5, ""]:
            with self.subTest(time=t), self.assertRaises(ValueError):
                aggregate_rows([row(t)], EXPECTED_COLUMNS)

    def test_invalid_schema_and_class_fail(self):
        with self.assertRaises(ValueError):
            aggregate_rows([row(0)], EXPECTED_COLUMNS[:-1])
        with self.assertRaises(ValueError):
            aggregate_rows([row(0, "2")], EXPECTED_COLUMNS)

    def test_empty_input_fails(self):
        with self.assertRaises(ValueError):
            aggregate_rows([], EXPECTED_COLUMNS)

    def test_published_aggregate_controls(self):
        root = Path(__file__).resolve().parent
        with (root / "hourly_profile.csv").open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, ["day", "hour", "count", "exposure_seconds"])
            profile = [{k: int(v) for k, v in r.items()} for r in reader]
        self.assertEqual([(r["day"], r["hour"]) for r in profile],
                         [(d, h) for d in range(2) for h in range(24)])
        self.assertTrue(all(r["count"] > 0 for r in profile))
        self.assertEqual(sum(r["count"] for r in profile), 284807)
        self.assertEqual([sum(r["count"] for r in profile if r["day"] == d)
                          for d in range(2)], [144786, 140021])
        self.assertEqual([r["exposure_seconds"] for r in profile], [3600] * 47 + [3592])
        stored = json.loads((root / "profile_summary.json").read_text(encoding="utf-8"))
        controls = {k: stored[k] for k in ["rows", "fraud_labels_identity_check_only", "time_min_seconds", "time_max_seconds", "nonmonotonic_steps"]}
        recalculated = summarize(profile, controls)
        self.assertEqual(stored, recalculated)
        self.assertTrue(math.isclose(sum(stored["normalized_hour_weights"]), 1.0, abs_tol=1e-12))
        self.assertEqual(stored["peak_relative_hour"], 21)
        self.assertEqual(stored["trough_relative_hour"], 4)


if __name__ == "__main__":
    unittest.main()
