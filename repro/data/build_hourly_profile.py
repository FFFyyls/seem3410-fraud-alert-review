"""Reproduce a public transaction-time aggregate; never retain raw transactions.

Python standard library only. Source: the ULB/Worldline dataset, mirrored by
TensorFlow's official imbalanced-classification tutorial. No model is trained.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import zipfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

SOURCE_URL = "https://storage.googleapis.com/download.tensorflow.org/data/creditcard.csv"
KAGGLE_METADATA_URL = "https://www.kaggle.com/api/v1/datasets/view/mlg-ulb/creditcardfraud"
OPENML_METADATA_URL = "https://www.openml.org/api/v1/json/data/1597"
EXPECTED_COLUMNS = ["Time", *[f"V{i}" for i in range(1, 29)], "Amount", "Class"]


def aggregate_rows(rows, fieldnames):
    if list(fieldnames) != EXPECTED_COLUMNS:
        raise ValueError("Unexpected source schema: expected Time,V1..V28,Amount,Class")
    counts = [[0] * 24 for _ in range(2)]
    n = fraud = 0
    earliest = math.inf
    latest = -math.inf
    nonmonotonic_steps = 0
    previous = -math.inf
    for row in rows:
        if None in row or any(row[k] is None for k in EXPECTED_COLUMNS):
            raise ValueError(f"Malformed CSV row {n + 2}")
        t = float(row["Time"])
        if not math.isfinite(t) or not t.is_integer() or not 0 <= t < 172800:
            raise ValueError(f"Invalid relative Time at row {n + 2}: {row['Time']}")
        label = row["Class"]
        if label not in ("0", "1"):
            raise ValueError(f"Unexpected Class at row {n + 2}: {label}")
        counts[int(t // 86400)][int(t // 3600) % 24] += 1
        n += 1
        fraud += int(label)
        earliest = min(earliest, t)
        latest = max(latest, t)
        nonmonotonic_steps += t < previous
        previous = t
    if not n:
        raise ValueError("No source records")
    profile = []
    for day in range(2):
        for hour in range(24):
            start = day * 86400 + hour * 3600
            exposure = max(0.0, min(start + 3600, latest) - max(start, earliest))
            profile.append({"day": day, "hour": hour, "count": counts[day][hour],
                            "exposure_seconds": int(exposure)})
    return profile, {"rows": n, "fraud_labels_identity_check_only": fraud,
                     "time_min_seconds": earliest, "time_max_seconds": latest,
                     "nonmonotonic_steps": nonmonotonic_steps}


def summarize(profile, controls):
    pooled_counts = [sum(r["count"] for r in profile if r["hour"] == h) for h in range(24)]
    exposures = [sum(r["exposure_seconds"] for r in profile if r["hour"] == h) for h in range(24)]
    if any(e <= 0 for e in exposures):
        raise ValueError("A relative hour has no observed exposure")
    rates = [c * 3600 / e for c, e in zip(pooled_counts, exposures)]
    weights = [r / sum(rates) for r in rates]
    peak = max(range(24), key=lambda h: rates[h])
    trough = min(range(24), key=lambda h: rates[h])
    top6 = sorted(range(24), key=lambda h: (-rates[h], h))[:6]
    raw_weights = [c / controls["rows"] for c in pooled_counts]
    return {
        **controls,
        "day_counts": [sum(r["count"] for r in profile if r["day"] == d) for d in range(2)],
        "observed_extent_seconds": controls["time_max_seconds"] - controls["time_min_seconds"],
        "nominal_two_day_seconds": 172800,
        "trailing_seconds_without_observed_record": 172800 - controls["time_max_seconds"],
        "exposure_convention": "Observed extent [min(Time), max(Time)]; last event included. Last event time is not a known collection cutoff.",
        "pooled_hour_counts": pooled_counts,
        "pooled_hour_exposure_seconds": exposures,
        "pooled_hour_rates_per_hour": rates,
        "normalized_hour_weights": weights,
        "peak_relative_hour": peak,
        "trough_relative_hour": trough,
        "peak_to_trough_rate_ratio": rates[peak] / rates[trough],
        "top6_relative_hours": top6,
        "top6_hour_share": sum(weights[h] for h in top6),
        "max_weight_difference_due_to_endpoint_adjustment": max(abs(a-b) for a,b in zip(weights,raw_weights)),
        "total_variation_due_to_endpoint_adjustment": sum(abs(a-b) for a,b in zip(weights,raw_weights))/2,
        "proposed_use": "Shape-only scenario; choose alert volume separately, e.g. lambda_h=540*normalized_hour_weights[h].",
        "not_identified": ["local clock origin", "alert creation", "review starts or completions", "risk tiers", "human service requirements", "staffing"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Optional original local ZIP or CSV; otherwise stream the official mirror")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    retrieved = datetime.now(timezone.utc).isoformat()
    if args.input:
        with ExitStack() as stack:
            if zipfile.is_zipfile(args.input):
                archive = stack.enter_context(zipfile.ZipFile(args.input))
                names = [n for n in archive.namelist() if n.split("/")[-1] == "creditcard.csv"]
                if len(names) != 1:
                    raise ValueError("Expected exactly one creditcard.csv inside source ZIP")
                f = stack.enter_context(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8-sig", newline=""))
            else:
                f = stack.enter_context(args.input.open(encoding="utf-8-sig", newline=""))
            reader = csv.DictReader(f)
            profile, controls = aggregate_rows(reader, reader.fieldnames)
    else:
        with urlopen(SOURCE_URL, timeout=120) as response:
            with io.TextIOWrapper(response, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                profile, controls = aggregate_rows(reader, reader.fieldnames)
    if (controls["rows"], controls["fraud_labels_identity_check_only"], controls["time_min_seconds"]) != (284807, 492, 0.0):
        raise ValueError(f"Source controls differ from published dataset: {controls}")
    summary = summarize(profile, controls)
    metadata = {
        "aggregation_started_at_utc": retrieved,
        "metadata_checked_on": "2026-11-24",
        "download_url": SOURCE_URL,
        "alternative_original_download_url": "https://api.kaggle.com/v1/datasets/download/mlg-ulb/creditcardfraud?datasetVersionNumber=3",
        "read_method": "Read original user-workspace ZIP/CSV" if args.input else "Streamed official mirror directly into CSV parser",
        "raw_records_written_by_this_script": False,
        "local_input_used": bool(args.input),
        "tutorial": "https://www.tensorflow.org/tutorials/structured_data/imbalanced_data",
        "original_dataset": "https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud",
        "kaggle_metadata_url": KAGGLE_METADATA_URL,
        "kaggle_metadata": {"ref": "mlg-ulb/creditcardfraud", "title": "Credit Card Fraud Detection", "licenseName": "Database: Open Database, Contents: Database Contents"},
        "openml_metadata_url": OPENML_METADATA_URL,
        "openml_metadata": {"id": "1597", "name": "creditcard", "version": "1", "creator": ["Andrea Dal Pozzolo", "Olivier Caelen", "Gianluca Bontempi"], "upload_date": "2015-06-25T16:52:17", "licence": "Public"},
        "licence_interpretation": "Use the original publisher's specific ODbL/DbCL terms, not OpenML's coarse Public label as a public-domain grant.",
        "fields_used": {"Time": "Relative seconds since first transaction; sole input to profile", "Class": "Only checks 492 fraud labels to confirm source identity; not used to select rows"},
        "aggregation": "day=floor(Time/86400); hour=floor(Time/3600)%24; retain all transactions, including repeated timestamps",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "hourly_profile.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["day", "hour", "count", "exposure_seconds"])
        writer.writeheader()
        writer.writerows(profile)
    for filename, content in (("profile_summary.json", summary), ("source_metadata.json", metadata)):
        (args.out / filename).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
