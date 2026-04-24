"""Profile drift analysis for recent pipeline outputs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from max.evaluation.weights import get_weights
from max.profiles.schema import PipelineProfile
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal

DEFAULT_SIGNAL_LIMIT = 500
DEFAULT_UNIT_LIMIT = 100
DEFAULT_INSIGHT_LIMIT = 500
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MIN_SIGNALS = 1


@dataclass(frozen=True)
class ProfileDriftDistribution:
    """Observed-vs-expected distribution drift for one profile dimension."""

    metric: str
    sample_count: int
    expected: dict[str, float]
    observed: dict[str, float]
    counts: dict[str, int]
    missing_expected: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    drift_score: float = 0.0
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "sample_count": self.sample_count,
            "expected": self.expected,
            "observed": self.observed,
            "counts": self.counts,
            "missing_expected": self.missing_expected,
            "unexpected": self.unexpected,
            "drift_score": self.drift_score,
            "status": self.status,
        }


@dataclass(frozen=True)
class EvaluationWeightMismatch:
    """Mismatch between configured profile weights and stored evaluation weights."""

    sample_count: int
    expected_weights: dict[str, float]
    average_weights_used: dict[str, float]
    average_absolute_delta: float
    max_dimension_delta: float
    mismatched_evaluation_count: int
    missing_weights_count: int
    status: str
    dimension_deltas: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "expected_weights": self.expected_weights,
            "average_weights_used": self.average_weights_used,
            "average_absolute_delta": self.average_absolute_delta,
            "max_dimension_delta": self.max_dimension_delta,
            "mismatched_evaluation_count": self.mismatched_evaluation_count,
            "missing_weights_count": self.missing_weights_count,
            "status": self.status,
            "dimension_deltas": self.dimension_deltas,
        }


@dataclass(frozen=True)
class ProfileDriftReport:
    """Profile drift report across recent stored pipeline outputs."""

    generated_at: str
    profile_name: str
    domain: str
    signal_limit: int
    unit_limit: int
    insight_limit: int
    lookback_days: int | None
    min_signals: int
    signals_analyzed: int
    insights_analyzed: int
    units_analyzed: int
    evaluations_analyzed: int
    category_drift: ProfileDriftDistribution
    source_mix_drift: ProfileDriftDistribution
    target_user_drift: ProfileDriftDistribution
    evaluation_weight_mismatch: EvaluationWeightMismatch
    overall_drift_score: float
    status: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "profile_name": self.profile_name,
            "domain": self.domain,
            "signal_limit": self.signal_limit,
            "unit_limit": self.unit_limit,
            "insight_limit": self.insight_limit,
            "lookback_days": self.lookback_days,
            "min_signals": self.min_signals,
            "signals_analyzed": self.signals_analyzed,
            "insights_analyzed": self.insights_analyzed,
            "units_analyzed": self.units_analyzed,
            "evaluations_analyzed": self.evaluations_analyzed,
            "category_drift": self.category_drift.to_dict(),
            "source_mix_drift": self.source_mix_drift.to_dict(),
            "target_user_drift": self.target_user_drift.to_dict(),
            "evaluation_weight_mismatch": self.evaluation_weight_mismatch.to_dict(),
            "overall_drift_score": self.overall_drift_score,
            "status": self.status,
            "warnings": self.warnings,
        }


def build_profile_drift_report(
    profile: PipelineProfile,
    store: Store,
    *,
    signal_limit: int = DEFAULT_SIGNAL_LIMIT,
    unit_limit: int = DEFAULT_UNIT_LIMIT,
    insight_limit: int = DEFAULT_INSIGHT_LIMIT,
    lookback_days: int | None = None,
    min_signals: int = 0,
) -> ProfileDriftReport:
    """Compare recent stored outputs to a selected domain profile."""

    if signal_limit < 1:
        raise ValueError("signal_limit must be at least 1")
    if unit_limit < 1:
        raise ValueError("unit_limit must be at least 1")
    if insight_limit < 1:
        raise ValueError("insight_limit must be at least 1")
    if lookback_days is not None and lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")
    if min_signals < 0:
        raise ValueError("min_signals must be non-negative")

    units = _recent_profile_units(profile, store, limit=unit_limit)
    insights = _recent_profile_insights(profile, store, limit=insight_limit)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
        if lookback_days is not None
        else None
    )
    if cutoff is not None:
        units = [
            unit
            for unit in units
            if _is_recent(_latest_timestamp(unit.created_at, unit.updated_at), cutoff)
        ]
        insights = [
            insight
            for insight in insights
            if _is_recent(getattr(insight, "created_at", None), cutoff)
        ]
    signals = _recent_profile_signals(profile, store, units=units, signal_limit=signal_limit)
    if cutoff is not None:
        signals = [signal for signal in signals if _is_recent(signal.fetched_at, cutoff)]
    evaluations = [store.get_evaluation(unit.id) for unit in units]
    evaluations = [evaluation for evaluation in evaluations if evaluation is not None]

    category_drift = _distribution_drift(
        "category_drift",
        expected=_equal_distribution(profile.domain.categories),
        values=[unit.category for unit in units],
    )
    source_mix_drift = _distribution_drift(
        "source_mix_drift",
        expected=_source_distribution(profile),
        values=[signal.source_adapter for signal in signals],
    )
    target_user_drift = _distribution_drift(
        "target_user_drift",
        expected=_equal_distribution(profile.domain.target_user_types),
        values=[unit.target_users for unit in units],
    )
    evaluation_weight_mismatch = _evaluation_weight_mismatch(profile, evaluations)

    component_scores = [
        category_drift.drift_score,
        source_mix_drift.drift_score,
        target_user_drift.drift_score,
        evaluation_weight_mismatch.average_absolute_delta,
    ]
    overall_score = _round_rate(sum(component_scores) / len(component_scores))
    warnings = _warnings(
        signals=signals,
        insights=insights,
        units=units,
        evaluations=evaluations,
        min_signals=min_signals,
        category_drift=category_drift,
        source_mix_drift=source_mix_drift,
        target_user_drift=target_user_drift,
        weight_mismatch=evaluation_weight_mismatch,
    )

    return ProfileDriftReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        profile_name=profile.name,
        domain=profile.domain.name,
        signal_limit=signal_limit,
        unit_limit=unit_limit,
        insight_limit=insight_limit,
        lookback_days=lookback_days,
        min_signals=min_signals,
        signals_analyzed=len(signals),
        insights_analyzed=len(insights),
        units_analyzed=len(units),
        evaluations_analyzed=len(evaluations),
        category_drift=category_drift,
        source_mix_drift=source_mix_drift,
        target_user_drift=target_user_drift,
        evaluation_weight_mismatch=evaluation_weight_mismatch,
        overall_drift_score=overall_score,
        status=_status(overall_score),
        warnings=warnings,
    )


def _recent_profile_units(profile: PipelineProfile, store: Store, *, limit: int) -> list[BuildableUnit]:
    units = store.get_buildable_units(limit=limit, domain=profile.domain.name)
    if units:
        return units

    candidates = store.get_buildable_units(limit=limit)
    scoped = [
        unit
        for unit in candidates
        if unit.domain in {profile.name, profile.domain.name}
    ]
    return scoped or [unit for unit in candidates if not unit.domain]


def _recent_profile_insights(profile: PipelineProfile, store: Store, *, limit: int):
    insights = store.get_active_insights(domain=profile.domain.name)
    if insights:
        return insights[:limit]
    candidates = store.get_insights(limit=limit)
    scoped = [
        insight
        for insight in candidates
        if profile.name in insight.domains or profile.domain.name in insight.domains
    ]
    return scoped or [insight for insight in candidates if not insight.domains]


def _recent_profile_signals(
    profile: PipelineProfile,
    store: Store,
    *,
    units: list[BuildableUnit],
    signal_limit: int,
) -> list[Signal]:
    evidence_ids: list[str] = []
    seen: set[str] = set()
    for unit in units:
        for signal_id in unit.evidence_signals:
            if signal_id and signal_id not in seen:
                seen.add(signal_id)
                evidence_ids.append(signal_id)

    evidence_signals = [
        signal
        for signal_id in evidence_ids[:signal_limit]
        if (signal := store.get_signal(signal_id)) is not None
    ]
    if evidence_signals:
        return evidence_signals

    enabled_adapters = {source.adapter for source in profile.sources if source.enabled}
    signals = store.get_signals(limit=signal_limit)
    scoped = [signal for signal in signals if signal.source_adapter in enabled_adapters]
    return scoped or signals


def _distribution_drift(
    metric: str,
    *,
    expected: dict[str, float],
    values: list[str],
) -> ProfileDriftDistribution:
    clean_values = [_normalize_label(value) for value in values if _normalize_label(value)]
    counts = dict(sorted(Counter(clean_values).items()))
    observed = _counts_to_distribution(counts)
    expected = dict(sorted((_normalize_label(key), value) for key, value in expected.items()))

    all_keys = set(expected) | set(observed)
    drift_score = _round_rate(
        sum(abs(observed.get(key, 0.0) - expected.get(key, 0.0)) for key in all_keys) / 2
    )
    missing_expected = sorted(key for key in expected if key not in observed)
    unexpected = sorted(key for key in observed if key not in expected)

    return ProfileDriftDistribution(
        metric=metric,
        sample_count=len(clean_values),
        expected=expected,
        observed=observed,
        counts=counts,
        missing_expected=missing_expected,
        unexpected=unexpected,
        drift_score=drift_score,
        status=_status(drift_score),
    )


def _evaluation_weight_mismatch(profile: PipelineProfile, evaluations) -> EvaluationWeightMismatch:
    expected = _expected_weights(profile)
    if not evaluations:
        return EvaluationWeightMismatch(
            sample_count=0,
            expected_weights=expected,
            average_weights_used={},
            average_absolute_delta=0.0,
            max_dimension_delta=0.0,
            mismatched_evaluation_count=0,
            missing_weights_count=0,
            status="insufficient_data",
            dimension_deltas={},
        )

    totals = {dimension: 0.0 for dimension in expected}
    mismatched = 0
    missing = 0
    for evaluation in evaluations:
        weights = evaluation.weights_used or {}
        if not weights:
            missing += 1
        deltas = [
            abs(float(weights.get(dimension, 0.0)) - expected_weight)
            for dimension, expected_weight in expected.items()
        ]
        if any(delta > 0.001 for delta in deltas):
            mismatched += 1
        for dimension in expected:
            totals[dimension] += float(weights.get(dimension, 0.0))

    average = {
        dimension: round(total / len(evaluations), 4)
        for dimension, total in sorted(totals.items())
    }
    dimension_deltas = {
        dimension: round(abs(average.get(dimension, 0.0) - expected_weight), 4)
        for dimension, expected_weight in sorted(expected.items())
    }
    average_delta = _round_rate(
        sum(dimension_deltas.values()) / max(len(dimension_deltas), 1)
    )
    max_delta = _round_rate(max(dimension_deltas.values()) if dimension_deltas else 0.0)

    return EvaluationWeightMismatch(
        sample_count=len(evaluations),
        expected_weights=expected,
        average_weights_used=average,
        average_absolute_delta=average_delta,
        max_dimension_delta=max_delta,
        mismatched_evaluation_count=mismatched,
        missing_weights_count=missing,
        status=_status(average_delta),
        dimension_deltas=dimension_deltas,
    )


def _expected_weights(profile: PipelineProfile) -> dict[str, float]:
    weights = profile.evaluation.custom_weights or get_weights(profile.evaluation.weight_profile)
    total = sum(float(value) for value in weights.values())
    if total <= 0:
        return {}
    return {
        str(dimension): round(float(value) / total, 4)
        for dimension, value in sorted(weights.items())
    }


def _source_distribution(profile: PipelineProfile) -> dict[str, float]:
    weights: dict[str, float] = {}
    for source in profile.sources:
        if not source.enabled:
            continue
        weights[source.adapter] = weights.get(source.adapter, 0.0) + max(float(source.weight), 0.0)
    if not weights:
        return {}
    if sum(weights.values()) <= 0:
        return _equal_distribution(list(weights))
    return _normalize_distribution(weights)


def _equal_distribution(values: list[str]) -> dict[str, float]:
    labels = sorted({_normalize_label(value) for value in values if _normalize_label(value)})
    if not labels:
        return {}
    share = round(1 / len(labels), 4)
    distribution = {label: share for label in labels}
    return _normalize_distribution(distribution)


def _counts_to_distribution(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {key: round(value / total, 4) for key, value in sorted(counts.items())}


def _normalize_distribution(values: dict[str, float]) -> dict[str, float]:
    total = sum(float(value) for value in values.values())
    if total <= 0:
        return {key: 0.0 for key in sorted(values)}
    return {
        _normalize_label(key): round(float(value) / total, 4)
        for key, value in sorted(values.items())
    }


def _normalize_label(value: str) -> str:
    return str(value or "").strip()


def _round_rate(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def _latest_timestamp(*values) -> datetime | None:
    parsed = [_parse_datetime(value) for value in values]
    parsed = [value for value in parsed if value is not None]
    return max(parsed) if parsed else None


def _is_recent(value, cutoff: datetime) -> bool:
    parsed = _parse_datetime(value)
    return parsed is not None and parsed >= cutoff


def _parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _status(score: float) -> str:
    if score >= 0.35:
        return "high"
    if score >= 0.15:
        return "medium"
    return "ok"


def _warnings(
    *,
    signals: list[Signal],
    insights: list,
    units: list[BuildableUnit],
    evaluations: list,
    min_signals: int,
    category_drift: ProfileDriftDistribution,
    source_mix_drift: ProfileDriftDistribution,
    target_user_drift: ProfileDriftDistribution,
    weight_mismatch: EvaluationWeightMismatch,
) -> list[str]:
    warnings: list[str] = []
    if not signals:
        warnings.append("No recent signals were available for source mix drift.")
    elif len(signals) < min_signals:
        warnings.append(
            f"Only {len(signals)} signal(s) were available; min_signals is {min_signals}."
        )
    if not insights:
        warnings.append("No recent insights were available for the selected profile.")
    if not units:
        warnings.append("No recent buildable units were available for category or target-user drift.")
    if not evaluations:
        warnings.append("No evaluations were available for weight mismatch analysis.")
    for metric in (category_drift, source_mix_drift, target_user_drift):
        if metric.unexpected:
            warnings.append(f"{metric.metric} has unexpected values: {', '.join(metric.unexpected)}.")
    if weight_mismatch.missing_weights_count:
        warnings.append(
            f"{weight_mismatch.missing_weights_count} evaluation(s) did not record weights_used."
        )
    return warnings
