"""Profile source adapter coverage gap reporting."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from max.profiles import loader as profile_loader
from max.profiles.schema import PipelineProfile, SourceConfig
from max.sources.base import snapshot_circuit_breakers
from max.sources.registry import AdapterMetadata, get_adapter, get_adapter_metadata

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.source_adapter_coverage_gaps.v1"
KIND = "max.source_adapter_coverage_gaps"
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_STALE_DAYS = 30
DEFAULT_MIN_EXPECTED_SOURCES = 1


def build_source_adapter_coverage_gap_report(
    store: Store,
    profile_name: str,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_expected_sources: int = DEFAULT_MIN_EXPECTED_SOURCES,
    stale_days: int = DEFAULT_STALE_DAYS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-ready report comparing profile sources to ingested signals."""

    profile = profile_loader.load_profile(profile_name)
    return build_source_adapter_coverage_gap_report_for_profile(
        store,
        profile,
        lookback_days=lookback_days,
        min_expected_sources=min_expected_sources,
        stale_days=stale_days,
        generated_at=generated_at,
    )


def build_source_adapter_coverage_gaps_report(
    store: Store,
    profile_name: str,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_expected_sources: int = DEFAULT_MIN_EXPECTED_SOURCES,
    stale_days: int = DEFAULT_STALE_DAYS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Alias using the plural report name from the module title."""

    return build_source_adapter_coverage_gap_report(
        store,
        profile_name,
        lookback_days=lookback_days,
        min_expected_sources=min_expected_sources,
        stale_days=stale_days,
        generated_at=generated_at,
    )


def build_source_adapter_coverage_gap_report_for_profile(
    store: Store,
    profile: PipelineProfile,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_expected_sources: int = DEFAULT_MIN_EXPECTED_SOURCES,
    stale_days: int = DEFAULT_STALE_DAYS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a coverage gap report for an already loaded profile."""

    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")
    if min_expected_sources < 1:
        raise ValueError("min_expected_sources must be at least 1")
    if stale_days < 1:
        raise ValueError("stale_days must be at least 1")

    generated = generated_at or datetime.now(UTC).isoformat()
    generated_dt = _parse_datetime(generated) or datetime.now(UTC)
    lookback_cutoff = generated_dt - timedelta(days=lookback_days)
    stale_cutoff = generated_dt - timedelta(days=stale_days)

    enabled_sources = [source for source in profile.sources if source.enabled]
    profile_adapters = {source.adapter for source in profile.sources}
    configured_adapters = {source.adapter for source in enabled_sources}
    signals = store.get_signal_freshness_records()
    signal_stats = _signal_stats_by_adapter(signals, lookback_cutoff=lookback_cutoff)
    active_adapters = {
        adapter for adapter, stats in signal_stats.items() if int(stats["recent_signal_count"]) > 0
    }
    adapter_names = sorted(configured_adapters | active_adapters)
    metadata = get_adapter_metadata()
    latest_fetch_status = _latest_fetch_status_by_adapter(store)
    circuit_snapshots = _circuit_snapshots(adapter_names)

    rows = [
        _adapter_row(
            adapter,
            source=_source_by_adapter(enabled_sources).get(adapter),
            configured=adapter in configured_adapters,
            present_in_profile=adapter in profile_adapters,
            stats=signal_stats.get(adapter, _empty_signal_stats()),
            metadata=metadata.get(adapter),
            latest_fetch_status=latest_fetch_status.get(adapter),
            circuit=circuit_snapshots.get(adapter),
            stale_cutoff=stale_cutoff,
        )
        for adapter in adapter_names
    ]
    rows.sort(key=lambda row: (-len(row["flags"]), row["adapter"]))

    flags = _flags(rows)
    recommendations = _recommendations(
        rows,
        enabled_adapter_count=len(configured_adapters),
        min_expected_sources=min_expected_sources,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated,
        "profile_name": profile.name,
        "domain": profile.domain.name,
        "lookback_window": {
            "days": lookback_days,
            "started_at": lookback_cutoff.isoformat(),
            "ended_at": generated_dt.isoformat(),
        },
        "filters": {
            "profile_name": profile.name,
            "lookback_days": lookback_days,
            "min_expected_sources": min_expected_sources,
            "stale_days": stale_days,
        },
        "summary": {
            "configured_adapter_count": len(configured_adapters),
            "disabled_adapter_count": len(profile.sources) - len(configured_adapters),
            "active_adapter_count": len(active_adapters),
            "adapter_row_count": len(rows),
            "recent_signal_count": sum(int(row["recent_signal_count"]) for row in rows),
            "configured_silent_count": len(flags["configured_silent"]),
            "active_unconfigured_count": len(flags["active_unconfigured"]),
            "stale_count": len(flags["stale"]),
            "failing_count": len(flags["failing"]),
            "below_min_expected_sources": len(configured_adapters) < min_expected_sources,
        },
        "adapter_rows": rows,
        "coverage_flags": flags,
        "recommendations": recommendations,
    }


def _adapter_row(
    adapter: str,
    *,
    source: SourceConfig | None,
    configured: bool,
    present_in_profile: bool,
    stats: dict[str, Any],
    metadata: AdapterMetadata | None,
    latest_fetch_status: str | None,
    circuit: dict[str, Any] | None,
    stale_cutoff: datetime,
) -> dict[str, Any]:
    recent_signal_count = int(stats["recent_signal_count"])
    total_signal_count = int(stats["total_signal_count"])
    newest_signal_at = stats["newest_signal_at"]
    newest_signal_dt = _parse_datetime(newest_signal_at)
    circuit_state = str((circuit or {}).get("state") or "unknown")
    flags: list[str] = []

    if configured and recent_signal_count == 0:
        flags.append("configured_silent")
    if not present_in_profile and recent_signal_count > 0:
        flags.append("active_unconfigured")
    if newest_signal_dt is not None and newest_signal_dt < stale_cutoff:
        flags.append("stale")
    if _is_failing(latest_fetch_status, circuit_state):
        flags.append("failing")

    return {
        "adapter": adapter,
        "configured": configured,
        "present_in_profile": present_in_profile,
        "enabled": source.enabled if source is not None else False,
        "source_type": _adapter_source_type(adapter, stats),
        "weight": float(source.weight) if source is not None else 0.0,
        "configured_params": dict(source.params) if source is not None else {},
        "watchlist": list(source.watchlist) if source is not None else [],
        "metadata": _metadata_payload(metadata),
        "recent_signal_count": recent_signal_count,
        "total_signal_count": total_signal_count,
        "newest_signal_at": newest_signal_at,
        "latest_fetch_status": latest_fetch_status,
        "circuit_breaker": circuit,
        "flags": flags,
    }


def _signal_stats_by_adapter(
    signals: Iterable[Mapping[str, Any]],
    *,
    lookback_cutoff: datetime,
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for signal in signals:
        adapter = str(signal.get("source_adapter") or "unknown")
        item = stats.setdefault(adapter, _empty_signal_stats())
        item["total_signal_count"] += 1
        source_type = str(signal.get("source_type") or "unknown")
        item["source_types"][source_type] += 1
        fetched_at = _parse_datetime(signal.get("fetched_at"))
        if fetched_at is None:
            continue
        newest_dt = _parse_datetime(item["newest_signal_at"])
        if newest_dt is None or fetched_at > newest_dt:
            item["newest_signal_at"] = fetched_at.isoformat()
        if fetched_at >= lookback_cutoff:
            item["recent_signal_count"] += 1
    return stats


def _empty_signal_stats() -> dict[str, Any]:
    return {
        "recent_signal_count": 0,
        "total_signal_count": 0,
        "newest_signal_at": None,
        "source_types": Counter(),
    }


def _latest_fetch_status_by_adapter(store: Store) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for run in store.get_pipeline_runs(limit=50):
        adapter_metrics = run.get("adapter_metrics") or {}
        if not isinstance(adapter_metrics, Mapping):
            continue
        for adapter, metrics in adapter_metrics.items():
            if adapter in statuses or not isinstance(metrics, Mapping):
                continue
            statuses[str(adapter)] = str(metrics.get("status") or "unknown")
    return statuses


def _circuit_snapshots(adapter_names: list[str]) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for snapshot in snapshot_circuit_breakers(adapter_names=adapter_names):
        snapshots[snapshot.adapter_name] = {
            "state": snapshot.state,
            "failure_count": snapshot.failure_count,
            "last_failure_at": snapshot.last_failure_at,
            "retry_after": snapshot.retry_after,
        }
    return snapshots


def _flags(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {
        "configured_silent": [],
        "active_unconfigured": [],
        "stale": [],
        "failing": [],
    }
    for row in rows:
        flag_row = {
            "adapter": row["adapter"],
            "recent_signal_count": row["recent_signal_count"],
            "newest_signal_at": row["newest_signal_at"],
            "latest_fetch_status": row["latest_fetch_status"],
            "circuit_state": (row["circuit_breaker"] or {}).get("state"),
        }
        for flag in row["flags"]:
            grouped[flag].append(flag_row)
    return grouped


def _recommendations(
    rows: list[dict[str, Any]],
    *,
    enabled_adapter_count: int,
    min_expected_sources: int,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if enabled_adapter_count < min_expected_sources:
        recommendations.append(
            {
                "type": "increase_profile_source_coverage",
                "action": (
                    f"Enable at least {min_expected_sources - enabled_adapter_count} more "
                    "profile source adapter(s) before relying on source mix conclusions."
                ),
                "adapters": [],
            }
        )

    for flag, action in (
        (
            "configured_silent",
            "Review adapter parameters, credentials, and fetch allocation for configured adapters with no recent signals.",
        ),
        (
            "active_unconfigured",
            "Add active unconfigured adapters to the profile or archive their signals if they are no longer intentional.",
        ),
        (
            "stale",
            "Refresh stale adapters or lower their profile weight until ingestion is current.",
        ),
        (
            "failing",
            "Inspect failing adapters and reset or repair circuit breaker and fetch errors before the next run.",
        ),
    ):
        adapters = [row["adapter"] for row in rows if flag in row["flags"]]
        if adapters:
            recommendations.append(
                {
                    "type": flag,
                    "action": action,
                    "adapters": adapters,
                }
            )
    if not recommendations:
        recommendations.append(
            {
                "type": "maintain_coverage",
                "action": "No adapter coverage gaps detected for the selected profile and lookback window.",
                "adapters": [],
            }
        )
    return recommendations


def _source_by_adapter(sources: Iterable[SourceConfig]) -> dict[str, SourceConfig]:
    return {source.adapter: source for source in sources}


def _adapter_source_type(adapter: str, stats: dict[str, Any]) -> str:
    source_types = stats.get("source_types")
    if isinstance(source_types, Counter) and source_types:
        return source_types.most_common(1)[0][0]
    try:
        source_type = get_adapter(adapter).source_type
    except Exception:
        return "unknown"
    if hasattr(source_type, "value"):
        return str(source_type.value)
    return str(source_type)


def _metadata_payload(metadata: AdapterMetadata | None) -> dict[str, Any]:
    if metadata is None:
        return {
            "description": "",
            "config_keys": [],
            "required_keys": [],
        }
    return {
        "description": metadata.description,
        "config_keys": list(metadata.config_keys),
        "required_keys": list(metadata.required_keys),
    }


def _is_failing(latest_fetch_status: str | None, circuit_state: str) -> bool:
    if latest_fetch_status in {"error", "failed", "timeout"}:
        return True
    return circuit_state in {"open", "half_open"}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
