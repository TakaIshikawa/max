"""Source configuration recommendations for domain profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any, Literal

from max.profiles.loader import load_profile
from max.profiles.schema import PipelineProfile, SourceConfig
from max.sources.registry import list_adapters
from max.store.db import Store

RecommendationAction = Literal[
    "increase_weight",
    "decrease_weight",
    "enable",
    "disable",
    "investigate",
    "keep",
]
RecommendationSeverity = Literal["low", "medium", "high"]

DEFAULT_MAX_AGE_DAYS = 30
MIN_APPROVAL_SAMPLES = 3
LOW_APPROVAL_RATE = 0.4
HIGH_APPROVAL_RATE = 0.7
HIGH_QUALITY_SCORE = 0.25
LOW_QUALITY_SCORE = 0.03


@dataclass(frozen=True)
class ProfileSourceRecommendation:
    """Recommendation for one source adapter in or near a profile."""

    adapter: str
    action: RecommendationAction
    severity: RecommendationSeverity
    enabled: bool
    registered: bool
    configured: bool
    current_weight: float
    suggested_weight: float
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "action": self.action,
            "severity": self.severity,
            "enabled": self.enabled,
            "registered": self.registered,
            "configured": self.configured,
            "current_weight": self.current_weight,
            "suggested_weight": self.suggested_weight,
            "reasons": self.reasons,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ProfileSourceRecommendationsReport:
    """Source recommendation report for one profile."""

    generated_at: str
    profile_name: str
    domain: str
    max_age_days: int
    recommendations: list[ProfileSourceRecommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "profile_name": self.profile_name,
            "domain": self.domain,
            "max_age_days": self.max_age_days,
            "recommendations": [rec.to_dict() for rec in self.recommendations],
        }


def build_profile_source_recommendations(
    profile_name: str,
    store: Store,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> ProfileSourceRecommendationsReport:
    """Load a profile and recommend source configuration changes."""
    profile = load_profile(profile_name)
    return build_profile_source_recommendations_for_profile(
        profile,
        store,
        max_age_days=max_age_days,
        now=now,
    )


def build_profile_source_recommendations_for_profile(
    profile: PipelineProfile,
    store: Store,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> ProfileSourceRecommendationsReport:
    """Recommend source configuration changes for an already-loaded profile."""
    if max_age_days < 1:
        raise ValueError("max_age_days must be at least 1")

    generated_at = _ensure_aware_utc(now or datetime.now(timezone.utc))
    source_by_adapter = _source_config_by_adapter(profile.sources)
    registered = set(list_adapters())
    quality_stats = store.get_adapter_quality_stats()
    approval_stats = store.get_adapter_approval_stats()
    freshness_stats = _freshness_by_adapter(
        store.get_signal_freshness_records(),
        now=generated_at,
        max_age_days=max_age_days,
    )

    adapters = sorted(
        set(source_by_adapter)
        | set(quality_stats)
        | set(approval_stats)
        | set(freshness_stats)
    )
    recommendations = [
        _recommend_adapter(
            adapter,
            source=source_by_adapter.get(adapter),
            registered=adapter in registered,
            quality=quality_stats.get(adapter, {}),
            approval=approval_stats.get(adapter, {}),
            freshness=freshness_stats.get(adapter, {}),
        )
        for adapter in adapters
    ]
    recommendations.sort(
        key=lambda rec: (_severity_rank(rec.severity), _action_rank(rec.action), rec.adapter)
    )

    return ProfileSourceRecommendationsReport(
        generated_at=generated_at.isoformat(),
        profile_name=profile.name,
        domain=profile.domain.name,
        max_age_days=max_age_days,
        recommendations=recommendations,
    )


def _recommend_adapter(
    adapter: str,
    *,
    source: SourceConfig | None,
    registered: bool,
    quality: dict[str, Any],
    approval: dict[str, Any],
    freshness: dict[str, Any],
) -> ProfileSourceRecommendation:
    configured = source is not None
    enabled = bool(source.enabled) if source else False
    current_weight = float(source.weight) if source else 0.0
    total_signals = int(quality.get("total_signals", freshness.get("total_count", 0)) or 0)
    insight_hit_rate = _rate(quality.get("insight_hit_rate"))
    idea_hit_rate = _rate(quality.get("idea_hit_rate"))
    quality_score = round((insight_hit_rate * 0.6) + (idea_hit_rate * 0.4), 4)
    total_feedbacked = int(approval.get("total_feedbacked", 0) or 0)
    approval_rate = _optional_rate(approval.get("approval_rate"))
    stale_count = int(freshness.get("stale_count", 0) or 0)
    freshness_total = int(freshness.get("total_count", 0) or 0)
    stale_rate = (stale_count / freshness_total) if freshness_total else 0.0

    evidence = {
        "quality": {
            "total_signals": total_signals,
            "insight_hit_rate": insight_hit_rate,
            "idea_hit_rate": idea_hit_rate,
            "quality_score": quality_score,
        },
        "approval": {
            "total_feedbacked": total_feedbacked,
            "approved": int(approval.get("approved", 0) or 0),
            "rejected": int(approval.get("rejected", 0) or 0),
            "approval_rate": approval_rate,
        },
        "freshness": {
            "total_count": freshness_total,
            "stale_count": stale_count,
            "stale_rate": round(stale_rate, 4),
            "newest_timestamp": freshness.get("newest_timestamp"),
            "median_age_days": freshness.get("median_age_days"),
        },
        "registered": registered,
        "configured": configured,
        "enabled": enabled,
    }

    reasons: list[str] = []
    action: RecommendationAction = "keep"
    severity: RecommendationSeverity = "low"
    suggested_weight = current_weight

    if configured and not registered:
        reasons.append("Configured adapter is not registered and cannot be fetched.")
        return _rec(
            adapter, "investigate", "high", enabled, registered, configured,
            current_weight, current_weight, reasons, evidence,
        )

    if not configured:
        reasons.append("Adapter has stored evidence but is not configured in this profile.")
        return _rec(
            adapter, "investigate", "medium", enabled, registered, configured,
            current_weight, current_weight, reasons, evidence,
        )

    if freshness_total and stale_rate >= 0.8:
        reasons.append(f"{stale_count} of {freshness_total} active signals are stale.")
        if enabled and total_signals >= 3 and quality_score <= LOW_QUALITY_SCORE:
            action = "disable"
            severity = "high"
            suggested_weight = 0.0
        else:
            action = "investigate"
            severity = "medium"
    elif freshness_total and stale_rate >= 0.5:
        reasons.append(f"{stale_count} of {freshness_total} active signals are stale.")
        action = "investigate"
        severity = "medium"

    if enabled and total_feedbacked >= MIN_APPROVAL_SAMPLES and approval_rate is not None:
        if approval_rate <= LOW_APPROVAL_RATE:
            reasons.append(
                f"Approval rate is {approval_rate:.2f} across {total_feedbacked} feedback records."
            )
            if action == "keep":
                action = "decrease_weight"
                severity = "medium"
                suggested_weight = _round_weight(current_weight * 0.5)
            elif action == "investigate":
                severity = "high"
        elif approval_rate >= HIGH_APPROVAL_RATE and action == "keep" and quality_score >= HIGH_QUALITY_SCORE:
            reasons.append(
                f"Approval rate is {approval_rate:.2f} and quality score is {quality_score:.2f}."
            )
            action = "increase_weight"
            severity = "low"
            suggested_weight = _round_weight(max(current_weight * 1.25, current_weight + 0.25))

    if not enabled and _is_high_performing(quality_score, total_signals, approval_rate, total_feedbacked):
        reasons.append("Disabled adapter has strong historical quality or approval evidence.")
        action = "enable"
        severity = "medium"
        suggested_weight = _round_weight(max(current_weight, 1.0))

    if enabled and action == "keep":
        reasons.append("Adapter is registered, enabled, and has no negative quality, approval, or freshness signals.")
    elif not enabled and action == "keep":
        reasons.append("Adapter is disabled and lacks enough positive evidence to recommend enabling.")

    return _rec(
        adapter, action, severity, enabled, registered, configured,
        current_weight, suggested_weight, reasons, evidence,
    )


def _source_config_by_adapter(sources: list[SourceConfig]) -> dict[str, SourceConfig]:
    by_adapter: dict[str, SourceConfig] = {}
    for source in sources:
        by_adapter[source.adapter] = source
    return by_adapter


def _freshness_by_adapter(
    records: list[dict[str, Any]],
    *,
    now: datetime,
    max_age_days: int,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        adapter = str(record.get("source_adapter") or "unknown")
        timestamp = _parse_timestamp(record.get("published_at") or record.get("fetched_at"))
        age_days = max((now - timestamp).total_seconds() / 86400, 0.0)
        grouped.setdefault(adapter, []).append({
            "timestamp": timestamp,
            "age_days": age_days,
            "is_stale": age_days > max_age_days,
        })

    stats: dict[str, dict[str, Any]] = {}
    for adapter, rows in grouped.items():
        timestamps = [row["timestamp"] for row in rows]
        ages = [row["age_days"] for row in rows]
        stats[adapter] = {
            "total_count": len(rows),
            "stale_count": sum(1 for row in rows if row["is_stale"]),
            "newest_timestamp": max(timestamps).isoformat() if timestamps else None,
            "median_age_days": round(float(median(ages)), 2) if ages else None,
        }
    return stats


def _is_high_performing(
    quality_score: float,
    total_signals: int,
    approval_rate: float | None,
    total_feedbacked: int,
) -> bool:
    if total_feedbacked >= MIN_APPROVAL_SAMPLES and approval_rate is not None:
        if approval_rate >= HIGH_APPROVAL_RATE:
            return True
    return total_signals >= 3 and quality_score >= HIGH_QUALITY_SCORE


def _rec(
    adapter: str,
    action: RecommendationAction,
    severity: RecommendationSeverity,
    enabled: bool,
    registered: bool,
    configured: bool,
    current_weight: float,
    suggested_weight: float,
    reasons: list[str],
    evidence: dict[str, Any],
) -> ProfileSourceRecommendation:
    return ProfileSourceRecommendation(
        adapter=adapter,
        action=action,
        severity=severity,
        enabled=enabled,
        registered=registered,
        configured=configured,
        current_weight=_round_weight(current_weight),
        suggested_weight=_round_weight(suggested_weight),
        reasons=reasons,
        evidence=evidence,
    )


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware_utc(value)
    if not value:
        return datetime.now(timezone.utc)
    return _ensure_aware_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_rate(value: Any) -> float | None:
    if value is None:
        return None
    return _rate(value)


def _rate(value: Any) -> float:
    if value is None:
        return 0.0
    return round(float(value), 4)


def _round_weight(value: float) -> float:
    return round(max(float(value), 0.0), 3)


def _severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)


def _action_rank(action: str) -> int:
    return {
        "disable": 0,
        "investigate": 1,
        "decrease_weight": 2,
        "enable": 3,
        "increase_weight": 4,
        "keep": 5,
    }.get(action, 6)
