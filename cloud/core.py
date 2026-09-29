"""Provider-neutral claim validation and preprocessing."""

from __future__ import annotations

import re
from datetime import date
from typing import Any


ISSUE_LABELS = {
    "steering_dashboard": "Steering assist and dashboard warnings",
    "display_camera": "Display, radio, and backup camera",
    "shutdown_restart": "Unexpected shutdown and restart",
    "recall_parts": "Recall repair parts unavailable",
    "hybrid_power": "Hybrid drive power loss",
    "instrument_cluster": "Instrument cluster and gauges",
    "battery_fire": "Battery fire and charging restrictions",
    "safety_recall": "Broader safety recall concerns",
    "other": "Other or unclear issue",
}

IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)")
SPACE = re.compile(r"\s+")


class ClaimValidationError(ValueError):
    pass


def normalize_claim(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept the existing NHTSA-shaped schema or text + JSON metadata."""
    if not isinstance(payload, dict):
        raise ClaimValidationError("Claim must be a JSON object")
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ClaimValidationError("metadata must be a JSON object")
    merged = {**metadata, **{key: value for key, value in payload.items() if key != "metadata"}}
    complaint_id = str(merged.get("complaint_id") or "").strip()
    if not IDENTIFIER.fullmatch(complaint_id):
        raise ClaimValidationError("complaint_id must be 1–100 letters, digits, underscores, or hyphens")
    narrative = merged.get("narrative", merged.get("text", ""))
    if not isinstance(narrative, str) or not 30 <= len(narrative.strip()) <= 20000:
        raise ClaimValidationError("narrative must contain 30–20,000 characters")
    received_date = str(merged.get("received_date") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", received_date):
        raise ClaimValidationError("received_date must use YYYY-MM-DD")
    try:
        date.fromisoformat(received_date)
    except ValueError as error:
        raise ClaimValidationError("received_date is invalid") from error
    model_year = merged.get("model_year")
    try:
        model_year = int(model_year)
    except (TypeError, ValueError) as error:
        raise ClaimValidationError("model_year must be a four-digit year") from error
    if not 1980 <= model_year <= date.today().year + 2:
        raise ClaimValidationError("model_year is outside the supported range")
    component = str(merged.get("component") or "ELECTRICAL SYSTEM").strip()[:120]
    source = str(merged.get("complaint_source_code") or merged.get("source") or "CUSTOMER").strip()[:30]
    return {
        "complaint_id": complaint_id,
        "received_date": received_date,
        "model_year": model_year,
        "component": component,
        "complaint_source_code": source,
        "narrative": narrative.strip(),
    }


def clean_narrative(text: str) -> str:
    """Remove common identifiers before sending complaint text to an LLM.

    This is a limited filter. Real customer records need a separate privacy review.
    """
    value = SPACE.sub(" ", text).strip()
    value = EMAIL.sub("[EMAIL]", value)
    value = PHONE.sub("[PHONE]", value)
    return VIN.sub("[VIN]", value)


def normalize_classification(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Classifier result must be an object")
    family = result.get("issue_family")
    if family not in ISSUE_LABELS:
        raise ValueError(f"Unknown issue_family: {family!r}")
    summary = result.get("symptom_summary")
    if not isinstance(summary, str) or not 3 <= len(summary.strip()) <= 300:
        raise ValueError("symptom_summary must be 3–300 characters")
    component = result.get("component")
    if not isinstance(component, str) or not component.strip():
        component = "Unspecified"
    review = result.get("needs_human_review")
    if not isinstance(review, bool):
        raise ValueError("needs_human_review must be a boolean")
    return {
        "issue_family": family,
        "issue_label": ISSUE_LABELS[family],
        "component": component.strip()[:120],
        "symptom_summary": summary.strip(),
        "needs_human_review": review,
    }
