"""Investment case export for stakeholder funding decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
KIND = "investment-case"


def build_investment_case(
    unit: dict[str, Any],
    evaluation: dict[str, Any],
    market_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a decision-ready investment case from a scored buildable unit."""
    market = market_data if isinstance(market_data, dict) else {}
    signals = _signals(unit, market)
    dimensions = _dimensions(evaluation)
    score = _score(evaluation)
    recommendation = _recommendation(score, evaluation, dimensions)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "investment_case",
            "idea_id": _text(_value(unit, "id"), _value(unit, "idea_id")),
        },
        "executive_summary": _executive_summary(unit, score, recommendation),
        "problem_validation": _problem_validation(unit, signals),
        "proposed_solution": _proposed_solution(unit),
        "market_opportunity": _market_opportunity(market, signals),
        "competitive_landscape": _competitive_landscape(unit, market, signals),
        "resource_requirements": _resource_requirements(unit, market),
        "risk_factors": _risk_factors(dimensions, evaluation),
        "expected_outcomes": _expected_outcomes(unit, evaluation, market),
        "recommendation": recommendation,
        "evidence_chain": _evidence_chain(signals),
    }


def render_investment_case_markdown(case: dict[str, Any]) -> str:
    """Render an investment case as Markdown."""
    lines = [
        f"# Investment Case: {_md(case.get('source', {}).get('idea_id') or 'Untitled')}",
        "",
        f"Schema: `{case['schema_version']}`",
        f"Generated: {case['generated_at']}",
        "",
        "## Executive Summary",
        "",
        str(case.get("executive_summary", "")),
        "",
        "## Problem Validation",
        "",
    ]
    validation = case.get("problem_validation", {})
    lines.extend(
        [
            f"- Problem: {_md(validation.get('problem'))}",
            f"- Source count: {validation.get('source_count', 0)}",
            f"- Evidence strength: {validation.get('evidence_strength', 'low')}",
        ]
    )
    for item in validation.get("evidence", []):
        lines.append(f"- Evidence: {_md(item)}")

    solution = case.get("proposed_solution", {})
    market = case.get("market_opportunity", {})
    landscape = case.get("competitive_landscape", {})
    resources = case.get("resource_requirements", {})
    recommendation = case.get("recommendation", {})
    lines.extend(
        [
            "",
            "## Proposed Solution",
            "",
            f"- Approach: {_md(solution.get('solution_approach'))}",
            f"- Tech stack: {_md(', '.join(solution.get('tech_stack', [])) or 'Not specified')}",
            "",
            "## Market Opportunity",
            "",
            f"- Size estimate: {_md(market.get('size_estimate'))}",
            f"- Growth indicators: {_md(', '.join(market.get('growth_indicators', [])) or 'None identified')}",
            f"- Confidence: {_md(market.get('confidence'))}",
            "",
            "## Competitive Landscape",
            "",
            f"- Alternatives: {_md(', '.join(landscape.get('alternatives', [])) or 'None identified')}",
            f"- Positioning: {_md(landscape.get('positioning'))}",
            "",
            "## Resource Requirements",
            "",
            f"- Team size: {resources.get('team_size', 0)}",
            f"- Estimated timeline: {_md(resources.get('estimated_timeline'))}",
            f"- Tech stack: {_md(', '.join(resources.get('tech_stack', [])) or 'Not specified')}",
            "",
            "## Risk Factors",
            "",
        ]
    )
    for risk in case.get("risk_factors", []):
        lines.append(
            f"- **{_md(risk['risk'])}** ({risk['severity']}): {_md(risk['mitigation'])}"
        )
    if not case.get("risk_factors"):
        lines.append("- No material risk factors identified.")

    lines.extend(["", "## Expected Outcomes", ""])
    for outcome in case.get("expected_outcomes", []):
        lines.append(f"- {_md(outcome.get('kpi'))}: {_md(outcome.get('target'))}")

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- Decision: **{_md(recommendation.get('decision'))}**",
            f"- Score: {recommendation.get('score', 0.0):.1f}",
            f"- Justification: {_md(recommendation.get('justification'))}",
            "",
            "## Evidence Chain",
            "",
        ]
    )
    for evidence in case.get("evidence_chain", []):
        url = evidence.get("url") or "no-url"
        lines.append(f"- {_md(evidence.get('title'))} ({_md(evidence.get('source'))}) - {url}")
    if not case.get("evidence_chain"):
        lines.append("- No source signals available.")
    return "\n".join(lines).rstrip() + "\n"


def render_investment_case_json(case: dict[str, Any]) -> str:
    """Render an investment case as stable formatted JSON."""
    return json.dumps(case, indent=2, sort_keys=True, default=str)


