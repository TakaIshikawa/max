"""Compare persisted pipeline run metrics without re-running pipeline work."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from max import config
from max.llm.client import estimate_token_cost_usd, token_counts_from_usage
from max.store.db import Store


@dataclass(frozen=True)
class PipelineRunComparisonNotFound(Exception):
    """Raised when one or both requested pipeline runs do not exist."""

    missing_run_ids: list[str]


def _metric_delta(base: int | float, target: int | float) -> dict[str, int | float]:
    return {"base": base, "target": target, "delta": target - base}


def _run_summary(run: dict) -> dict[str, object]:
    return {
        "id": run["id"],
        "started_at": run["started_at"],
        "finished_at": run.get("completed_at"),
        "status": run.get("status") or ("completed" if run.get("completed_at") else "running"),
    }


def _run_cost(run: dict) -> float:
    token_usage = run.get("token_usage") or {}
    stored_cost = token_usage.get("estimated_cost_usd")
    if isinstance(stored_cost, (int, float)):
        return float(stored_cost)

    input_tokens, output_tokens = token_counts_from_usage(token_usage)
    model = str((run.get("config") or {}).get("model") or config.MODEL)
    return estimate_token_cost_usd(input_tokens, output_tokens, model=model)


def _budget_metrics(run: dict) -> dict[str, int | float]:
    input_tokens, output_tokens = token_counts_from_usage(run.get("token_usage") or {})
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": _run_cost(run),
    }


def _numeric_mapping_deltas(
    base: Mapping[str, object],
    target: Mapping[str, object],
) -> dict[str, dict[str, int | float]]:
    keys = sorted(set(base) | set(target))
    deltas: dict[str, dict[str, int | float]] = {}
    for key in keys:
        base_value = base.get(key, 0)
        target_value = target.get(key, 0)
        if isinstance(base_value, (int, float)) or isinstance(target_value, (int, float)):
            base_number = base_value if isinstance(base_value, (int, float)) else 0
            target_number = target_value if isinstance(target_value, (int, float)) else 0
            deltas[key] = _metric_delta(base_number, target_number)
    return deltas


def _adapter_deltas(base_run: dict, target_run: dict) -> list[dict[str, object]]:
    base_metrics = base_run.get("adapter_metrics") or {}
    target_metrics = target_run.get("adapter_metrics") or {}
    adapters = sorted(set(base_metrics) | set(target_metrics))

    rows: list[dict[str, object]] = []
    for adapter in adapters:
        base_adapter = base_metrics.get(adapter) or {}
        target_adapter = target_metrics.get(adapter) or {}
        base_status = base_adapter.get("status") if isinstance(base_adapter, Mapping) else None
        target_status = target_adapter.get("status") if isinstance(target_adapter, Mapping) else None
        rows.append(
            {
                "adapter": adapter,
                "base_status": base_status,
                "target_status": target_status,
                "status_changed": base_status != target_status,
                "metrics": _numeric_mapping_deltas(
                    base_adapter if isinstance(base_adapter, Mapping) else {},
                    target_adapter if isinstance(target_adapter, Mapping) else {},
                ),
                "base_error_message": (
                    base_adapter.get("error_message") if isinstance(base_adapter, Mapping) else None
                ),
                "target_error_message": (
                    target_adapter.get("error_message") if isinstance(target_adapter, Mapping) else None
                ),
            }
        )
    return rows


def compare_pipeline_runs(
    store: Store,
    *,
    base_run_id: str,
    target_run_id: str,
    include_adapter_metrics: bool = True,
) -> dict[str, object]:
    """Return persisted metric deltas between two pipeline runs.

    The comparison reads stored run rows, token usage, adapter metrics, and
    feedback attribution only. It intentionally does not call pipeline stages or
    source adapters.
    """
    base_run = store.get_pipeline_run(base_run_id)
    target_run = store.get_pipeline_run(target_run_id)
    missing = [
        run_id
        for run_id, run in ((base_run_id, base_run), (target_run_id, target_run))
        if run is None
    ]
    if missing:
        raise PipelineRunComparisonNotFound(missing)

    assert base_run is not None
    assert target_run is not None

    base_outputs = store.get_pipeline_run_output_counts(base_run_id)
    target_outputs = store.get_pipeline_run_output_counts(target_run_id)
    base_budget = _budget_metrics(base_run)
    target_budget = _budget_metrics(target_run)

    report: dict[str, object] = {
        "base_run": _run_summary(base_run),
        "target_run": _run_summary(target_run),
        "fetched_signals": {
            "signals_fetched": _metric_delta(
                base_run["signals_fetched"], target_run["signals_fetched"]
            ),
            "signals_new": _metric_delta(base_run["signals_new"], target_run["signals_new"]),
        },
        "insights": {
            "insights_generated": _metric_delta(
                base_run["insights_generated"], target_run["insights_generated"]
            ),
            "clusters_found": _metric_delta(base_run["clusters_found"], target_run["clusters_found"]),
            "gaps_detected": _metric_delta(base_run["gaps_detected"], target_run["gaps_detected"]),
        },
        "generated_ideas": {
            "ideas_generated": _metric_delta(
                base_run["ideas_generated"], target_run["ideas_generated"]
            ),
            "ideas_evaluated": _metric_delta(
                base_run["ideas_evaluated"], target_run["ideas_evaluated"]
            ),
            "avg_idea_score": _metric_delta(
                base_run["avg_idea_score"], target_run["avg_idea_score"]
            ),
        },
        "approved_published_outputs": {
            "approved": _metric_delta(base_outputs["approved"], target_outputs["approved"]),
            "published": _metric_delta(base_outputs["published"], target_outputs["published"]),
            "approved_or_published": _metric_delta(
                base_outputs["approved_or_published"],
                target_outputs["approved_or_published"],
            ),
        },
        "budget_usage": {
            key: _metric_delta(base_budget[key], target_budget[key]) for key in base_budget
        },
    }
    if include_adapter_metrics:
        report["adapter_metrics"] = _adapter_deltas(base_run, target_run)
    return report
