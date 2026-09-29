"""Cloud-neutral orchestration for one complaint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .ai import Classifier, classify_claim
from .core import clean_narrative, normalize_claim


def prepare_raw_claim(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate API input while retaining the original narrative in raw storage."""
    return normalize_claim(payload)


def process_claim(payload: dict[str, Any], provider: Classifier) -> dict[str, Any]:
    """Preprocess and infer without referring to AWS or Gemini directly."""
    claim = normalize_claim(payload)
    cleaned = clean_narrative(claim["narrative"])
    classification = classify_claim(cleaned, provider)
    return {
        "complaint_id": claim["complaint_id"],
        "received_date": claim["received_date"],
        "received_month": claim["received_date"][:7],
        "model_year": claim["model_year"],
        "source_component": claim["component"],
        "complaint_source_code": claim["complaint_source_code"],
        "narrative": cleaned,
        **classification,
        "processing_status": "processed",
        "ai_provider": provider.name,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