def _executive_summary(unit: dict[str, Any], score: float, recommendation: dict[str, Any]) -> str:
    title = _text(_value(unit, "title"), _value(unit, "name"), "Untitled idea")
    problem = _text(_value(unit, "problem"), _nested(unit, "problem", "statement"), "a validated customer problem")
    solution = _text(
        _value(unit, "solution_approach"),
        _nested(unit, "solution", "approach"),
        _value(unit, "solution"),
        "the proposed solution",
    )
    return (
        f"{title} addresses {problem} with {solution}. "
        f"The evaluated score is {score:.1f}/100, supporting a {recommendation['decision']} recommendation. "
        f"{recommendation['justification']}"
    )


def _problem_validation(unit: dict[str, Any], signals: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = [
        _text(signal.get("summary"), signal.get("content"), signal.get("title"))
        for signal in signals[:5]
    ]
    source_count = len({str(signal.get("source") or signal.get("source_type") or signal.get("url") or i) for i, signal in enumerate(signals)})
    return {
        "problem": _text(_value(unit, "problem"), _nested(unit, "problem", "statement"), "Not specified"),
        "source_count": source_count,
        "signal_count": len(signals),
        "evidence_strength": "high" if source_count >= 4 else "medium" if source_count >= 2 else "low",
        "evidence": [item for item in evidence if item],
    }


def _proposed_solution(unit: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_approach": _text(
            _value(unit, "solution_approach"),
            _nested(unit, "solution", "approach"),
            _value(unit, "solution"),
            "Not specified",
        ),
        "tech_stack": _tech_stack(unit),
    }


def _market_opportunity(market: dict[str, Any], signals: list[dict[str, Any]]) -> dict[str, Any]:
    growth = _list(market.get("growth_indicators"))
    if not growth:
        growth = _growth_indicators(signals)
    return {
        "size_estimate": _text(
            market.get("size_estimate"),
            market.get("market_size"),
            market.get("tam"),
            "Unknown; market sizing data not provided",
        ),
        "growth_indicators": growth,
        "confidence": _text(market.get("confidence"), "low" if not market else "medium"),
        "notes": _text(market.get("notes"), market.get("methodology"), ""),
    }


