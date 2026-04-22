"""Evidence-chain graph assembly for API and MCP surfaces."""

from __future__ import annotations

from collections.abc import Callable

from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight
from max.types.signal import Signal


def _dt(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else value


def _idea_node(unit: BuildableUnit) -> dict:
    return {
        "id": unit.id,
        "title": unit.title,
        "one_liner": unit.one_liner,
        "category": unit.category,
        "domain": unit.domain,
        "status": unit.status,
        "problem": unit.problem,
        "solution": unit.solution,
        "target_users": unit.target_users,
        "specific_user": unit.specific_user,
        "buyer": unit.buyer,
        "workflow_context": unit.workflow_context,
        "value_proposition": unit.value_proposition,
        "quality_score": unit.quality_score,
        "novelty_score": unit.novelty_score,
        "usefulness_score": unit.usefulness_score,
        "created_at": _dt(unit.created_at),
        "updated_at": _dt(unit.updated_at),
    }


def _insight_node(insight: Insight) -> dict:
    category = insight.category.value if hasattr(insight.category, "value") else insight.category
    return {
        "id": insight.id,
        "category": category,
        "title": insight.title,
        "summary": insight.summary,
        "confidence": insight.confidence,
        "domains": insight.domains,
        "implications": insight.implications,
        "time_horizon": insight.time_horizon,
        "created_at": _dt(insight.created_at),
    }


def _signal_node(signal: Signal) -> dict:
    source_type = signal.source_type.value if hasattr(signal.source_type, "value") else signal.source_type
    return {
        "id": signal.id,
        "source_type": source_type,
        "source_adapter": signal.source_adapter,
        "signal_role": signal.signal_role,
        "title": signal.title,
        "content": signal.content,
        "url": signal.url,
        "author": signal.author,
        "published_at": _dt(signal.published_at),
        "fetched_at": _dt(signal.fetched_at),
        "tags": signal.tags,
        "credibility": signal.credibility,
        "metadata": signal.metadata,
    }


def build_evidence_chain_graph(
    unit: BuildableUnit,
    store: Store,
    *,
    insight_converter: Callable[[Insight], dict] | None = None,
    signal_converter: Callable[[Signal], dict] | None = None,
) -> dict:
    """Build idea -> insight -> signal graph with typed edges."""
    insights: list[dict] = []
    signals: list[dict] = []
    edges: list[dict] = []
    seen_insights: set[str] = set()
    seen_signals: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    to_insight_node = insight_converter or _insight_node
    to_signal_node = signal_converter or _signal_node

    def add_edge(source: str, target: str, edge_type: str, role: str) -> None:
        key = (source, target, edge_type)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": source, "target": target, "type": edge_type, "role": role})

    def add_signal(signal: Signal) -> None:
        if signal.id in seen_signals:
            return
        seen_signals.add(signal.id)
        signals.append(to_signal_node(signal))

    for insight_id in unit.inspiring_insights:
        insight = store.get_insight(insight_id)
        if not insight:
            continue
        if insight.id not in seen_insights:
            seen_insights.add(insight.id)
            insights.append(to_insight_node(insight))
        add_edge(unit.id, insight.id, "inspired_by", "inspires")

        for signal_id in insight.evidence:
            signal = store.get_signal(signal_id)
            if not signal:
                continue
            add_signal(signal)
            add_edge(insight.id, signal.id, "supported_by", "evidenced_by")

    for signal_id in unit.evidence_signals:
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        add_signal(signal)
        add_edge(unit.id, signal.id, "direct_evidence", "evidenced_by")

    return {
        "idea_id": unit.id,
        "idea": _idea_node(unit),
        "insights": insights,
        "signals": signals,
        "edges": edges,
    }
