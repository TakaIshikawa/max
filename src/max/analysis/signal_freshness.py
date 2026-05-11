"""Freshness analysis for ingested signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any


DEFAULT_MAX_AGE_DAYS = 30


@dataclass(frozen=True)
class FreshnessScore:
    source_adapter: str
    signal_count: int
    avg_age_hours: float
    median_age_hours: float
    newest_age_hours: float
    oldest_age_hours: float
    stale_count: int
    stale_ratio: float
    health: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_adapter": self.source_adapter,
            "signal_count": self.signal_count,
            "avg_age_hours": self.avg_age_hours,
            "median_age_hours": self.median_age_hours,
            "newest_age_hours": self.newest_age_hours,
            "oldest_age_hours": self.oldest_age_hours,
            "stale_count": self.stale_count,
            "stale_ratio": self.stale_ratio,
            "health": self.health,
        }


@dataclass
class FreshnessReport:
    scores: list[FreshnessScore]
    overall_health: str
    generated_at: str
    staleness_threshold_hours: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "scores": [score.to_dict() for score in self.scores],
            "overall_health": self.overall_health,
            "generated_at": self.generated_at,
            "staleness_threshold_hours": self.staleness_threshold_hours,
        }


class SignalFreshnessAnalyzer:
    """Analyze freshness of in-memory signal dictionaries by source adapter."""

    def __init__(self, *, staleness_threshold_hours: float = 168.0) -> None:
        if staleness_threshold_hours <= 0:
            raise ValueError("staleness_threshold_hours must be greater than 0")
        self.staleness_threshold_hours = float(staleness_threshold_hours)

    def analyze(self, signals: list[dict[str, Any]]) -> FreshnessReport:
        now = datetime.now(timezone.utc)
        grouped: dict[str, list[float]] = {}
        for signal in signals:
            source_adapter = str(signal.get("source_adapter") or "unknown")
            grouped.setdefault(source_adapter, []).append(self._compute_age(signal, now))

        scores: list[FreshnessScore] = []
        for source_adapter, ages in grouped.items():
            stale_count = sum(age > self.staleness_threshold_hours for age in ages)
            avg_age = sum(ages) / len(ages)
            stale_ratio = stale_count / len(ages)
            scores.append(
                FreshnessScore(
                    source_adapter=source_adapter,
                    signal_count=len(ages),
                    avg_age_hours=round(avg_age, 2),
                    median_age_hours=round(float(median(ages)), 2),
                    newest_age_hours=round(min(ages), 2),
                    oldest_age_hours=round(max(ages), 2),
                    stale_count=stale_count,
                    stale_ratio=round(stale_ratio, 4),
                    health=self._classify_health(avg_age, stale_ratio),
                )
            )

        scores.sort(key=lambda score: score.source_adapter)
        return FreshnessReport(
            scores=scores,
            overall_health=self._overall_health(scores),
            generated_at=now.isoformat(),
            staleness_threshold_hours=self.staleness_threshold_hours,
        )

    def _compute_age(self, signal: dict[str, Any], now: datetime) -> float:
        timestamp = _parse_optional_timestamp(
            signal.get("fetched_at") or signal.get("published_at")
        )
        if timestamp is None:
            return 0.0
        age_hours = (now - timestamp).total_seconds() / 3600
        return max(age_hours, 0.0)

    def _classify_health(self, avg_age: float, stale_ratio: float) -> str:
        threshold = self.staleness_threshold_hours
        if stale_ratio >= 0.75 or avg_age >= threshold * 2:
            return "critical"
        if stale_ratio >= 0.4 or avg_age >= threshold:
            return "stale"
        if stale_ratio > 0 or avg_age >= threshold * 0.5:
            return "aging"
        return "fresh"

    def _overall_health(self, scores: list[FreshnessScore]) -> str:
        if not scores:
            return "fresh"
        severity = {"fresh": 0, "aging": 1, "stale": 2, "critical": 3}
        return max(scores, key=lambda score: severity[score.health]).health


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
    parsed = _parse_optional_timestamp(value)
    if parsed is None:
        return datetime.now(timezone.utc)
    return parsed


def _parse_optional_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_aware_utc(value)
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _ensure_aware_utc(parsed)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def render_freshness_markdown(report: FreshnessReport) -> str:
    lines = [
        "# Signal Freshness",
        "",
        f"Generated: {report.generated_at}",
        f"Staleness threshold: {report.staleness_threshold_hours:g} hours",
        f"Overall health: {_health_indicator(report.overall_health)}",
        "",
        "| Source | Count | Avg age | Median age | Newest | Oldest | Stale | Health |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for score in report.scores:
        lines.append(
            "| "
            f"{score.source_adapter} | "
            f"{score.signal_count} | "
            f"{score.avg_age_hours:.1f}h | "
            f"{score.median_age_hours:.1f}h | "
            f"{score.newest_age_hours:.1f}h | "
            f"{score.oldest_age_hours:.1f}h | "
            f"{score.stale_count} ({score.stale_ratio:.0%}) | "
            f"{_health_indicator(score.health)} |"
        )
    return "\n".join(lines)


def _health_indicator(health: str) -> str:
    colors = {
        "fresh": "[green] fresh",
        "aging": "[yellow] aging",
        "stale": "[orange] stale",
        "critical": "[red] critical",
    }
    return colors.get(health, health)
