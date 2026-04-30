"""Portfolio evidence concentration report."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal


SCHEMA_VERSION = "max.evidence_concentration.v1"
DEFAULT_LIMIT = 20
MAX_IDEAS_ANALYZED = 10_000

# Portfolio-level shares above these thresholds indicate brittle evidence sourcing.
SOURCE_ADAPTER_SHARE_THRESHOLD = 0.60
DOMAIN_TAG_SHARE_THRESHOLD = 0.70
SIGNAL_ROLE_SHARE_THRESHOLD = 0.70

_EXCLUDED_IDEA_STATUSES = {"rejected", "archived", "abandoned"}


def build_evidence_concentration_report(store: Store, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Summarize portfolio evidence concentration across generated/approved ideas."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    units = [
        unit
        for unit in store.get_buildable_units(limit=MAX_IDEAS_ANALYZED)
        if (unit.status or "").lower() not in _EXCLUDED_IDEA_STATUSES
    ]

    adapter_counts: Counter[str] = Counter()
    domain_tag_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    idea_rows: list[dict[str, Any]] = []
    ideas_with_evidence = 0
    total_evidence_links = 0

    for unit in units:
        signals = _resolved_signals(unit, store)
        if signals:
            ideas_with_evidence += 1
        total_evidence_links += len(signals)

        idea_adapter_counts = Counter(_adapter(signal) for signal in signals)
        idea_tag_counts = Counter(tag for signal in signals for tag in _domain_tags(signal))
        idea_role_counts = Counter(_role(signal) for signal in signals)

        adapter_counts.update(idea_adapter_counts)
        domain_tag_counts.update(idea_tag_counts)
        role_counts.update(idea_role_counts)

        idea_rows.append(
            _idea_concentration_row(
                unit,
                signal_count=len(signals),
                adapter_counts=idea_adapter_counts,
                domain_tag_counts=idea_tag_counts,
                role_counts=idea_role_counts,
            )
        )

    by_source_adapter = _share_rows(
        adapter_counts,
        total_evidence_links,
        key_name="source_adapter",
    )
    by_domain_tag = _share_rows(
        domain_tag_counts,
        sum(domain_tag_counts.values()),
        key_name="domain_tag",
    )
    by_signal_role = _share_rows(
        role_counts,
        total_evidence_links,
        key_name="signal_role",
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": limit,
        "thresholds": {
            "source_adapter_share": SOURCE_ADAPTER_SHARE_THRESHOLD,
            "domain_tag_share": DOMAIN_TAG_SHARE_THRESHOLD,
            "signal_role_share": SIGNAL_ROLE_SHARE_THRESHOLD,
        },
        "total_ideas": len(units),
        "ideas_with_evidence": ideas_with_evidence,
        "total_evidence_links": total_evidence_links,
        "by_source_adapter": by_source_adapter,
        "by_domain_tag": by_domain_tag,
        "by_signal_role": by_signal_role,
        "top_concentrated_ideas": _top_concentrated_ideas(idea_rows, limit),
        "recommendations": _recommendations(
            by_source_adapter=by_source_adapter,
            by_domain_tag=by_domain_tag,
            by_signal_role=by_signal_role,
        ),
    }


def _resolved_signals(unit: BuildableUnit, store: Store) -> list[Signal]:
    signal_ids = list(unit.evidence_signals)
    for insight_id in unit.inspiring_insights:
        insight = store.get_insight(insight_id)
        if insight:
            signal_ids.extend(insight.evidence)

    signals: list[Signal] = []
    seen: set[str] = set()
    for signal_id in signal_ids:
        if signal_id in seen:
            continue
        seen.add(signal_id)
        signal = store.get_signal(signal_id)
        if signal:
            signals.append(signal)
    return signals


def _adapter(signal: Signal) -> str:
    return _clean(signal.source_adapter) or "unspecified"


def _role(signal: Signal) -> str:
    return _clean(signal.signal_role) or "unclassified"


def _domain_tags(signal: Signal) -> list[str]:
    tags = [_clean(tag) for tag in signal.tags]
    return [tag for tag in tags if tag] or ["untagged"]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _share_rows(counts: Counter[str], total: int, *, key_name: str) -> list[dict[str, Any]]:
    return [
        {
            key_name: value,
            "count": count,
            "share": _share(count, total),
        }
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _share(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _dominant(counts: Counter[str], total: int) -> tuple[str | None, float]:
    if not counts or total <= 0:
        return None, 0.0
    value, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return value, _share(count, total)


def _idea_concentration_row(
    unit: BuildableUnit,
    *,
    signal_count: int,
    adapter_counts: Counter[str],
    domain_tag_counts: Counter[str],
    role_counts: Counter[str],
) -> dict[str, Any]:
    adapter, adapter_share = _dominant(adapter_counts, signal_count)
    domain_tag, domain_tag_share = _dominant(
        domain_tag_counts,
        sum(domain_tag_counts.values()),
    )
    role, role_share = _dominant(role_counts, signal_count)
    concentration_score = max(adapter_share, domain_tag_share, role_share)
    return {
        "idea_id": unit.id,
        "title": unit.title,
        "status": unit.status,
        "domain": unit.domain or "unspecified",
        "evidence_signal_count": signal_count,
        "dominant_source_adapter": adapter,
        "source_adapter_share": adapter_share,
        "dominant_domain_tag": domain_tag,
        "domain_tag_share": domain_tag_share,
        "dominant_signal_role": role,
        "signal_role_share": role_share,
        "concentration_score": concentration_score,
    }


def _top_concentrated_ideas(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            -float(row["concentration_score"]),
            -int(row["evidence_signal_count"]),
            row["idea_id"],
        ),
    )
    return ranked[:limit]


def _recommendations(
    *,
    by_source_adapter: list[dict[str, Any]],
    by_domain_tag: list[dict[str, Any]],
    by_signal_role: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    recommendations.extend(
        _dimension_recommendations(
            by_source_adapter,
            dimension="source_adapter",
            value_key="source_adapter",
            threshold=SOURCE_ADAPTER_SHARE_THRESHOLD,
            action="Add evidence from independent adapters before approving more ideas in this cluster.",
        )
    )
    recommendations.extend(
        _dimension_recommendations(
            by_domain_tag,
            dimension="domain_tag",
            value_key="domain_tag",
            threshold=DOMAIN_TAG_SHARE_THRESHOLD,
            action="Broaden discovery into adjacent domains or retag evidence with more specific domains.",
        )
    )
    recommendations.extend(
        _dimension_recommendations(
            by_signal_role,
            dimension="signal_role",
            value_key="signal_role",
            threshold=SIGNAL_ROLE_SHARE_THRESHOLD,
            action="Balance the portfolio with problem, solution, and market evidence before promoting ideas.",
        )
    )
    return recommendations


def _dimension_recommendations(
    rows: list[dict[str, Any]],
    *,
    dimension: str,
    value_key: str,
    threshold: float,
    action: str,
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    for row in rows:
        share = float(row["share"])
        if share <= threshold:
            continue
        value = str(row[value_key])
        recs.append(
            {
                "dimension": dimension,
                "value": value,
                "share": share,
                "threshold": threshold,
                "message": (
                    f"{share * 100:.1f}% of portfolio evidence links depend on "
                    f"{dimension} '{value}', above the {threshold * 100:.0f}% threshold."
                ),
                "action": action,
            }
        )
    return recs
