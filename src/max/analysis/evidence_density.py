"""Evidence density report for buildable ideas."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from max.server.evidence_chain import build_evidence_chain_graph
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _timestamp(signal: dict) -> datetime | None:
    return _parse_dt(signal.get("published_at")) or _parse_dt(signal.get("fetched_at"))


def _count_key(value: Any) -> str:
    return str(value or "unspecified")


def _density_score(
    *,
    signal_count: int,
    insight_count: int,
    source_adapter_count: int,
    source_type_count: int,
    average_credibility: float | None,
    missing_reference_count: int,
) -> float:
    """Return a compact 0-100 density score from volume, diversity, and quality."""
    evidence_volume = min(signal_count / 5, 1.0)
    insight_volume = min(insight_count / 3, 1.0)
    adapter_diversity = min(source_adapter_count / 3, 1.0)
    type_diversity = min(source_type_count / 3, 1.0)
    credibility = average_credibility if average_credibility is not None else 0.0

    raw = (
        evidence_volume * 0.40
        + insight_volume * 0.20
        + adapter_diversity * 0.15
        + type_diversity * 0.10
        + credibility * 0.15
    )
    penalty = min(missing_reference_count * 0.08, 0.40)
    return round(max(0.0, raw - penalty) * 100, 1)


def build_evidence_density_report(unit: BuildableUnit, store: Store) -> dict:
    """Summarize evidence density for an idea using its evidence-chain graph."""
    graph = build_evidence_chain_graph(unit, store)
    signals = graph["signals"]
    insights = graph["insights"]

    by_source_adapter = Counter(_count_key(signal.get("source_adapter")) for signal in signals)
    by_source_type = Counter(_count_key(signal.get("source_type")) for signal in signals)
    by_signal_role = Counter(_count_key(signal.get("signal_role")) for signal in signals)

    credibility_values = [
        float(signal["credibility"])
        for signal in signals
        if signal.get("credibility") is not None
    ]
    average_credibility = (
        round(sum(credibility_values) / len(credibility_values), 3)
        if credibility_values
        else None
    )

    evidence_timestamps = [ts for signal in signals if (ts := _timestamp(signal))]

    missing_insight_ids: list[str] = []
    missing_signal_ids: list[str] = []
    warnings: list[str] = []

    for insight_id in unit.inspiring_insights:
        insight = store.get_insight(insight_id)
        if not insight:
            missing_insight_ids.append(insight_id)
            continue
        for signal_id in insight.evidence:
            if not store.get_signal(signal_id):
                missing_signal_ids.append(signal_id)

    for signal_id in unit.evidence_signals:
        if not store.get_signal(signal_id):
            missing_signal_ids.append(signal_id)

    missing_insight_ids = list(dict.fromkeys(missing_insight_ids))
    missing_signal_ids = list(dict.fromkeys(missing_signal_ids))

    if missing_insight_ids:
        warnings.append(
            "Missing inspiring insight(s): " + ", ".join(missing_insight_ids)
        )
    if missing_signal_ids:
        warnings.append("Missing evidence signal(s): " + ", ".join(missing_signal_ids))
    if not signals:
        warnings.append("No evidence signals resolved for this idea.")
    if not insights and unit.inspiring_insights:
        warnings.append("No inspiring insights resolved for this idea.")

    signal_count = len(signals)
    insight_count = len(insights)
    missing_reference_count = len(missing_insight_ids) + len(missing_signal_ids)

    return {
        "idea_id": unit.id,
        "signal_count": signal_count,
        "insight_count": insight_count,
        "counts_by_source_adapter": dict(sorted(by_source_adapter.items())),
        "counts_by_source_type": dict(sorted(by_source_type.items())),
        "counts_by_signal_role": dict(sorted(by_signal_role.items())),
        "average_credibility": average_credibility,
        "newest_evidence_timestamp": max(evidence_timestamps).isoformat()
        if evidence_timestamps
        else None,
        "oldest_evidence_timestamp": min(evidence_timestamps).isoformat()
        if evidence_timestamps
        else None,
        "missing_evidence_warnings": warnings,
        "missing_insight_ids": missing_insight_ids,
        "missing_signal_ids": missing_signal_ids,
        "density_score": _density_score(
            signal_count=signal_count,
            insight_count=insight_count,
            source_adapter_count=len(by_source_adapter),
            source_type_count=len(by_source_type),
            average_credibility=average_credibility,
            missing_reference_count=missing_reference_count,
        ),
    }
