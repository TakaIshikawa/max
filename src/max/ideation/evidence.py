"""Evidence packs for domain-focused ideation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from max.types.insight import Insight
from max.types.signal import Signal

if TYPE_CHECKING:
    from max.analysis.gap_detector import Gap
    from max.profiles.schema import DomainContext
    from max.store.db import Store


@dataclass
class EvidencePack:
    """Compact context used by the ideation quality loop."""

    domain_name: str = ""
    target_segments: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    buyer_roles: list[str] = field(default_factory=list)
    hard_constraints: list[str] = field(default_factory=list)
    bad_idea_patterns: list[str] = field(default_factory=list)
    good_idea_criteria: list[str] = field(default_factory=list)
    insights: list[dict] = field(default_factory=list)
    problem_signals: list[dict] = field(default_factory=list)
    solution_signals: list[dict] = field(default_factory=list)
    market_signals: list[dict] = field(default_factory=list)
    validated_gaps: list[dict] = field(default_factory=list)
    rejected_patterns: list[str] = field(default_factory=list)
    successful_patterns: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def _signal_summary(signal: Signal) -> dict:
    return {
        "id": signal.id,
        "title": signal.title,
        "source": signal.source_adapter,
        "role": signal.signal_role,
        "credibility": signal.credibility,
        "content": signal.content[:500],
        "url": signal.url,
    }


def _insight_summary(insight: Insight) -> dict:
    return {
        "id": insight.id,
        "title": insight.title,
        "summary": insight.summary,
        "confidence": insight.confidence,
        "domains": insight.domains,
        "evidence": insight.evidence,
    }


def _gap_summary(gap: Gap) -> dict:
    return {
        "topic": gap.topic,
        "gap_score": gap.gap_score,
        "source_diversity": gap.source_diversity,
        "problem_signal_ids": [s.id for s in gap.problem_signals],
        "solution_signal_ids": [s.id for s in gap.solution_signals],
    }


def _patterns_from_feedback(
    store: Store,
    *,
    domain: str | None = None,
    limit: int = 50,
) -> tuple[list[str], list[str]]:
    rejected: list[str] = []
    successful: list[str] = []
    if hasattr(store, "get_idea_memory"):
        memory_rows = store.get_idea_memory(domain=domain, limit=limit)
        for row in memory_rows:
            pattern = row.get("pattern") or ""
            if not pattern:
                continue
            if row.get("outcome") in ("rejected", "quality_rejected"):
                rejected.append(pattern)
            elif row.get("outcome") in ("approved", "quality_passed", "published"):
                successful.append(pattern)
    for row in store.get_feedback_log(limit=limit):
        title = row.get("title") or ""
        reason = row.get("reason") or ""
        pattern = f"{title}: {reason}".strip(": ")
        if not pattern:
            continue
        if row.get("outcome") in ("rejected", "abandoned"):
            rejected.append(pattern)
        elif row.get("outcome") in ("approved", "published"):
            successful.append(pattern)
    return rejected[:10], successful[:10]


def build_evidence_pack(
    *,
    insights: list[Insight],
    store: Store,
    domain: DomainContext | None = None,
    gaps: list[Gap] | None = None,
    signal_limit: int = 30,
) -> EvidencePack:
    """Build structured evidence and domain context for idea generation."""
    pack = EvidencePack(
        domain_name=domain.name if domain else "",
        target_segments=domain.target_segments if domain else [],
        workflows=domain.workflows if domain else [],
        buyer_roles=domain.buyer_roles if domain else [],
        hard_constraints=domain.hard_constraints if domain else [],
        bad_idea_patterns=domain.bad_idea_patterns if domain else [],
        good_idea_criteria=domain.good_idea_criteria if domain else [],
        insights=[_insight_summary(i) for i in insights[:20]],
        validated_gaps=[_gap_summary(g) for g in (gaps or [])[:10]],
    )

    signals = store.get_signals(limit=signal_limit)
    for signal in signals:
        role = signal.signal_role
        if role == "problem":
            pack.problem_signals.append(_signal_summary(signal))
        elif role == "solution":
            pack.solution_signals.append(_signal_summary(signal))
        elif role == "market":
            pack.market_signals.append(_signal_summary(signal))

    pack.rejected_patterns, pack.successful_patterns = _patterns_from_feedback(
        store, domain=pack.domain_name or None,
    )
    return pack
