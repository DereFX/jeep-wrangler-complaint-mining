"""Prepare a focused NHTSA complaint cohort from official five-year ZIP files.

Run: python prepare_data.py --source-dir PATH_TO_ZIPS
Requires only the Python standard library.
"""

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path


ZIP_NAMES = (
    "complaints_2020_2024.zip",
    "complaints_2025_2026.zip",
)
SOURCE_URLS = (
    "https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2020-2024.zip",
    "https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2025-2026.zip",
)
FIRST_RECEIVED = date(2020, 1, 1)
LAST_RECEIVED = date(2026, 8, 31)  # Last complete month in the source snapshot.
FIRST_MODEL_YEAR = 2018
LAST_MODEL_YEAR = 2025
MAKE = "JEEP"
MODEL = "WRANGLER"
COMPONENT = "ELECTRICAL SYSTEM"
MIN_NARRATIVE_CHARS = 40

VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)")
SPACE = re.compile(r"\s+")


def normalize_narrative(value: str) -> str:
    value = SPACE.sub(" ", value).strip()
    value = EMAIL.sub("[EMAIL]", value)
    value = PHONE.sub("[PHONE]", value)
    return VIN.sub("[VIN]", value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(source_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    counts = Counter()
    sources = []

    for filename, url in zip(ZIP_NAMES, SOURCE_URLS):
        path = source_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}. Download from {url}")
        sources.append({"file": filename, "url": url, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".txt")]
            if len(members) != 1:
                raise ValueError(f"Expected one text file in {path}, found {members}")
            with archive.open(members[0]) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""), delimiter="\t")
                for row in reader:
                    counts["source_rows"] += 1
                    if len(row) != 51:
                        counts["invalid_field_count"] += 1
                        continue
                    if row[45].strip() != "V" or row[3].strip().upper() != MAKE or row[4].strip().upper() != MODEL:
                        continue
                    counts["matching_vehicle_rows"] += 1
                    if not row[11].strip().upper().startswith(COMPONENT):
                        continue
                    counts["matching_component_rows"] += 1
                    try:
                        received = date.fromisoformat(f"{row[16][:4]}-{row[16][4:6]}-{row[16][6:8]}")
                        model_year = int(row[5])
                    except (ValueError, TypeError):
                        counts["invalid_date_or_model_year"] += 1
                        continue
                    if not FIRST_RECEIVED <= received <= LAST_RECEIVED or not FIRST_MODEL_YEAR <= model_year <= LAST_MODEL_YEAR:
                        counts["outside_scope"] += 1
                        continue
                    counts["in_scope_rows"] += 1
                    narrative = normalize_narrative(row[19])
                    if len(narrative) < MIN_NARRATIVE_CHARS:
                        counts["short_or_empty_narrative"] += 1
                        continue
                    complaint_id = row[1].strip()
                    if not complaint_id:
                        counts["missing_complaint_id"] += 1
                        continue
                    candidate = {
                        "complaint_id": complaint_id,
                        "received_date": received.isoformat(),
                        "model_year": model_year,
                        "component": COMPONENT,
                        "complaint_source_code": row[20].strip(),
                        "narrative": narrative,
                    }
                    if complaint_id in records:
                        counts["duplicate_component_rows"] += 1
                        if len(narrative) <= len(records[complaint_id]["narrative"]):
                            continue
                    records[complaint_id] = candidate

    ordered = sorted(records.values(), key=lambda item: (item["received_date"], item["complaint_id"]))
    fields = ("complaint_id", "received_date", "model_year", "component", "complaint_source_code", "narrative")
    with (output_dir / "complaints.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(ordered)

    month_counts = Counter(record["received_date"][:7] for record in ordered)
    with (output_dir / "monthly_counts.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("received_month", "complaint_count"))
        year, month = FIRST_RECEIVED.year, FIRST_RECEIVED.month
        while (year, month) <= (LAST_RECEIVED.year, LAST_RECEIVED.month):
            key = f"{year:04d}-{month:02d}"
            writer.writerow((key, month_counts[key]))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    counts["output_complaints"] = len(ordered)
    metadata = {
        "cohort": {"make": MAKE, "model": MODEL, "component": COMPONENT,
                   "model_years": [FIRST_MODEL_YEAR, LAST_MODEL_YEAR],
                   "received_dates": [FIRST_RECEIVED.isoformat(), LAST_RECEIVED.isoformat()]},
        "source_files": sources,
        "counts": dict(sorted(counts.items())),
        "monthly_range": [min(month_counts, default=None), max(month_counts, default=None)],
        "fields": list(fields),
        "note": "Narratives are public source text with regex masking of VIN-like strings, email addresses, and phone numbers. Review before public redistribution.",
    }
    (output_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output_dir)["counts"], indent=2))
