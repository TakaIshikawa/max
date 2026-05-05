"""JSON API endpoint renderer for validation signal exports."""

from __future__ import annotations

import json
from typing import Any

from max.analysis.validation_signal_export import validation_experiment_signal
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal


SCHEMA_VERSION = "max.api.validation_signal_export.v1"


def validation_signal_export_to_json(experiment: dict, idea: BuildableUnit) -> str:
    """
    Render a validation experiment signal as JSON for API endpoints.

    Args:
        experiment: Validation experiment dict with hypothesis, method, result_summary, etc.
        idea: BuildableUnit associated with the experiment

    Returns:
        JSON string representation of the validation signal export
    """
    signal = validation_experiment_signal(experiment, idea)
    return _render_signal_as_json(signal, experiment, idea)


def _render_signal_as_json(signal: Signal, experiment: dict, idea: BuildableUnit) -> str:
    """Convert Signal and context into JSON-ready structure."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.api.validation_signal_export",
        "signal": {
            "source_type": signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type),
            "source_adapter": signal.source_adapter,
            "title": signal.title,
            "content": signal.content,
            "url": signal.url,
            "tags": list(signal.tags) if signal.tags else [],
            "credibility": signal.credibility,
        },
        "validation_data": {
            "experiment_id": experiment.get("id"),
            "idea_id": idea.id,
            "idea_title": idea.title,
            "hypothesis": signal.metadata.get("hypothesis", ""),
            "method": signal.metadata.get("method", ""),
            "status": signal.metadata.get("status", ""),
            "success_metric": signal.metadata.get("success_metric", ""),
            "result_summary": signal.metadata.get("result_summary", ""),
            "confidence_delta": signal.metadata.get("confidence_delta"),
            "evidence_urls": signal.metadata.get("evidence_urls", []),
            "completed_at": signal.metadata.get("completed_at"),
        },
        "aggregation_metrics": _compute_aggregation_metrics(experiment, signal),
    }

    return json.dumps(payload, indent=2, sort_keys=True)


def _compute_aggregation_metrics(experiment: dict, signal: Signal) -> dict[str, Any]:
    """Compute aggregation metrics for the validation signal."""
    confidence_delta = signal.metadata.get("confidence_delta")
    evidence_urls = signal.metadata.get("evidence_urls", [])

    return {
        "has_positive_confidence_delta": confidence_delta is not None and confidence_delta > 0,
        "has_evidence_urls": len(evidence_urls) > 0,
        "evidence_url_count": len(evidence_urls),
        "is_completed": signal.metadata.get("status") == "completed",
        "credibility_score": signal.credibility,
        "signal_quality_score": _compute_signal_quality_score(confidence_delta, evidence_urls, signal.credibility),
    }


def _compute_signal_quality_score(
    confidence_delta: float | None,
    evidence_urls: list[str],
    credibility: float,
) -> float:
    """
    Compute an overall quality score for the signal.

    Combines confidence delta, evidence presence, and credibility into a 0-1 score.
    """
    score = credibility  # Base score from credibility (0-1)

    if confidence_delta is not None and confidence_delta > 0:
        # Boost for positive confidence delta (up to 0.5 additional)
        score += min(confidence_delta, 0.5)

    if evidence_urls:
        # Boost for having evidence URLs (0.2)
        score += 0.2

    # Normalize to 0-1 range
    return min(score, 1.0)
