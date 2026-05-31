"""Generate synthesis backfill plans."""

from __future__ import annotations

from typing import Any, Mapping

VALID_REASONS = {"prompt_change", "embedding_change", "schema_change"}


def generate_synthesis_backfill_plan(request: Mapping[str, Any]) -> dict[str, Any]:
    reason = _text(request.get("backfill_reason") or request.get("reason")) or "unknown"
    ranges = _list(request.get("signal_ranges") or request.get("candidate_signal_ranges"), ["unknown-range"])
    batch_size = _int(request.get("batch_size"), 500)
    budget = _map(request.get("budget") or request.get("budget_guardrails"))
    max_tokens = _int(budget.get("max_tokens"), _int(request.get("max_tokens"), 0))
    return {"schema_version": "max.synthesis_backfill_plan.v1", "kind": "max.synthesis_backfill_plan", "backfill_reason": reason, "reason_supported": reason in VALID_REASONS, "candidate_signal_ranges": [{"range_id": _text(item) or f"range-{index}"} for index, item in enumerate(ranges, start=1)], "batching_strategy": {"batch_size": batch_size, "ordering": "oldest_signal_first", "checkpoint": "persist after every completed batch"}, "budget_guardrails": {"max_tokens": max_tokens, "stop_on_budget_breach": True, "per_batch_token_cap": _int(budget.get("per_batch_token_cap"), max_tokens or batch_size * 200)}, "deduplication_checks": [{"id": "DED1", "description": "Skip signal/version pairs already synthesized for this reason."}, {"id": "DED2", "description": "Compare output content hash before publish."}], "acceptance_criteria": [{"id": "ACC1", "description": "Batch reconciliation has zero duplicate synthesized records."}, {"id": "ACC2", "description": "Quality sample passes review before widening."}]}


def _list(value: Any, fallback: list[Any]) -> list[Any]:
    if isinstance(value, list):
        return value or fallback
    return fallback if value in (None, "") else [value]


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
