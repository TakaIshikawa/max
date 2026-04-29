"""Build deterministic replay plans for persisted pipeline runs."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from max.store.db import Store


@dataclass(frozen=True)
class PipelineReplayRunNotFound(Exception):
    """Raised when a requested pipeline run does not exist."""

    run_id: str


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "started_at": run["started_at"],
        "finished_at": run.get("completed_at"),
        "status": run.get("status") or ("completed" if run.get("completed_at") else "running"),
    }


def _original_metrics(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "signals_fetched": run.get("signals_fetched", 0),
        "signals_new": run.get("signals_new", 0),
        "insights_generated": run.get("insights_generated", 0),
        "ideas_generated": run.get("ideas_generated", 0),
        "ideas_evaluated": run.get("ideas_evaluated", 0),
        "clusters_found": run.get("clusters_found", 0),
        "gaps_detected": run.get("gaps_detected", 0),
        "avg_idea_score": run.get("avg_idea_score", 0.0),
        "fetch_allocation": dict(sorted((run.get("fetch_allocation") or {}).items())),
        "token_usage": run.get("token_usage") or {},
    }


def _resolve_profile(profile_name: str | None) -> tuple[Any | None, str | None]:
    if not profile_name:
        return None, None

    from max.profiles.loader import load_profile

    try:
        return load_profile(profile_name), None
    except FileNotFoundError:
        return None, f"Profile '{profile_name}' could not be loaded; replay inputs are inferred from stored run data."


def _profile_config(run_config: Mapping[str, Any], profile: Any | None, profile_name: str | None) -> dict[str, Any]:
    if profile is None:
        return {
            "name": profile_name,
            "found": False,
            "domain": None,
            "signal_limit": run_config.get("signal_limit"),
            "min_score": run_config.get("min_score"),
            "weight_profile": run_config.get("weight_profile"),
            "ideation_mode": run_config.get("ideation_mode"),
            "quality_loop_enabled": run_config.get("quality_loop_enabled"),
            "draft_count": run_config.get("draft_count"),
        }

    return {
        "name": profile.name,
        "found": True,
        "domain": profile.domain.name,
        "signal_limit": profile.signal_limit,
        "min_score": profile.evaluation.min_score,
        "weight_profile": profile.evaluation.weight_profile,
        "ideation_mode": profile.ideation_mode,
        "quality_loop_enabled": profile.quality_loop_enabled,
        "draft_count": profile.draft_count,
    }


def _adapter_input_rows(
    *,
    profile: Any | None,
    adapter_metrics: Mapping[str, Any],
    fetch_allocation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows_by_adapter: dict[str, dict[str, Any]] = {}
    if profile is not None:
        for source in profile.sources:
            rows_by_adapter[source.adapter] = {
                "adapter": source.adapter,
                "enabled": source.enabled,
                "weight": source.weight,
                "params": source.normalized_params,
                "observed_status": None,
                "observed_signal_count": 0,
                "recommended_limit": _int_or_none(fetch_allocation.get(source.adapter)),
            }

    for adapter, metrics in adapter_metrics.items():
        metric_map = metrics if isinstance(metrics, Mapping) else {}
        row = rows_by_adapter.setdefault(
            adapter,
            {
                "adapter": adapter,
                "enabled": True,
                "weight": None,
                "params": {},
                "observed_status": None,
                "observed_signal_count": 0,
                "recommended_limit": _int_or_none(fetch_allocation.get(adapter)),
            },
        )
        row["observed_status"] = metric_map.get("status")
        row["observed_signal_count"] = _int_value(metric_map.get("signal_count"))
        if row["recommended_limit"] is None:
            row["recommended_limit"] = row["observed_signal_count"]

    return [rows_by_adapter[name] for name in sorted(rows_by_adapter)]


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _adapter_metrics(adapter_metrics: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        adapter: dict(metrics) if isinstance(metrics, Mapping) else {}
        for adapter, metrics in sorted(adapter_metrics.items())
    }


def _recommended_limits(
    adapter_inputs: list[dict[str, Any]],
    run_config: Mapping[str, Any],
) -> dict[str, int]:
    default_limit = _int_value(run_config.get("signal_limit"))
    limits: dict[str, int] = {}
    for row in adapter_inputs:
        recommended = row.get("recommended_limit")
        observed = row.get("observed_signal_count")
        limit = recommended if isinstance(recommended, int) else observed
        limits[row["adapter"]] = max(1, int(limit or default_limit or 1))
    return dict(sorted(limits.items()))


def _available_adapters_warning(adapter_names: set[str]) -> list[str]:
    if not adapter_names:
        return []

    from max.sources.registry import list_adapters

    available = set(list_adapters())
    unavailable = sorted(adapter_names - available)
    if not unavailable:
        return []
    return [
        "Adapters referenced by the original run are not currently available: "
        + ", ".join(unavailable)
    ]


def _dry_run_commands(
    profile_name: str | None,
    run_config: Mapping[str, Any],
    recommended_limits: Mapping[str, int],
) -> dict[str, Any]:
    signal_limit = _int_value(run_config.get("signal_limit"))
    if not signal_limit and recommended_limits:
        signal_limit = max(recommended_limits.values())

    cli_parts = ["max", "run", "--dry-run"]
    if profile_name:
        cli_parts.extend(["--profile", profile_name])
    if signal_limit:
        cli_parts.extend(["--signal-limit", str(signal_limit)])
    if run_config.get("min_score") is not None:
        cli_parts.extend(["--min-score", str(run_config["min_score"])])
    if run_config.get("weight_profile"):
        cli_parts.extend(["--weight-profile", str(run_config["weight_profile"])])
    if run_config.get("ideation_mode"):
        cli_parts.extend(["--mode", str(run_config["ideation_mode"])])
    if run_config.get("quality_loop_enabled"):
        cli_parts.append("--quality-loop")
    if run_config.get("draft_count") is not None:
        cli_parts.extend(["--draft-count", str(run_config["draft_count"])])

    return {
        "cli": shlex.join(cli_parts),
        "api": {
            "method": "POST",
            "path": "/api/v1/pipeline/dry-run",
            "body": {
                key: value
                for key, value in {
                    "profile": profile_name,
                    "signal_limit": signal_limit or None,
                    "min_score": run_config.get("min_score"),
                    "weight_profile": run_config.get("weight_profile"),
                    "ideation_mode": run_config.get("ideation_mode"),
                    "quality_loop_enabled": run_config.get("quality_loop_enabled"),
                    "draft_count": run_config.get("draft_count"),
                }.items()
                if value is not None
            },
        },
    }


def build_pipeline_replay_plan(
    store: Store,
    run_id: str,
    profile_name: str | None = None,
) -> dict[str, Any]:
    """Return a read-only plan for replaying a persisted pipeline run.

    The plan is assembled only from stored run metadata, profile files, and the
    adapter registry. It does not fetch sources, call LLMs, or write to the
    store.
    """
    run = store.get_pipeline_run(run_id)
    if run is None:
        raise PipelineReplayRunNotFound(run_id)

    run_config = run.get("config") or {}
    inferred_profile_name = profile_name or run_config.get("profile")
    profile, profile_warning = _resolve_profile(inferred_profile_name)
    adapter_metrics = _adapter_metrics(run.get("adapter_metrics") or {})
    fetch_allocation = run.get("fetch_allocation") or {}
    adapter_inputs = _adapter_input_rows(
        profile=profile,
        adapter_metrics=adapter_metrics,
        fetch_allocation=fetch_allocation,
    )
    recommended_limits = _recommended_limits(adapter_inputs, run_config)

    warnings: list[str] = []
    if profile_warning:
        warnings.append(profile_warning)
    elif not inferred_profile_name:
        warnings.append("No profile was recorded for the original run; replay inputs are inferred from stored run data.")
    if not adapter_metrics:
        warnings.append("No adapter metrics were recorded for the original run; adapter replay details are degraded.")
    warnings.extend(_available_adapters_warning({row["adapter"] for row in adapter_inputs}))

    return {
        "run": _run_summary(run),
        "profile": _profile_config(run_config, profile, inferred_profile_name),
        "original_config": dict(sorted(run_config.items())),
        "original_metrics": _original_metrics(run),
        "adapter_inputs": adapter_inputs,
        "adapter_metrics": adapter_metrics,
        "recommended_source_limits": recommended_limits,
        "dry_run_commands": _dry_run_commands(
            inferred_profile_name,
            run_config,
            recommended_limits,
        ),
        "warnings": warnings,
    }
