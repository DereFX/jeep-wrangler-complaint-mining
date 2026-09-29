"""Portable dashboard projections over processed claims."""

from collections import Counter
from typing import Iterable


def summarize(records: Iterable[dict]) -> dict:
    records = [record for record in records if record.get("processing_status") == "processed"]
    families = Counter(record.get("issue_family", "other") for record in records)
    months = Counter((record.get("received_month") or record["received_date"][:7],
                      record.get("issue_family", "other")) for record in records)
    by_model_year = Counter(str(record.get("model_year", "unknown")) for record in records)
    return {
        "total_claims": len(records),
        "by_issue_family": [{"issue_family": family, "count": count} for family, count in families.most_common()],
        "by_model_year": [{"model_year": year, "count": count} for year, count in sorted(by_model_year.items())],
        "monthly_by_issue": [
            {"received_month": month, "issue_family": family, "count": count}
            for (month, family), count in sorted(months.items())
        ],
        "needs_review": sum(bool(record.get("needs_human_review")) for record in records),
    }


def claim_view(record: dict) -> dict:
    allowed = (
        "complaint_id", "received_date", "model_year", "source_component",
        "complaint_source_code", "issue_family", "issue_label", "component",
        "symptom_summary", "needs_human_review", "ai_provider", "narrative",
    )
    return {field: record.get(field) for field in allowed}
