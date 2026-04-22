"""Machine-readable pipeline run manifests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "max.pipeline.run_manifest/v1"


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def build_run_manifest(
    result: Any,
    *,
    started_at: str,
    completed_at: str,
    inputs: dict[str, Any],
    source_counts: dict[str, int] | None = None,
    publication_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a stable JSON-serializable summary for a pipeline run."""
    budget = {
        "token_usage": getattr(result, "token_usage", {}) or {},
        "estimated_cost_usd": getattr(result, "estimated_cost_usd", 0.0),
        "cost_by_stage": getattr(result, "cost_by_stage", {}) or {},
        "budget_exceeded": getattr(result, "budget_exceeded", False),
    }
    counts = {
        "signals_fetched": getattr(result, "signals_fetched", 0),
        "signals_new": getattr(result, "signals_new", 0),
        "signals_skipped": getattr(result, "signals_skipped", 0),
        "insights_generated": getattr(result, "insights_generated", 0),
        "insights_duplicates_skipped": getattr(result, "insights_duplicates_skipped", 0),
        "ideas_generated": getattr(result, "ideas_generated", 0),
        "ideas_duplicates_skipped": getattr(result, "ideas_duplicates_skipped", 0),
        "ideas_evaluated": getattr(result, "ideas_evaluated", 0),
        "draft_ideas_generated": getattr(result, "draft_ideas_generated", 0),
        "ideas_revised": getattr(result, "ideas_revised", 0),
        "ideas_rejected_by_quality_gate": getattr(result, "ideas_rejected_by_quality_gate", 0),
        "ideas_rejected_by_domain_quality": getattr(result, "ideas_rejected_by_domain_quality", 0),
        "clusters_found": getattr(result, "clusters_found", 0),
        "multi_source_clusters": getattr(result, "multi_source_clusters", 0),
        "gaps_detected": getattr(result, "gaps_detected", 0),
    }

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": getattr(result, "run_id", ""),
        "profile_name": getattr(result, "profile_name", "") or inputs.get("profile_name", ""),
        "status": getattr(result, "status", "completed"),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": _duration_seconds(started_at, completed_at),
        "inputs": inputs,
        "source_counts": source_counts or getattr(result, "source_counts", {}) or {},
        "adapter_metrics": getattr(result, "adapter_metrics", {}) or {},
        "fetch_allocation": getattr(result, "fetch_allocation", {}) or {},
        "counts": counts,
        "generated_idea_ids": getattr(result, "generated_idea_ids", []) or [],
        "evaluation_recommendations": getattr(result, "evaluation_recommendations", []) or [],
        "top_ideas": getattr(result, "top_ideas", []) or [],
        "budget": budget,
        "publication_outputs": publication_outputs
        if publication_outputs is not None
        else getattr(result, "publication_outputs", []) or [],
        "error_message": getattr(result, "error_message", "") or "",
    }
    return _json_ready(manifest)


def write_run_manifest(path: Path | str, manifest: dict[str, Any]) -> Path:
    """Write a run manifest as deterministic pretty-printed JSON."""
    manifest_path = Path(path)
    if manifest_path.suffix:
        output_path = manifest_path
    else:
        output_path = manifest_path / "run-manifest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_json_ready(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _duration_seconds(started_at: str, completed_at: str) -> float:
    try:
        start = datetime.fromisoformat(started_at)
        complete = datetime.fromisoformat(completed_at)
    except ValueError:
        return 0.0
    return max(0.0, round((complete - start).total_seconds(), 3))


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
