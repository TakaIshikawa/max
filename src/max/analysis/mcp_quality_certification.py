"""Deterministic MCP server quality certification reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from max.analysis.mcp_capability_coverage import (
    CAPABILITY_CATEGORIES,
    MCP_SOURCE_ADAPTERS,
    classify_mcp_capability,
)
from max.analysis.source_reliability import build_source_reliability_report
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation
from max.types.signal import Signal

DEFAULT_SIGNAL_LIMIT = 10_000

_SECURITY_SEVERITY_WEIGHT = {
    "critical": 1.0,
    "high": 0.7,
    "medium": 0.35,
    "moderate": 0.35,
    "low": 0.15,
    "info": 0.05,
    "informational": 0.05,
}


class MCPQualityCertificationNotFound(ValueError):
    """Raised when a scoped certification references an unknown idea."""


@dataclass(frozen=True)
class MCPQualityEvidenceReference:
    """Reference to a source of certification evidence."""

    kind: str
    id: str
    title: str
    source_adapter: str | None = None
    source_type: str | None = None
    url: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "title": self.title,
            "source_adapter": self.source_adapter,
            "source_type": self.source_type,
            "url": self.url,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MCPQualityScoreComponent:
    """Weighted score component for the certification."""

    name: str
    score: float
    weight: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class MCPQualityCertificationReport:
    """MCP quality certification result."""

    generated_at: str
    scope: str
    idea_id: str | None
    score: float
    grade: str
    blocked: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""
    score_components: list[MCPQualityScoreComponent] = field(default_factory=list)
    evidence_references: list[MCPQualityEvidenceReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "scope": self.scope,
            "idea_id": self.idea_id,
            "score": self.score,
            "grade": self.grade,
            "blocked": self.blocked,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "summary": self.summary,
            "score_components": [component.to_dict() for component in self.score_components],
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
        }


def build_mcp_quality_certification_report(
    store: Store,
    *,
    idea_id: str | None = None,
    signal_limit: int = DEFAULT_SIGNAL_LIMIT,
) -> MCPQualityCertificationReport:
    """Build a deterministic MCP quality certification report.

    Global reports evaluate all active MCP registry/security signals and MCP server ideas.
    Idea-scoped reports evaluate only the idea, its evidence signals, and its evaluation.
    """
    if signal_limit < 1:
        raise ValueError("signal_limit must be at least 1")

    idea: BuildableUnit | None = None
    evaluation: UtilityEvaluation | None = None
    if idea_id is not None:
        idea = store.get_buildable_unit(idea_id)
        if idea is None:
            raise MCPQualityCertificationNotFound(f"Idea not found: {idea_id}")
        evaluation = store.get_evaluation(idea_id)

    signals = _scoped_mcp_signals(store, idea=idea, signal_limit=signal_limit)
    ideas = [idea] if idea is not None else _mcp_ideas(store)

    capability_score, capability_explanation, categories = _capability_component(signals, ideas)
    reliability_score, reliability_explanation = _reliability_component(store, signals)
    security_score, security_explanation, security_blockers, security_warnings = (
        _security_component(signals)
    )
    idea_score, idea_explanation, idea_warnings = _idea_component(ideas, evaluation, store)

    components = [
        MCPQualityScoreComponent(
            name="capability",
            score=capability_score,
            weight=0.30,
            explanation=capability_explanation,
        ),
        MCPQualityScoreComponent(
            name="reliability",
            score=reliability_score,
            weight=0.25,
            explanation=reliability_explanation,
        ),
        MCPQualityScoreComponent(
            name="security",
            score=security_score,
            weight=0.20,
            explanation=security_explanation,
        ),
        MCPQualityScoreComponent(
            name="idea_evaluation",
            score=idea_score,
            weight=0.25,
            explanation=idea_explanation,
        ),
    ]
    score = _round_score(sum(component.score * component.weight for component in components))

    blockers: list[str] = []
    warnings: list[str] = []
    if not signals:
        blockers.append("No MCP registry or security signals are available for this scope.")
    if idea is not None and not _is_mcp_idea(idea):
        warnings.append("Scoped idea is not explicitly categorized or described as MCP-related.")
    blockers.extend(security_blockers)
    warnings.extend(security_warnings)
    warnings.extend(idea_warnings)
    if categories == ["unknown"]:
        warnings.append("Capability evidence could not be mapped beyond the unknown category.")

    blocked = bool(blockers)
    grade = "blocked" if blocked else _grade(score)
    if blocked:
        score = min(score, 59.0)

    return MCPQualityCertificationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        scope="idea" if idea_id else "global",
        idea_id=idea_id,
        score=score,
        grade=grade,
        blocked=blocked,
        blockers=sorted(dict.fromkeys(blockers)),
        warnings=sorted(dict.fromkeys(warnings)),
        summary=_summary(score=score, grade=grade, blocked=blocked, component_count=len(components)),
        score_components=components,
        evidence_references=_evidence_references(signals, ideas, evaluation, store),
    )


def _scoped_mcp_signals(
    store: Store,
    *,
    idea: BuildableUnit | None,
    signal_limit: int,
) -> list[Signal]:
    if idea is not None:
        evidence_ids = set(idea.evidence_signals)
        signals = [
            signal
            for signal_id in sorted(evidence_ids)
            if (signal := store.get_signal(signal_id)) is not None and _is_mcp_signal(signal)
        ]
        return sorted(signals, key=lambda signal: signal.id)

    return sorted(
        [signal for signal in store.get_signals(limit=signal_limit) if _is_mcp_signal(signal)],
        key=lambda signal: signal.id,
    )


def _mcp_ideas(store: Store) -> list[BuildableUnit]:
    return sorted(
        [unit for unit in store.get_buildable_units(limit=DEFAULT_SIGNAL_LIMIT) if _is_mcp_idea(unit)],
        key=lambda unit: unit.id,
    )


def _capability_component(
    signals: list[Signal],
    ideas: list[BuildableUnit],
) -> tuple[float, str, list[str]]:
    categories = sorted(
        {
            classify_mcp_capability(_signal_record(signal))
            for signal in signals
        },
        key=lambda category: CAPABILITY_CATEGORIES.index(category),
    )
    known_categories = [category for category in categories if category != "unknown"]
    known_signal_count = sum(
        1 for signal in signals if classify_mcp_capability(_signal_record(signal)) != "unknown"
    )
    known_ratio = known_signal_count / len(signals) if signals else 0.0
    diversity_ratio = min(len(known_categories) / 3, 1.0)
    idea_fit = 1.0 if any(_is_mcp_idea(unit) for unit in ideas) else 0.0
    score = _round_score(((known_ratio * 0.45) + (diversity_ratio * 0.45) + (idea_fit * 0.10)) * 100)
    if not signals:
        return 0.0, "No MCP capability signals are present.", ["unknown"]
    explanation = (
        f"{len(known_categories)} known capability categories from {len(signals)} MCP signals; "
        f"{known_signal_count}/{len(signals)} signals classified beyond unknown."
    )
    return score, explanation, categories or ["unknown"]


def _reliability_component(store: Store, signals: list[Signal]) -> tuple[float, str]:
    if not signals:
        return 0.0, "No signal evidence is available to assess source reliability."

    adapters = {signal.source_adapter for signal in signals}
    source_types = {
        signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type)
        for signal in signals
    }
    report = build_source_reliability_report(
        store,
        signal_limit=DEFAULT_SIGNAL_LIMIT,
        source_adapters=adapters,
        min_signal_count=1,
    )
    matching_rows = [row for row in report.source_types if row.source_type in source_types]
    if matching_rows:
        score = _round_score(
            sum(row.reliability_score for row in matching_rows) / len(matching_rows) * 100
        )
        explanation = (
            f"{len(adapters)} adapters represented; average source reliability "
            f"{score:.1f}/100 across {len(matching_rows)} source types."
        )
        return score, explanation

    credibility = sum(signal.credibility for signal in signals) / len(signals)
    return (
        _round_score(credibility * 100),
        f"{len(adapters)} adapters represented; fell back to average signal credibility.",
    )


def _security_component(signals: list[Signal]) -> tuple[float, str, list[str], list[str]]:
    security_signals = [signal for signal in signals if _is_security_signal(signal)]
    if not security_signals:
        return 100.0, "No MCP security findings are present in scope.", [], []

    severity_counts: dict[str, int] = {}
    risk = 0.0
    blockers: list[str] = []
    warnings: list[str] = []
    for signal in security_signals:
        severity = _security_severity(signal)
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        risk += _SECURITY_SEVERITY_WEIGHT.get(severity, 0.25)

    if severity_counts.get("critical", 0):
        blockers.append("Critical MCP security findings block certification.")
    if severity_counts.get("high", 0) and len(security_signals) >= 2:
        blockers.append("Multiple scoped MCP security findings include high severity risk.")
    elif severity_counts.get("high", 0):
        warnings.append("High severity MCP security finding lowers certification grade.")
    if severity_counts.get("medium", 0) or severity_counts.get("moderate", 0):
        warnings.append("Medium severity MCP security findings require remediation tracking.")

    score = _round_score(max(0.0, 100.0 - (risk * 35.0)))
    counts = ", ".join(f"{severity}:{count}" for severity, count in sorted(severity_counts.items()))
    return score, f"{len(security_signals)} security findings considered ({counts}).", blockers, warnings


def _idea_component(
    ideas: list[BuildableUnit],
    evaluation: UtilityEvaluation | None,
    store: Store,
) -> tuple[float, str, list[str]]:
    warnings: list[str] = []
    if evaluation is not None:
        score = _round_score(evaluation.overall_score)
        if evaluation.recommendation in {"no", "strong_no"}:
            warnings.append("Idea evaluation recommends against pursuing this idea.")
        return score, f"Idea evaluation contributes overall score {score:.1f}/100.", warnings

    evaluated_scores = [
        ev.overall_score
        for unit in ideas
        if (ev := store.get_evaluation(unit.id)) is not None
    ]
    if evaluated_scores:
        score = _round_score(sum(evaluated_scores) / len(evaluated_scores))
        return score, f"{len(evaluated_scores)} MCP idea evaluations averaged into the score.", warnings

    quality_scores = [unit.quality_score * 10 for unit in ideas if unit.quality_score > 0]
    if quality_scores:
        score = _round_score(sum(quality_scores) / len(quality_scores))
        warnings.append("No utility evaluation exists; used idea quality_score as fallback.")
        return score, f"{len(quality_scores)} MCP idea quality scores used as fallback.", warnings

    warnings.append("No MCP idea evaluation data is available for this scope.")
    return 50.0, "No idea evaluation data is available; neutral midpoint applied.", warnings


def _evidence_references(
    signals: list[Signal],
    ideas: list[BuildableUnit],
    evaluation: UtilityEvaluation | None,
    store: Store,
) -> list[MCPQualityEvidenceReference]:
    references: list[MCPQualityEvidenceReference] = []
    for signal in sorted(signals, key=lambda item: item.id):
        references.append(
            MCPQualityEvidenceReference(
                kind="signal",
                id=signal.id,
                title=signal.title,
                source_adapter=signal.source_adapter,
                source_type=(
                    signal.source_type.value
                    if hasattr(signal.source_type, "value")
                    else str(signal.source_type)
                ),
                url=signal.url,
                reason=_signal_reason(signal),
            )
        )
    for idea in sorted(ideas, key=lambda item: item.id):
        references.append(
            MCPQualityEvidenceReference(
                kind="idea",
                id=idea.id,
                title=idea.title,
                reason=f"status:{idea.status}; category:{idea.category}",
            )
        )
    if evaluation is not None:
        references.append(
            MCPQualityEvidenceReference(
                kind="evaluation",
                id=evaluation.buildable_unit_id,
                title="Utility evaluation",
                reason=f"overall_score:{evaluation.overall_score:.1f}; recommendation:{evaluation.recommendation}",
            )
        )
    else:
        for idea in sorted(ideas, key=lambda item: item.id):
            if (idea_evaluation := store.get_evaluation(idea.id)) is None:
                continue
            references.append(
                MCPQualityEvidenceReference(
                    kind="evaluation",
                    id=idea_evaluation.buildable_unit_id,
                    title="Utility evaluation",
                    reason=(
                        f"overall_score:{idea_evaluation.overall_score:.1f}; "
                        f"recommendation:{idea_evaluation.recommendation}"
                    ),
                )
            )
    return references


def _is_mcp_signal(signal: Signal) -> bool:
    text = _signal_text(signal)
    source_type = signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type)
    return (
        signal.source_adapter in MCP_SOURCE_ADAPTERS
        or signal.source_adapter == "mcp_security_import"
        or source_type == "security"
        and "mcp" in text
        or "mcp" in text
        or "model context protocol" in text
    )


def _is_security_signal(signal: Signal) -> bool:
    source_type = signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type)
    return source_type == "security" or signal.source_adapter == "mcp_security_import"


def _security_severity(signal: Signal) -> str:
    severity = str(signal.metadata.get("severity") or "").strip().casefold()
    if severity:
        return severity
    for tag in signal.tags:
        if str(tag).startswith("severity:"):
            return str(tag).split(":", 1)[1].casefold()
    return "unknown"


def _is_mcp_idea(unit: BuildableUnit) -> bool:
    text = " ".join(
        [
            unit.title,
            unit.one_liner,
            unit.category,
            unit.problem,
            unit.solution,
            unit.tech_approach,
            unit.domain,
            " ".join(unit.domain_risks),
        ]
    ).casefold()
    return unit.category == "mcp_server" or "mcp" in text or "model context protocol" in text


def _signal_record(signal: Signal) -> dict[str, Any]:
    return {
        "id": signal.id,
        "source_adapter": signal.source_adapter,
        "title": signal.title,
        "content": signal.content,
        "tags": signal.tags,
        "metadata": signal.metadata,
    }


def _signal_text(signal: Signal) -> str:
    return " ".join(
        [
            signal.title,
            signal.content,
            " ".join(signal.tags),
            " ".join(str(value) for value in signal.metadata.values() if value is not None),
        ]
    ).casefold()


def _signal_reason(signal: Signal) -> str:
    if _is_security_signal(signal):
        return f"security:{_security_severity(signal)}"
    return f"capability:{classify_mcp_capability(_signal_record(signal))}"


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _summary(*, score: float, grade: str, blocked: bool, component_count: int) -> str:
    status = "blocked" if blocked else f"grade {grade}"
    return f"MCP quality certification is {status} with score {score:.1f}/100 across {component_count} components."


def _round_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)
