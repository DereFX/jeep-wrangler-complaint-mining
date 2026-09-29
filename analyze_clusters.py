"""Produce reproducible checks for the largest monthly complaint spike.

Run: python analyze_clusters.py
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UPDATE_WORDS = re.compile(r"\b(?:update|updates|updated|updating|ota|uconnect)\b|over.the.air", re.I)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


if __name__ == "__main__":
    complaints = {row["complaint_id"]: row for row in read_csv(DATA / "complaints.csv")}
    assignments = read_csv(DATA / "cluster_assignments.csv")
    monthly = read_csv(DATA / "monthly_counts.csv")
    peak = max(monthly, key=lambda row: int(row["complaint_count"]))
    peak_month = peak["received_month"]
    peak_rows = [row for row in assignments if row["received_date"].startswith(peak_month)]
    peak_clusters = Counter(row["cluster_id"] for row in peak_rows)
    dominant_cluster, dominant_count = peak_clusters.most_common(1)[0]
    dominant_rows = [complaints[row["complaint_id"]] for row in peak_rows if row["cluster_id"] == dominant_cluster]
    labels = json.loads((ROOT / "model" / "cluster_labels.json").read_text(encoding="utf-8"))["labels"]
    result = {
        "peak_month": peak_month,
        "peak_total_complaints": len(peak_rows),
        "dominant_cluster_id": int(dominant_cluster),
        "dominant_cluster_label": labels[dominant_cluster],
        "dominant_cluster_complaints": dominant_count,
        "dominant_cluster_share_of_peak_percent": round(100 * dominant_count / len(peak_rows), 1),
        "dominant_cluster_update_word_mentions": sum(bool(UPDATE_WORDS.search(row["narrative"])) for row in dominant_rows),
        "dominant_cluster_model_year_2024": sum(row["model_year"] == "2024" for row in dominant_rows),
        "low_similarity_review_count": sum(row["needs_review"] == "yes" for row in assignments),
        "interpretation": "Keyword mentions and cluster membership are descriptive, not proof of cause or defect.",
    }
    (DATA / "insight_checks.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