def _competitive_landscape(
    unit: dict[str, Any],
    market: dict[str, Any],
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    alternatives = _list(market.get("alternatives")) or _list(market.get("competitors"))
    if not alternatives:
        alternatives = _alternatives_from_signals(signals)
    return {
        "alternatives": alternatives,
        "positioning": _text(
            market.get("positioning"),
            _value(unit, "differentiation"),
            "Position against current manual workflows and incumbent alternatives.",
        ),
    }


def _resource_requirements(unit: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(unit)
    tech_stack = _tech_stack(unit)
    timeline = _text(
        market.get("estimated_timeline"),
        metadata.get("estimated_timeline"),
        metadata.get("timeline"),
        _value(unit, "estimated_timeline"),
        "8-12 weeks",
    )
    return {
        "team_size": _int(
            market.get("team_size"),
            metadata.get("team_size"),
            max(3, min(6, len(tech_stack) + 2)),
        ),
        "roles": _list(market.get("roles")) or _list(metadata.get("roles")) or ["Product lead", "Engineering lead", "Designer"],
        "tech_stack": tech_stack,
        "estimated_timeline": timeline,
    }


def _risk_factors(dimensions: dict[str, float], evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = _list(evaluation.get("risks") or evaluation.get("risk_factors"))
    risks: list[dict[str, Any]] = []
    for item in explicit[:3]:
        risks.append({"risk": item, "severity": "medium", "mitigation": "Assign an owner and validate before funding release."})

    weak_dimensions = sorted(dimensions.items(), key=lambda item: item[1])
    for dimension, score in weak_dimensions:
        if len(risks) >= 3:
            break
        if score >= 65:
            continue
        risks.append(
            {
                "risk": _label(dimension),
                "severity": "high" if score < 45 else "medium",
                "score": round(score, 1),
                "mitigation": _mitigation(dimension),
            }
        )

    if not risks:
        risks.append(
            {
                "risk": "Execution uncertainty",
                "severity": "low",
                "mitigation": "Confirm scope, ownership, and validation milestones during kickoff.",
            }
        )
    return risks[:3]


def _expected_outcomes(
    unit: dict[str, Any],
    evaluation: dict[str, Any],
    market: dict[str, Any],
) -> list[dict[str, str]]:
    explicit = _list(_value(unit, "expected_outcomes")) or _list(market.get("expected_outcomes"))
    if explicit:
        return [{"kpi": item, "target": "Measured during pilot"} for item in explicit[:5]]
    score = _score(evaluation)
    return [
        {"kpi": "Validated demand", "target": "At least 5 qualified stakeholder or customer confirmations"},
        {"kpi": "Pilot adoption", "target": "3 active pilot teams within 60 days"},
        {"kpi": "Funding confidence", "target": f"Maintain evaluation score at or above {max(60.0, score):.1f}"},
    ]


def _recommendation(
    score: float,
    evaluation: dict[str, Any],
    dimensions: dict[str, float],
) -> dict[str, Any]:
    requested = _text(evaluation.get("recommendation")).lower()
    weak_count = sum(1 for value in dimensions.values() if value < 50)
    if requested in {"no", "reject", "rejected"} or score < 50:
        decision = "no-go"
        justification = "Evaluation score is below the funding threshold or the source recommendation is negative."
    elif requested in {"yes", "go", "approved"} or (score >= 75 and weak_count == 0):
        decision = "go"
        justification = "Evaluation score and supporting dimensions clear the funding threshold."
    else:
        decision = "conditional"
        justification = "Proceed only after the lowest-scoring assumptions are validated."
    return {
        "decision": decision,
        "score": round(score, 1),
        "justification": justification,
        "weak_dimension_count": weak_count,
    }


def _evidence_chain(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chain = []
    for index, signal in enumerate(signals, start=1):
        chain.append(
            {
                "id": _text(signal.get("id"), f"signal-{index}"),
                "title": _text(signal.get("title"), signal.get("summary"), "Untitled signal"),
                "source": _text(signal.get("source"), signal.get("source_type"), "unknown"),
                "url": _text(signal.get("url"), signal.get("link"), ""),
            }
        )
    return chain


def _signals(unit: dict[str, Any], market: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _value(unit, "signals")
    if raw is None:
        raw = _value(unit, "source_signals")
    signals = [item for item in _dict_list(raw) if item]
    signals.extend(item for item in _dict_list(market.get("signals")) if item)
    return signals


def _dimensions(evaluation: dict[str, Any]) -> dict[str, float]:
    raw = evaluation.get("dimensions") or evaluation.get("dimension_scores") or {}
    if not isinstance(raw, dict):
        return {}
    dimensions: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            value = value.get("score") or value.get("value")
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        dimensions[str(key)] = number * 10 if number <= 10 else number
    return dimensions


def _score(evaluation: dict[str, Any]) -> float:
    for key in ("overall_score", "score", "readiness_score"):
        try:
            return max(0.0, min(100.0, float(evaluation.get(key))))
        except (TypeError, ValueError):
            continue
    return 0.0


def _tech_stack(unit: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("tech_stack", "technology_stack", "suggested_stack", "dependencies"):
        values.extend(_list(_value(unit, key)))
    solution = _value(unit, "solution")
    if isinstance(solution, dict):
        values.extend(_list(solution.get("tech_stack")))
        values.extend(_list(solution.get("suggested_stack")))
    return sorted(dict.fromkeys(values))


def _growth_indicators(signals: list[dict[str, Any]]) -> list[str]:
    terms = ("growth", "adoption", "demand", "market", "revenue", "expansion")
    found: list[str] = []
    for signal in signals:
        text = _signal_text(signal)
        for term in terms:
            if term in text and term not in found:
                found.append(term)
    return found[:5]


def _alternatives_from_signals(signals: list[dict[str, Any]]) -> list[str]:
    alternatives: list[str] = []
    for signal in signals:
        alternatives.extend(_list(signal.get("alternatives")))
        alternatives.extend(_list(signal.get("competitors")))
    return sorted(dict.fromkeys(alternatives))[:5]


def _metadata(unit: dict[str, Any]) -> dict[str, Any]:
    metadata = _value(unit, "metadata")
    return metadata if isinstance(metadata, dict) else {}


def _nested(obj: dict[str, Any], key: str, nested_key: str) -> Any:
    value = _value(obj, key)
    return value.get(nested_key) if isinstance(value, dict) else None


def _value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    if isinstance(value, dict):
        if "name" in value:
            return _list(value["name"])
        values: list[str] = []
        for item in value.values():
            values.extend(_list(item))
        return values
    if isinstance(value, list | tuple | set):
        values: list[str] = []
        for item in value:
            values.extend(_list(item))
        return values
    return [str(value).strip()] if str(value).strip() else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int(*values: Any) -> int:
    for value in values:
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            continue
    return 0


def _signal_text(signal: dict[str, Any]) -> str:
    return " ".join(
        str(signal.get(key, "")).lower()
        for key in ("title", "summary", "content", "description")
    )


def _label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _mitigation(dimension: str) -> str:
    lowered = dimension.lower()
    if "market" in lowered or "demand" in lowered:
        return "Run focused customer discovery and quantify demand before full funding."
    if "technical" in lowered or "effort" in lowered or "complexity" in lowered:
        return "Run a technical spike and reduce scope to the smallest fundable pilot."
    if "risk" in lowered or "dependency" in lowered:
        return "Identify alternatives, owners, and exit criteria before kickoff."
    return "Add validation evidence and an accountable owner before scaling investment."


def _text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _md(value: Any) -> str:
    return str(value or "Not specified").replace("|", "\\|").replace("\n", " ")
