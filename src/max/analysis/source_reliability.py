"""Source reliability analysis by source type."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from max.analysis.triangulation import triangulate
from max.sources.base import snapshot_circuit_breakers
from max.sources.registry import list_adapters
from max.store.db import Store
from max.types.signal import Signal


DEFAULT_SIGNAL_LIMIT = 500


@dataclass(frozen=True)
class SourceReliabilityRow:
    """Reliability metrics for one signal source type."""

    source_type: str
    total_signals: int
    source_adapters: list[str]
    registered_adapters: list[str]
    adapter_health_score: float
    signal_usefulness_score: float
    corroboration_rate: float
    downstream_idea_conversion_rate: float
    feedback_approval_rate: float | None
    reliability_score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "total_signals": self.total_signals,
            "source_adapters": self.source_adapters,
            "registered_adapters": self.registered_adapters,
            "adapter_health_score": self.adapter_health_score,
            "signal_usefulness_score": self.signal_usefulness_score,
            "corroboration_rate": self.corroboration_rate,
            "downstream_idea_conversion_rate": self.downstream_idea_conversion_rate,
            "feedback_approval_rate": self.feedback_approval_rate,
            "reliability_score": self.reliability_score,
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class SourceReliabilityReport:
    """Source reliability report grouped by signal source type."""

    generated_at: str
    signal_limit: int
    total_signals: int
    source_types: list[SourceReliabilityRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "signal_limit": self.signal_limit,
            "total_signals": self.total_signals,
            "source_types": [row.to_dict() for row in self.source_types],
        }


def build_source_reliability_report(
    store: Store,
    *,
    signal_limit: int = DEFAULT_SIGNAL_LIMIT,
) -> SourceReliabilityReport:
    """Build a deterministic source reliability report grouped by source type."""
    if signal_limit < 1:
        raise ValueError("signal_limit must be at least 1")

    signals = store.get_signals(limit=signal_limit)
    if not signals:
        return SourceReliabilityReport(
            generated_at=_now_iso(),
            signal_limit=signal_limit,
            total_signals=0,
            source_types=[],
        )

    registered = set(list_adapters())
    latest_fetch_status = _latest_fetch_status_by_adapter(store)
    circuit_score = _circuit_score_by_adapter(registered | {s.source_adapter for s in signals})
    approval_stats = store.get_adapter_approval_stats()

    signals_by_type: dict[str, list[Signal]] = defaultdict(list)
    for signal in signals:
        source_type = signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type)
        signals_by_type[source_type].append(signal)

    insight_signal_ids = _insight_signal_ids(store)
    idea_signal_ids = _idea_signal_ids(store)
    corroborated_signal_ids = _corroborated_signal_ids(signals)

    rows = [
        _build_row(
            source_type,
            source_signals,
            registered=registered,
            latest_fetch_status=latest_fetch_status,
            circuit_score=circuit_score,
            approval_stats=approval_stats,
            insight_signal_ids=insight_signal_ids,
            idea_signal_ids=idea_signal_ids,
            corroborated_signal_ids=corroborated_signal_ids,
        )
        for source_type, source_signals in signals_by_type.items()
    ]
    rows.sort(key=lambda row: (-row.reliability_score, row.source_type))

    return SourceReliabilityReport(
        generated_at=_now_iso(),
        signal_limit=signal_limit,
        total_signals=len(signals),
        source_types=rows,
    )


def _build_row(
    source_type: str,
    signals: list[Signal],
    *,
    registered: set[str],
    latest_fetch_status: dict[str, str],
    circuit_score: dict[str, float],
    approval_stats: dict[str, dict],
    insight_signal_ids: set[str],
    idea_signal_ids: set[str],
    corroborated_signal_ids: set[str],
) -> SourceReliabilityRow:
    total = len(signals)
    adapters = sorted({signal.source_adapter for signal in signals})
    registered_adapters = [adapter for adapter in adapters if adapter in registered]

    adapter_health_score = _round_rate(
        sum(
            _adapter_health_score(
                adapter,
                registered=adapter in registered,
                fetch_status=latest_fetch_status.get(adapter),
                circuit_score=circuit_score.get(adapter, 1.0),
            )
            for adapter in adapters
        )
        / max(len(adapters), 1)
    )
    signal_usefulness_score = _round_rate(
        sum(1 for signal in signals if signal.id in insight_signal_ids) / total
    )
    downstream_idea_conversion_rate = _round_rate(
        sum(1 for signal in signals if signal.id in idea_signal_ids) / total
    )
    corroboration_rate = _round_rate(
        sum(1 for signal in signals if signal.id in corroborated_signal_ids) / total
    )
    feedback_approval_rate = _weighted_approval_rate(adapters, approval_stats)

    reliability_score = _round_rate(
        (adapter_health_score * 0.25)
        + (signal_usefulness_score * 0.30)
        + (corroboration_rate * 0.25)
        + (downstream_idea_conversion_rate * 0.20)
    )

    reasons = _reason_strings(
        adapters=adapters,
        registered_adapters=registered_adapters,
        latest_fetch_status=latest_fetch_status,
        total_signals=total,
        signal_usefulness_score=signal_usefulness_score,
        corroboration_rate=corroboration_rate,
        downstream_idea_conversion_rate=downstream_idea_conversion_rate,
        feedback_approval_rate=feedback_approval_rate,
    )

    return SourceReliabilityRow(
        source_type=source_type,
        total_signals=total,
        source_adapters=adapters,
        registered_adapters=registered_adapters,
        adapter_health_score=adapter_health_score,
        signal_usefulness_score=signal_usefulness_score,
        corroboration_rate=corroboration_rate,
        downstream_idea_conversion_rate=downstream_idea_conversion_rate,
        feedback_approval_rate=feedback_approval_rate,
        reliability_score=reliability_score,
        reasons=reasons,
    )


def _adapter_health_score(
    adapter: str,
    *,
    registered: bool,
    fetch_status: str | None,
    circuit_score: float,
) -> float:
    registry_component = 1.0 if registered else 0.0
    fetch_component = 0.5
    if fetch_status == "ok":
        fetch_component = 1.0
    elif fetch_status == "error":
        fetch_component = 0.0
    return (registry_component + fetch_component + circuit_score) / 3.0


def _latest_fetch_status_by_adapter(store: Store) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for run in store.get_pipeline_runs(limit=50):
        adapter_metrics = run.get("adapter_metrics") or {}
        for adapter, metrics in adapter_metrics.items():
            if adapter not in statuses:
                statuses[adapter] = str(metrics.get("status") or "unknown")
    return statuses


def _circuit_score_by_adapter(adapter_names: set[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for snapshot in snapshot_circuit_breakers(adapter_names=sorted(adapter_names)):
        state = snapshot.state
        if state == "closed":
            score = 1.0
        elif state == "half_open":
            score = 0.5
        else:
            score = 0.0
        scores[snapshot.adapter_name] = score
    return scores


def _insight_signal_ids(store: Store) -> set[str]:
    ids: set[str] = set()
    for insight in store.get_insights(limit=10_000):
        ids.update(insight.evidence)
    return ids


def _idea_signal_ids(store: Store) -> set[str]:
    ids: set[str] = set()
    for unit in store.get_buildable_units(limit=10_000):
        ids.update(unit.evidence_signals)
    return ids


def _corroborated_signal_ids(signals: list[Signal]) -> set[str]:
    corroborated: set[str] = set()
    for cluster in triangulate(signals, max_clusters=max(len(signals), 1)):
        adapters = {signal.source_adapter for signal in cluster.signals}
        source_types = {
            signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type)
            for signal in cluster.signals
        }
        if len(adapters) > 1 or len(source_types) > 1:
            corroborated.update(signal.id for signal in cluster.signals)
    return corroborated


def _weighted_approval_rate(
    adapters: list[str],
    approval_stats: dict[str, dict],
) -> float | None:
    approved = 0
    total = 0
    for adapter in adapters:
        stats = approval_stats.get(adapter)
        if not stats:
            continue
        approved += int(stats.get("approved", 0))
        total += int(stats.get("total_feedbacked", 0))
    if total == 0:
        return None
    return _round_rate(approved / total)


def _reason_strings(
    *,
    adapters: list[str],
    registered_adapters: list[str],
    latest_fetch_status: dict[str, str],
    total_signals: int,
    signal_usefulness_score: float,
    corroboration_rate: float,
    downstream_idea_conversion_rate: float,
    feedback_approval_rate: float | None,
) -> list[str]:
    ok_count = sum(1 for adapter in adapters if latest_fetch_status.get(adapter) == "ok")
    error_count = sum(1 for adapter in adapters if latest_fetch_status.get(adapter) == "error")
    unknown_count = len(adapters) - ok_count - error_count

    reasons = [
        f"{len(registered_adapters)}/{len(adapters)} adapters are registered for {total_signals} active signals.",
        f"Latest fetch status: {ok_count} ok, {error_count} error, {unknown_count} unknown.",
        f"{_pct(signal_usefulness_score)} of signals are cited by synthesized insights.",
        f"{_pct(corroboration_rate)} of signals are corroborated by multi-source triangulation.",
        f"{_pct(downstream_idea_conversion_rate)} of signals convert into buildable idea evidence.",
    ]
    if feedback_approval_rate is not None:
        reasons.append(f"{_pct(feedback_approval_rate)} downstream idea approval rate for contributing adapters.")
    else:
        reasons.append("No approved/rejected downstream feedback is available for contributing adapters.")
    return reasons


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _round_rate(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
