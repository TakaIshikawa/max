"""Deterministic anomaly detection for pipeline LLM cost and token usage."""

from __future__ import annotations

from statistics import median
from typing import Mapping

from max import config
from max.analysis.budget_usage import _stage_usage_from_mapping
from max.llm.client import estimate_token_cost_usd, token_counts_from_usage

MIN_BASELINE_SAMPLES = 3


def _float_value(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _model_name(run: Mapping[str, object]) -> str:
    run_config = run.get("config")
    if isinstance(run_config, Mapping) and run_config.get("model"):
        return str(run_config["model"])
    return config.MODEL


def _profile_name(run: Mapping[str, object]) -> str | None:
    run_config = run.get("config")
    if not isinstance(run_config, Mapping):
        return None
    value = run_config.get("profile") or run_config.get("profile_name")
    return str(value) if value else None


def _run_usage(run: Mapping[str, object]) -> Mapping[str, object]:
    token_usage = run.get("token_usage")
    return token_usage if isinstance(token_usage, Mapping) else {}


def _run_metrics(run: Mapping[str, object]) -> dict[str, float | int]:
    token_usage = _run_usage(run)
    input_tokens, output_tokens = token_counts_from_usage(token_usage)
    stored_cost = _float_value(token_usage.get("estimated_cost_usd"))
    cost = (
        stored_cost
        if stored_cost is not None
        else estimate_token_cost_usd(input_tokens, output_tokens, model=_model_name(run))
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": cost,
    }


def _stage_metrics(run: Mapping[str, object]) -> dict[str, dict[str, float | int]]:
    stages = _stage_usage_from_mapping(_run_usage(run), model=_model_name(run))
    return {str(stage["stage"]): stage for stage in stages}


def _baseline(values: list[float]) -> dict[str, float | int]:
    midpoint = median(values)
    deviations = [abs(value - midpoint) for value in values]
    mad = median(deviations)
    return {"median": float(midpoint), "mad": float(mad), "sample_count": len(values)}


def _score(observed: float, baseline: dict[str, float | int]) -> tuple[float, float]:
    base = float(baseline["median"])
    mad = float(baseline["mad"])
    ratio = observed / base if base > 0 else (float("inf") if observed > 0 else 1.0)
    if mad > 0:
        z_score = 0.6745 * (observed - base) / mad
    elif observed > base:
        z_score = ratio
    else:
        z_score = 0.0
    return ratio, z_score


def _is_anomaly(observed: float, baseline: dict[str, float | int], z_threshold: float) -> bool:
    base = float(baseline["median"])
    ratio, z_score = _score(observed, baseline)
    return observed > base and (z_score >= z_threshold or ratio >= z_threshold)


def _recommendation(stage: str, metric: str) -> str:
    name = stage.lower()
    if any(part in name for part in ("draft", "critique", "revision", "ideat")):
        return "Reduce draft_count or narrow ideation inputs before this stage."
    if any(part in name for part in ("fetch", "signal", "source", "insight")):
        return "Lower signal_limit or tighten source filters for this profile."
    if "synth" in name:
        return "Inspect synthesis prompt size and trim evidence included per cluster."
    if "evaluat" in name or "score" in name:
        return "Reduce evaluation batch size or shorten rubric context."
    if metric == "estimated_cost_usd":
        return "Inspect model choice and prompt size for this stage."
    return "Inspect stage token usage and input payload size."


def _metric_anomaly(
    *,
    metric: str,
    observed: float,
    baseline: dict[str, float | int],
    z_threshold: float,
) -> dict[str, object] | None:
    if not _is_anomaly(observed, baseline, z_threshold):
        return None
    ratio, z_score = _score(observed, baseline)
    return {
        "metric": metric,
        "baseline": baseline["median"],
        "observed": observed,
        "ratio": ratio,
        "z_score": z_score,
        "sample_count": baseline["sample_count"],
    }


def _stage_anomalies(
    *,
    run: Mapping[str, object],
    stage_baselines: Mapping[str, Mapping[str, dict[str, float | int]]],
    z_threshold: float,
) -> list[dict[str, object]]:
    anomalies: list[dict[str, object]] = []
    for stage, metrics in _stage_metrics(run).items():
        baselines = stage_baselines.get(stage)
        if not baselines:
            continue
        for metric in ("total_tokens", "estimated_cost_usd"):
            observed = float(metrics.get(metric) or 0.0)
            anomaly = _metric_anomaly(
                metric=metric,
                observed=observed,
                baseline=baselines[metric],
                z_threshold=z_threshold,
            )
            if anomaly is None:
                continue
            anomaly.update(
                {
                    "stage": stage,
                    "recommendation": _recommendation(stage, metric),
                }
            )
            anomalies.append(anomaly)
    anomalies.sort(key=lambda item: (float(item["ratio"]), float(item["observed"])), reverse=True)
    return anomalies


def build_cost_anomaly_report(
    store: object,
    limit: int = 50,
    z_threshold: float = 2.0,
) -> dict[str, object]:
    """Return anomalous recent pipeline runs and stages from persisted token usage.

    Baselines are medians from prior same-profile runs. At least three prior
    samples are required for run-level metrics and for each stage-level metric.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if z_threshold <= 0:
        raise ValueError("z_threshold must be positive")

    history_limit = max(limit + MIN_BASELINE_SAMPLES, limit * 3, 100)
    runs = store.get_pipeline_runs(limit=history_limit)
    candidate_ids = {str(run["id"]) for run in runs[:limit]}
    chronological_runs = list(reversed(runs))

    prior_by_profile: dict[str | None, list[dict[str, object]]] = {}
    anomalies_by_id: dict[str, dict[str, object]] = {}
    evaluated_count = 0

    for run in chronological_runs:
        profile = _profile_name(run)
        prior_runs = prior_by_profile.setdefault(profile, [])
        run_id = str(run["id"])

        if run_id in candidate_ids:
            evaluated_count += 1
            if len(prior_runs) >= MIN_BASELINE_SAMPLES:
                total_values = [float(_run_metrics(prior)["total_tokens"]) for prior in prior_runs]
                cost_values = [float(_run_metrics(prior)["estimated_cost_usd"]) for prior in prior_runs]
                run_baselines = {
                    "total_tokens": _baseline(total_values),
                    "estimated_cost_usd": _baseline(cost_values),
                }
                stage_values: dict[str, dict[str, list[float]]] = {}
                for prior in prior_runs:
                    for stage, metrics in _stage_metrics(prior).items():
                        bucket = stage_values.setdefault(
                            stage,
                            {"total_tokens": [], "estimated_cost_usd": []},
                        )
                        bucket["total_tokens"].append(float(metrics.get("total_tokens") or 0.0))
                        bucket["estimated_cost_usd"].append(
                            float(metrics.get("estimated_cost_usd") or 0.0)
                        )
                stage_baselines = {
                    stage: {
                        metric: _baseline(values)
                        for metric, values in metrics.items()
                        if len(values) >= MIN_BASELINE_SAMPLES
                    }
                    for stage, metrics in stage_values.items()
                }

                metrics = _run_metrics(run)
                run_anomalies = [
                    anomaly
                    for anomaly in (
                        _metric_anomaly(
                            metric="total_tokens",
                            observed=float(metrics["total_tokens"]),
                            baseline=run_baselines["total_tokens"],
                            z_threshold=z_threshold,
                        ),
                        _metric_anomaly(
                            metric="estimated_cost_usd",
                            observed=float(metrics["estimated_cost_usd"]),
                            baseline=run_baselines["estimated_cost_usd"],
                            z_threshold=z_threshold,
                        ),
                    )
                    if anomaly is not None
                ]
                stage_anomalies = _stage_anomalies(
                    run=run,
                    stage_baselines=stage_baselines,
                    z_threshold=z_threshold,
                )

                if run_anomalies or stage_anomalies:
                    recommendations = []
                    for anomaly in stage_anomalies:
                        recommendation = str(anomaly["recommendation"])
                        if recommendation not in recommendations:
                            recommendations.append(recommendation)
                    if not recommendations:
                        recommendations.append("Inspect overall token usage and model cost for this run.")

                    anomalies_by_id[run_id] = {
                        "run_id": run_id,
                        "profile": profile,
                        "started_at": run.get("started_at"),
                        "total_tokens": metrics["total_tokens"],
                        "estimated_cost_usd": metrics["estimated_cost_usd"],
                        "run_anomalies": run_anomalies,
                        "stage_anomalies": stage_anomalies,
                        "recommendations": recommendations,
                    }

        prior_runs.append(dict(run))

    anomalies = [anomalies_by_id[run_id] for run_id in candidate_ids if run_id in anomalies_by_id]
    anomalies.sort(key=lambda item: str(item.get("started_at") or ""), reverse=True)

    return {
        "limit": limit,
        "z_threshold": z_threshold,
        "min_baseline_samples": MIN_BASELINE_SAMPLES,
        "run_count": evaluated_count,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
