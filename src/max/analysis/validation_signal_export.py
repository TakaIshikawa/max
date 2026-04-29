"""Export completed validation experiments as first-class evidence signals."""

from __future__ import annotations

from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType

SOURCE_ADAPTER = "validation_experiment"


def _normalize_evidence_urls(value: object) -> list[str]:
    if isinstance(value, str):
        url = value.strip()
        return [url] if url else []

    try:
        values = iter(value)  # type: ignore[arg-type]
    except TypeError:
        return []

    return [url for item in values if isinstance(item, str) and (url := item.strip())]


def validation_experiment_signal(experiment: dict, idea: BuildableUnit) -> Signal:
    """Convert a completed validation experiment and its parent idea into a Signal."""
    evidence_urls = _normalize_evidence_urls(experiment.get("evidence_urls"))
    result_summary = (experiment.get("result_summary") or "").strip()
    hypothesis = (experiment.get("hypothesis") or "").strip()
    method = (experiment.get("method") or "").strip()

    content_parts = [
        f"Idea: {idea.title}",
        f"Hypothesis: {hypothesis}",
        f"Method: {method}",
        f"Success metric: {experiment.get('success_metric') or ''}",
    ]
    if result_summary:
        content_parts.append(f"Result: {result_summary}")
    if experiment.get("confidence_delta") is not None:
        content_parts.append(f"Confidence delta: {experiment['confidence_delta']}")
    if evidence_urls:
        content_parts.append("Evidence URLs: " + ", ".join(evidence_urls))

    return Signal(
        source_type=SignalSourceType.EXPERIMENT,
        source_adapter=SOURCE_ADAPTER,
        title=f"Validation experiment result: {idea.title}",
        content="\n".join(content_parts),
        url=f"max://validation-experiments/{experiment['id']}",
        tags=["validation", "experiment", "idea"],
        credibility=0.8,
        metadata={
            "experiment_id": experiment["id"],
            "idea_id": experiment["idea_id"],
            "hypothesis": hypothesis,
            "method": method,
            "status": experiment.get("status") or "",
            "confidence_delta": experiment.get("confidence_delta"),
            "evidence_urls": evidence_urls,
            "success_metric": experiment.get("success_metric") or "",
            "result_summary": result_summary,
            "completed_at": experiment.get("completed_at"),
            "signal_role": "market",
        },
    )
