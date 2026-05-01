"""Evidence quality scorecard for persisted synthesized design briefs."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from max.analysis.design_brief_evidence_matrix import (
    build_design_brief_evidence_matrix,
    _collect_evidence,
    _source_ideas,
)

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.design_brief.evidence_quality_scorecard.v1"
KIND = "max.design_brief.evidence_quality_scorecard"

DIMENSION_WEIGHTS: dict[str, float] = {
    "evidence_volume": 0.22,
    "source_diversity": 0.18,
    "recency": 0.14,
    "role_balance": 0.16,
    "contradiction_risk": 0.14,
    "traceability": 0.16,
}

ROLE_GROUPS: dict[str, set[str]] = {
    "problem": {"problem", "pain", "gap"},
    "market": {"market", "buyer", "trend", "timing"},
    "workflow": {"workflow", "solution"},
    "risk": {"risk", "security", "failure"},
    "validation": {"validation", "experiment", "survey"},
}

CONTRADICTION_TERMS = (
    "contradict",
    "conflict",
    "invalidated",
    "rejected",
    "not willing",
    "no budget",
    "obsolete",
    "false positive",
)


def build_design_brief_evidence_quality_scorecard(
    store: Store,
    design_brief: dict[str, Any],
    *,
    evidence_matrix: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic evidence quality scorecard for build execution readiness."""

    generated = generated_at or datetime.now(timezone.utc).isoformat()
    matrix = evidence_matrix or build_design_brief_evidence_matrix(
        store,
        design_brief,
        generated_at=generated,
    )
    source_ideas = _source_ideas(store, design_brief)
    evidence = _collect_evidence(store, source_ideas)

    context = {
        "generated_at": generated,
        "matrix": matrix,
        "source_ideas": source_ideas,
        "signals": evidence["signals"],
        "insight_signal_ids": evidence["insight_signal_ids"],
    }

    dimensions = [
        _score_evidence_volume(context),
        _score_source_diversity(context),
        _score_recency(context),
        _score_role_balance(context, design_brief),
        _score_contradiction_risk(context),
        _score_traceability(context, design_brief),
    ]
    overall_score = _overall_score(dimensions)
    blockers = _blockers(dimensions)
    warnings = _warnings(dimensions)
    band = _band(overall_score, blockers)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": generated,
            "evidence_matrix_schema_version": matrix["schema_version"],
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": design_brief.get("source_idea_ids", []),
        },
        "summary": {
            "overall_score": overall_score,
            "band": band,
            "confidence": _confidence(overall_score, blockers),
            "recommendation": _recommendation(band),
        },
        "dimension_scores": dimensions,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_next_evidence_actions": _recommended_actions(dimensions, blockers),
        "evidence_refs": _evidence_refs(context),
    }


