"""Freshness analysis for ingested signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any


DEFAULT_MAX_AGE_DAYS = 30


@dataclass(frozen=True)
class FreshnessGroupSummary:
    key: str
    total_count: int
    newest_timestamp: str | None
    oldest_timestamp: str | None
    median_age_days: float | None
    stale_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "total_count": self.total_count,
            "newest_timestamp": self.newest_timestamp,
            "oldest_timestamp": self.oldest_timestamp,
            "median_age_days": self.median_age_days,
            "stale_count": self.stale_count,
        }


@dataclass(frozen=True)
class FreshnessRecommendation:
    source_adapter: str
    stale_count: int
    total_count: int
    newest_timestamp: str | None
    median_age_days: float | None
    reason: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_adapter": self.source_adapter,
            "stale_count": self.stale_count,
            "total_count": self.total_count,
            "newest_timestamp": self.newest_timestamp,
            "median_age_days": self.median_age_days,
            "reason": self.reason,
            "action": self.action,
        }


@dataclass(frozen=True)
class SignalFreshnessReport:
    generated_at: str
    max_age_days: int
    source_adapter_filters: list[str] = field(default_factory=list)
    total_signals: int = 0
    stale_signals: int = 0
    by_source_adapter: list[FreshnessGroupSummary] = field(default_factory=list)
    by_source_type: list[FreshnessGroupSummary] = field(default_factory=list)
    by_domain_tag: list[FreshnessGroupSummary] = field(default_factory=list)
    by_signal_role: list[FreshnessGroupSummary] = field(default_factory=list)
    recommendations: list[FreshnessRecommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "max_age_days": self.max_age_days,
            "source_adapter_filters": self.source_adapter_filters,
            "total_signals": self.total_signals,
            "stale_signals": self.stale_signals,
            "by_source_adapter": [group.to_dict() for group in self.by_source_adapter],
            "by_source_type": [group.to_dict() for group in self.by_source_type],
            "by_domain_tag": [group.to_dict() for group in self.by_domain_tag],
            "by_signal_role": [group.to_dict() for group in self.by_signal_role],
            "recommendations": [rec.to_dict() for rec in self.recommendations],
        }


def build_signal_freshness_report(
    store,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    source_adapters: list[str] | None = None,
    now: datetime | None = None,
) -> SignalFreshnessReport:
    """Build a read-only freshness report for active signals."""
    if max_age_days < 1:
        raise ValueError("max_age_days must be at least 1")

    generated_at = now or datetime.now(timezone.utc)
    generated_at = _ensure_aware_utc(generated_at)
    filters = _clean_filters(source_adapters)
    rows = store.get_signal_freshness_records(source_adapters=filters or None)
    enriched = [_enrich_record(row, generated_at, max_age_days) for row in rows]

    return SignalFreshnessReport(
        generated_at=generated_at.isoformat(),
        max_age_days=max_age_days,
        source_adapter_filters=filters,
        total_signals=len(enriched),
        stale_signals=sum(1 for row in enriched if row["is_stale"]),
        by_source_adapter=_summarize_groups(enriched, "source_adapter"),
        by_source_type=_summarize_groups(enriched, "source_type"),
        by_domain_tag=_summarize_domain_tags(enriched),
        by_signal_role=_summarize_groups(enriched, "signal_role"),
        recommendations=_build_recommendations(
            _summarize_groups(enriched, "source_adapter"),
            max_age_days=max_age_days,
        ),
    )


def _clean_filters(values: list[str] | None) -> list[str]:
    if not values:
        return []
    filters: set[str] = set()
    for value in values:
        if not value:
            continue
        filters.update(part.strip() for part in value.split(",") if part.strip())
    return sorted(filters)


def _enrich_record(row: dict[str, Any], now: datetime, max_age_days: int) -> dict[str, Any]:
    timestamp = _parse_timestamp(row.get("published_at") or row.get("fetched_at"))
    age_days = max((now - timestamp).total_seconds() / 86400, 0.0)
    return {
        **row,
        "signal_timestamp": timestamp,
        "age_days": age_days,
        "is_stale": age_days > max_age_days,
        "signal_role": row.get("signal_role") or "unclassified",
        "tags": row.get("tags") or [],
    }


def _summarize_groups(records: list[dict[str, Any]], key_name: str) -> list[FreshnessGroupSummary]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = str(record.get(key_name) or "unknown")
        grouped.setdefault(key, []).append(record)
    return _summaries_from_groups(grouped)


def _summarize_domain_tags(records: list[dict[str, Any]]) -> list[FreshnessGroupSummary]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        tags = record.get("tags") or ["untagged"]
        for tag in tags:
            key = str(tag).strip() or "untagged"
            grouped.setdefault(key, []).append(record)
    return _summaries_from_groups(grouped)


def _summaries_from_groups(grouped: dict[str, list[dict[str, Any]]]) -> list[FreshnessGroupSummary]:
    summaries = [_summarize_group(key, rows) for key, rows in grouped.items()]
    return sorted(
        summaries,
        key=lambda item: (-item.stale_count, -(item.median_age_days or 0.0), item.key),
    )


def _summarize_group(key: str, records: list[dict[str, Any]]) -> FreshnessGroupSummary:
    timestamps = [record["signal_timestamp"] for record in records]
    ages = [record["age_days"] for record in records]
    newest = max(timestamps) if timestamps else None
    oldest = min(timestamps) if timestamps else None
    return FreshnessGroupSummary(
        key=key,
        total_count=len(records),
        newest_timestamp=newest.isoformat() if newest else None,
        oldest_timestamp=oldest.isoformat() if oldest else None,
        median_age_days=round(float(median(ages)), 2) if ages else None,
        stale_count=sum(1 for record in records if record["is_stale"]),
    )


def _build_recommendations(
    adapter_summaries: list[FreshnessGroupSummary],
    *,
    max_age_days: int,
) -> list[FreshnessRecommendation]:
    recommendations: list[FreshnessRecommendation] = []
    for summary in adapter_summaries:
        if summary.stale_count == 0:
            continue
        if summary.stale_count == summary.total_count:
            reason = f"All {summary.total_count} active signals exceed {max_age_days} days old."
        else:
            reason = (
                f"{summary.stale_count} of {summary.total_count} active signals exceed "
                f"{max_age_days} days old."
            )
        recommendations.append(
            FreshnessRecommendation(
                source_adapter=summary.key,
                stale_count=summary.stale_count,
                total_count=summary.total_count,
                newest_timestamp=summary.newest_timestamp,
                median_age_days=summary.median_age_days,
                reason=reason,
                action="Review adapter configuration, credentials, rate limits, and fetch cadence.",
            )
        )
    return recommendations


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware_utc(value)
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _ensure_aware_utc(parsed)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
