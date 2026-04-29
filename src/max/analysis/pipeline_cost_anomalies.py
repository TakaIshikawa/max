"""Detect deterministic cost anomalies in persisted pipeline runs."""

from __future__ import annotations

from statistics import mean
from typing import Mapping

from max import config
from max.analysis.budget_usage import _stage_usage_from_mapping
from max.llm.client import estimate_token_cost_usd
from max.store.db import Store

DEFAULT_LIMIT = 20
DEFAULT_BASELINE_WINDOW = 5
DEFAULT_MIN_COST_USD = 0.05
DEFAULT_MULTIPLIER_THRESHOLD = 2.0


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    try:
        return int(value)
    except (OverflowError, ValueError):
        return 0


def _token_counts_from_usage(token_usage: Mapping[str, object]) -> tuple[int, int]:
    input_tokens = token_usage.get("total_input", token_usage.get("input", 0))
    output_tokens = token_usage.get("total_output", token_usage.get("output", 0))
    return _int_value(input_tokens), _int_value(output_tokens)


def _profile_name(run: Mapping[str, object]) -> str | None:
    run_config = run.get("config")
    if not isinstance(run_config, Mapping):
        return None
    value = run_config.get("profile") or run_config.get("profile_name")
    return str(value) if value else None


def _model_name(run: Mapping[str, object]) -> str:
    run_config = run.get("config")
    if isinstance(run_config, Mapping) and run_config.get("model"):
        return str(run_config["model"])
    return config.MODEL


def _run_usage(run: Mapping[str, object]) -> Mapping[str, object]:
    token_usage = run.get("token_usage")
    return token_usage if isinstance(token_usage, Mapping) else {}


def _run_total_tokens(run: Mapping[str, object]) -> int:
    input_tokens, output_tokens = _token_counts_from_usage(_run_usage(run))
    return input_tokens + output_tokens


def _run_cost(run: Mapping[str, object]) -> float:
    token_usage = _run_usage(run)
    stored_cost = _float_value(token_usage.get("estimated_cost_usd"))
    if stored_cost is not None:
        return stored_cost
    input_tokens, output_tokens = _token_counts_from_usage(token_usage)
    return estimate_token_cost_usd(input_tokens, output_tokens, model=_model_name(run))


def _sanitized_stage_usage(token_usage: Mapping[str, object]) -> dict[str, object]:
    sanitized = dict(token_usage)
    by_stage = token_usage.get("by_stage")
    if isinstance(by_stage, Mapping):
        sanitized["by_stage"] = {
            stage: {
                "input": _int_value(counts.get("input")),
                "output": _int_value(counts.get("output")),
            }
            for stage, counts in by_stage.items()
            if isinstance(counts, Mapping)
        }

    cost_by_stage = token_usage.get("cost_by_stage")
    if isinstance(cost_by_stage, Mapping):
        sanitized["cost_by_stage"] = {
            stage: cost
            for stage, cost in (
                (stage, _float_value(value)) for stage, value in cost_by_stage.items()
            )
            if cost is not None
        }

    for key, value in token_usage.items():
        if not isinstance(key, str):
            continue
        if key.endswith("_input") or key.endswith("_output"):
            sanitized[key] = _int_value(value)

    return sanitized


def _top_stage_metrics(run: Mapping[str, object], *, max_stages: int = 3) -> list[dict[str, object]]:
    stages = _stage_usage_from_mapping(
        _sanitized_stage_usage(_run_usage(run)),
        model=_model_name(run),
    )
    stages.sort(
        key=lambda stage: (
            float(stage.get("estimated_cost_usd") or 0.0),
            int(stage.get("total_tokens") or 0),
            str(stage.get("stage") or ""),
        ),
        reverse=True,
    )
    return stages[:max_stages]


def build_pipeline_cost_anomaly_report(
    store: Store,
    *,
    limit: int = DEFAULT_LIMIT,
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
    min_cost_usd: float = DEFAULT_MIN_COST_USD,
    multiplier_threshold: float = DEFAULT_MULTIPLIER_THRESHOLD,
) -> dict[str, object]:
    """Return recent pipeline runs whose cost is anomalous versus prior runs.

    Baselines are computed from the previous ``baseline_window`` runs with the
    same profile. Runs without enough prior same-profile history are skipped.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if baseline_window < 1:
        raise ValueError("baseline_window must be at least 1")
    if min_cost_usd < 0:
        raise ValueError("min_cost_usd must be non-negative")
    if multiplier_threshold <= 0:
        raise ValueError("multiplier_threshold must be positive")

    history_limit = max(limit + baseline_window, limit + (baseline_window * 5), 100)
    runs = store.get_pipeline_runs(limit=history_limit)
    chronological_runs = list(reversed(runs))
    candidate_ids = {str(run["id"]) for run in runs[:limit]}

    prior_by_profile: dict[str | None, list[dict[str, object]]] = {}
    anomalies_by_id: dict[str, dict[str, object]] = {}

    for run in chronological_runs:
        profile = _profile_name(run)
        prior_runs = prior_by_profile.setdefault(profile, [])
        run_id = str(run["id"])

        if run_id in candidate_ids and len(prior_runs) >= baseline_window:
            baseline_runs = prior_runs[-baseline_window:]
            baseline_cost = mean(_run_cost(baseline_run) for baseline_run in baseline_runs)
            estimated_cost = _run_cost(run)
            multiplier = estimated_cost / baseline_cost if baseline_cost > 0 else 0.0
            reasons: list[str] = []

            if estimated_cost >= min_cost_usd:
                reasons.append(
                    f"estimated cost ${estimated_cost:.4f} is at or above threshold ${min_cost_usd:.4f}"
                )
            if baseline_cost > 0 and multiplier >= multiplier_threshold:
                reasons.append(
                    f"estimated cost is {multiplier:.2f}x the rolling baseline ${baseline_cost:.4f}"
                )

            if reasons:
                anomalies_by_id[run_id] = {
                    "run_id": run_id,
                    "profile": profile,
                    "started_at": run["started_at"],
                    "total_tokens": _run_total_tokens(run),
                    "estimated_cost_usd": estimated_cost,
                    "baseline_cost_usd": baseline_cost,
                    "multiplier": multiplier,
                    "anomaly_reasons": reasons,
                    "top_stage_metrics": _top_stage_metrics(run),
                }

        prior_runs.append(dict(run))

    anomalies = [anomalies_by_id[run_id] for run_id in candidate_ids if run_id in anomalies_by_id]
    anomalies.sort(key=lambda item: str(item["started_at"]), reverse=True)

    return {
        "limit": limit,
        "baseline_window": baseline_window,
        "min_cost_usd": min_cost_usd,
        "multiplier_threshold": multiplier_threshold,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