def render_design_brief_evidence_quality_scorecard(
    scorecard: dict[str, Any],
    fmt: str = "json",
) -> str:
    """Render an evidence quality scorecard as JSON or Markdown."""

    if fmt == "json":
        return json.dumps(scorecard, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported evidence quality scorecard format: {fmt}")

    brief = scorecard["design_brief"]
    summary = scorecard["summary"]
    lines = [
        f"# Evidence Quality Scorecard: {brief['title']}",
        "",
        f"Schema: `{scorecard['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Overall score: {summary['overall_score']}/100",
        f"Band: `{summary['band']}`",
        f"Confidence: `{summary['confidence']}`",
        f"Recommendation: {summary['recommendation']}",
        "",
        "## Dimension Scores",
        "",
    ]

    for dimension in scorecard["dimension_scores"]:
        lines.extend(
            [
                f"### {dimension['label']}",
                "",
                f"- **Score**: {dimension['score']}/100",
                f"- **Weight**: {dimension['weight']:.2f}",
                f"- **Summary**: {dimension['summary']}",
                f"- **Evidence refs**: {_inline_ids(dimension['evidence_refs'])}",
                "",
            ]
        )

    lines.extend(["## Blockers", ""])
    lines.extend(f"- {item}" for item in scorecard["blockers"] or ["None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in scorecard["warnings"] or ["None"])
    lines.extend(["", "## Recommended Next Evidence Actions", ""])
    lines.extend(f"- {item}" for item in scorecard["recommended_next_evidence_actions"])

    refs = scorecard["evidence_refs"]
    lines.extend(
        [
            "",
            "## Evidence References",
            "",
            f"- **Source ideas**: {_inline_ids(refs['source_idea_ids'])}",
            f"- **Signals**: {_inline_ids(refs['signal_ids'])}",
            f"- **Insights**: {_inline_ids(refs['insight_ids'])}",
            f"- **Evidence matrix rows**: {_inline_ids(refs['evidence_matrix_rows'])}",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def _score_evidence_volume(context: dict[str, Any]) -> dict[str, Any]:
    signals = context["signals"]
    source_ideas = context["source_ideas"]
    insight_ids = context["insight_signal_ids"]
    matrix_rows = context["matrix"]["rows"]
    supported_rows = [
        row
        for row in matrix_rows
        if row["supporting_signal_ids"] and row["evidence_strength"] in {"moderate", "strong"}
    ]
    score = min(
        100,
        len(signals) * 14
        + len(source_ideas) * 12
        + len(insight_ids) * 10
        + len(supported_rows) * 4,
    )
    return _dimension(
        "evidence_volume",
        "Evidence Volume",
        score,
        (
            f"{len(signals)} signal(s), {len(source_ideas)} source idea(s), "
            f"{len(insight_ids)} insight link(s), and {len(supported_rows)} supported claim row(s)."
        ),
        _refs(context, signal_ids=signals.keys(), source_idea_ids=[idea["id"] for idea in source_ideas]),
    )


def _score_source_diversity(context: dict[str, Any]) -> dict[str, Any]:
    signals = context["signals"]
    adapters = {
        str(getattr(signal, "source_adapter", "") or "")
        for signal in signals.values()
        if getattr(signal, "source_adapter", "")
    }
    source_types = {_source_type(signal) for signal in signals.values() if _source_type(signal)}
    score = min(100, len(adapters) * 28 + len(source_types) * 18 + min(len(context["source_ideas"]), 3) * 8)
    return _dimension(
        "source_diversity",
        "Source Diversity",
        score,
        f"{len(adapters)} adapter(s), {len(source_types)} source type(s), and {len(context['source_ideas'])} source idea(s).",
        _refs(context, signal_ids=signals.keys(), source_idea_ids=[idea["id"] for idea in context["source_ideas"]]),
    )


def _score_recency(context: dict[str, Any]) -> dict[str, Any]:
    signals = context["signals"]
    if not signals:
        return _dimension(
            "recency",
            "Recency",
            20,
            "No persisted signals are available to assess freshness.",
            _refs(context),
        )

    generated_at = _parse_datetime(context["generated_at"])
    ages = []
    for signal in signals.values():
        signal_time = getattr(signal, "published_at", None) or getattr(signal, "fetched_at", None)
        parsed = _parse_datetime(signal_time)
        if parsed is not None and generated_at is not None:
            ages.append(max((generated_at - parsed).days, 0))

    if not ages:
        score = 45
        summary = "Signals are present but have no parseable timestamp."
    else:
        recent = sum(1 for age in ages if age <= 90)
        currentish = sum(1 for age in ages if age <= 180)
        stale = sum(1 for age in ages if age > 365)
        score = min(100, round((recent / len(ages)) * 70 + (currentish / len(ages)) * 25 + 5))
        score = max(25, score - stale * 10)
        summary = f"{recent}/{len(ages)} signal(s) are <=90 days old; {stale} are >365 days old."

    return _dimension("recency", "Recency", score, summary, _refs(context, signal_ids=signals.keys()))


def _score_role_balance(context: dict[str, Any], design_brief: dict[str, Any]) -> dict[str, Any]:
    roles = _role_counts(context["signals"].values())
    covered_groups = {
        group
        for group, expected in ROLE_GROUPS.items()
        if expected & set(roles)
    }
    populated_brief_fields = sum(
        1
        for field in (
            "buyer",
            "specific_user",
            "workflow_context",
            "why_this_now",
            "validation_plan",
            "risks",
        )
        if _has_value(design_brief.get(field))
    )
    score = min(100, len(covered_groups) * 14 + populated_brief_fields * 5)
    return _dimension(
        "role_balance",
        "Role Balance",
        score,
        (
            f"Evidence covers {len(covered_groups)}/{len(ROLE_GROUPS)} role group(s); "
            f"{populated_brief_fields}/6 brief execution fields are populated."
        ),
        _refs(context, signal_ids=context["signals"].keys()),
    )


def _score_contradiction_risk(context: dict[str, Any]) -> dict[str, Any]:
    hits: list[str] = []
    for signal_id, signal in context["signals"].items():
        text = " ".join(
            [
                str(getattr(signal, "title", "") or ""),
                str(getattr(signal, "content", "") or ""),
                " ".join(str(tag) for tag in getattr(signal, "tags", [])),
            ]
        ).lower()
        if any(term in text for term in CONTRADICTION_TERMS):
            hits.append(signal_id)

    for idea in context["source_ideas"]:
        text = " ".join(
            [
                " ".join(str(tag) for tag in idea.get("rejection_tags", [])),
                str(idea.get("evidence_rationale", "") or ""),
            ]
        ).lower()
        if any(term in text for term in CONTRADICTION_TERMS):
            hits.append(str(idea["id"]))

    score = max(0, 100 - len(set(hits)) * 28)
    summary = "No explicit contradiction markers found." if not hits else f"Contradiction markers found in {len(set(hits))} record(s)."
    return _dimension("contradiction_risk", "Contradiction Risk", score, summary, _refs(context, signal_ids=hits))


def _score_traceability(context: dict[str, Any], design_brief: dict[str, Any]) -> dict[str, Any]:
    source_idea_ids = [idea["id"] for idea in context["source_ideas"]]
    signal_ids = set(context["signals"])
    insight_ids = set(context["insight_signal_ids"])
    linked_rows = [row for row in context["matrix"]["rows"] if row["supporting_source_idea_ids"]]
    brief_declared_sources = set(_string_list(design_brief.get("source_idea_ids"))) | {
        str(design_brief.get("lead_idea_id") or "")
    }
    resolvable_ratio = len(set(source_idea_ids) & brief_declared_sources) / max(len(brief_declared_sources - {""}), 1)
    score = min(
        100,
        round(resolvable_ratio * 35)
        + (25 if signal_ids else 0)
        + (20 if insight_ids else 0)
        + min(20, len(linked_rows) * 3),
    )
    return _dimension(
        "traceability",
        "Traceability",
        score,
        (
            f"{len(source_idea_ids)} source idea(s), {len(signal_ids)} signal(s), "
            f"{len(insight_ids)} insight(s), and {len(linked_rows)} matrix row(s) are linked."
        ),
        _refs(context, signal_ids=signal_ids, source_idea_ids=source_idea_ids),
    )


def _dimension(
    dimension_id: str,
    label: str,
    score: int | float,
    summary: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": dimension_id,
        "label": label,
        "score": int(round(max(0, min(100, score)))),
        "weight": DIMENSION_WEIGHTS[dimension_id],
        "summary": summary,
        "evidence_refs": sorted(set(evidence_refs)),
    }


def _overall_score(dimensions: list[dict[str, Any]]) -> int:
    return int(round(sum(item["score"] * item["weight"] for item in dimensions)))


def _band(score: int, blockers: list[str]) -> str:
    if blockers or score < 50:
        return "blocked"
    if score >= 85:
        return "ready"
    if score >= 70:
        return "monitor"
    return "needs_evidence"


def _confidence(score: int, blockers: list[str]) -> str:
    if blockers or score < 55:
        return "low"
    if score >= 80:
        return "high"
    return "medium"


def _recommendation(band: str) -> str:
    if band == "ready":
        return "Proceed to build execution with standard evidence monitoring."
    if band == "monitor":
        return "Proceed only with explicit monitoring and evidence follow-up owners."
    if band == "needs_evidence":
        return "Gather targeted evidence before build execution."
    return "Do not start build execution until blockers are resolved."


def _blockers(dimensions: list[dict[str, Any]]) -> list[str]:
    by_id = {item["id"]: item for item in dimensions}
    blockers: list[str] = []
    if by_id["evidence_volume"]["score"] < 40:
        blockers.append("Insufficient persisted evidence volume for build execution.")
    if by_id["traceability"]["score"] < 50:
        blockers.append("Brief cannot be traced to enough source ideas, insights, or signals.")
    if by_id["contradiction_risk"]["score"] < 50:
        blockers.append("Contradictory or invalidating evidence must be resolved.")
    return blockers


def _warnings(dimensions: list[dict[str, Any]]) -> list[str]:
    warning_map = {
        "source_diversity": "Evidence is concentrated in too few source adapters or source types.",
        "recency": "Evidence is stale or lacks reliable timestamps.",
        "role_balance": "Evidence does not cover enough buyer, workflow, risk, and validation roles.",
        "evidence_volume": "Evidence volume is below the preferred threshold.",
        "traceability": "Traceability is weaker than preferred for execution handoff.",
        "contradiction_risk": "Some records contain possible contradiction markers.",
    }
    return [warning_map[item["id"]] for item in dimensions if item["score"] < 75]


def _recommended_actions(dimensions: list[dict[str, Any]], blockers: list[str]) -> list[str]:
    actions: list[str] = []
    by_id = {item["id"]: item for item in dimensions}
    if by_id["evidence_volume"]["score"] < 75:
        actions.append("Add at least three credible signals tied to the lead and supporting source ideas.")
    if by_id["source_diversity"]["score"] < 75:
        actions.append("Add evidence from another independent adapter and source type.")
    if by_id["recency"]["score"] < 75:
        actions.append("Refresh the brief with signals published or fetched within the last 90 days.")
    if by_id["role_balance"]["score"] < 75:
        actions.append("Cover buyer, workflow, risk, and validation roles before execution.")
    if by_id["contradiction_risk"]["score"] < 90:
        actions.append("Resolve or explicitly waive contradictory evidence before launch planning.")
    if by_id["traceability"]["score"] < 75:
        actions.append("Link each major claim to source ideas, signals, and evidence matrix rows.")
    if not actions and not blockers:
        actions.append("Keep monitoring evidence freshness and contradiction markers during build execution.")
    return actions


def _evidence_refs(context: dict[str, Any]) -> dict[str, list[str]]:
    matrix_rows = context["matrix"]["rows"]
    return {
        "source_idea_ids": sorted({str(idea["id"]) for idea in context["source_ideas"]}),
        "signal_ids": sorted(context["signals"]),
        "insight_ids": sorted(context["insight_signal_ids"]),
        "evidence_matrix_rows": [row["claim_area"] for row in matrix_rows],
    }


def _refs(
    context: dict[str, Any],
    *,
    signal_ids: Any = (),
    source_idea_ids: Any = (),
) -> list[str]:
    refs = [f"signal:{signal_id}" for signal_id in signal_ids]
    refs.extend(f"source_idea:{idea_id}" for idea_id in source_idea_ids)
    return refs


def _role_counts(signals: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    for signal in signals:
        role = str(getattr(signal, "signal_role", "") or "").lower()
        if role:
            counts[role] += 1
        for tag in getattr(signal, "tags", []):
            normalized = str(tag).lower()
            if normalized:
                counts[normalized] += 1
        source_type = _source_type(signal)
        if source_type:
            counts[source_type] += 1
    return counts


def _source_type(signal: Any) -> str:
    value = getattr(signal, "source_type", "") or ""
    if hasattr(value, "value"):
        return str(value.value).lower()
    return str(value).lower()


def _parse_datetime(value: Any) -> datetime | None:
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


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [str(key) for key in value.keys()]
    return [str(item) for item in value if str(item).strip()]


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"
