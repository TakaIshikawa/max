"""Deterministic churn risk reports for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.churn_risk_report.v1"
KIND = "max.design_brief.churn_risk_report"

_VALIDATED_STATUSES = {"approved", "validated", "ready", "launched", "active"}
_WEAK_STATUSES = {"draft", "candidate", "proposed", "backlog", "new"}

_PRICING_FRICTION_TERMS = (
    "budget",
    "price",
    "pricing",
    "procurement",
    "cost",
    "willingness",
    "no budget",
    "expensive",
)
_SUPPORT_BURDEN_TERMS = (
    "support",
    "ticket",
    "manual",
    "onboarding",
    "training",
    "migration",
    "integration",
    "dependency",
    "security",
    "compliance",
    "handoff",
    "incident",
)
_RETENTION_VALUE_TERMS = (
    "save",
    "reduce",
    "recurring",
    "automation",
    "habit",
    "daily",
    "weekly",
    "retention",
    "adoption",
)


def build_design_brief_churn_risk_report(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a churn risk report from a persisted design brief and linked lineage."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    evidence_refs = _evidence_references(store, source_ideas)
    evaluations = _evaluation_records(store, source_ideas)
    context = _context(design_brief, source_ideas, evidence_refs, evaluations)
    dimensions = [
        _evidence_strength_dimension(context),
        _validation_status_dimension(design_brief, context),
        _support_burden_dimension(context),
        _pricing_friction_dimension(context),
        _retention_value_dimension(context),
    ]
    score = _risk_score(dimensions)
    tier = _risk_tier(score)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
            "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer")),
            "specific_user": _first_text(
                design_brief.get("specific_user"),
                _field_values(source_ideas, "specific_user"),
            ),
            "workflow_context": _first_text(
                design_brief.get("workflow_context"),
                _field_values(source_ideas, "workflow_context"),
            ),
        },
        "summary": {
            "score": score,
            "tier": tier,
            "evidence_reference_count": len(evidence_refs),
            "validation_status": _validation_status(design_brief),
            "support_burden": _burden_band(
                next(item["points"] for item in dimensions if item["id"] == "support_burden")
            ),
            "pricing_friction": _friction_band(
                next(item["points"] for item in dimensions if item["id"] == "pricing_friction")
            ),
        },
        "score": score,
        "tier": tier,
        "risk_drivers": _risk_drivers(dimensions, context),
        "retention_levers": _retention_levers(design_brief, context, tier),
        "warning_indicators": _warning_indicators(design_brief, context, tier),
        "follow_up_experiments": _follow_up_experiments(design_brief, context, dimensions),
        "dimension_scores": dimensions,
        "evidence_references": evidence_refs,
        "source_ideas": source_ideas,
    }


def render_design_brief_churn_risk_report(
    report: dict[str, Any],
    fmt: str = "json",
) -> str:
    """Render a churn risk report as deterministic JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported churn risk report format: {fmt}")

    brief = report["design_brief"]
    lines = [
        f"# Churn Risk Report: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        f"Design brief: `{brief['id']}`",
        f"Score: {report['score']}/100",
        f"Tier: `{report['tier']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        "",
        "## Risk Drivers",
        "",
    ]
    for driver in report["risk_drivers"]:
        lines.extend(
            [
                f"- **{driver['label']}** ({driver['severity']}): {driver['summary']}",
                f"  Evidence: {_inline_ids(driver['evidence_refs'])}",
            ]
        )

    lines.extend(["", "## Retention Levers", ""])
    for lever in report["retention_levers"]:
        lines.append(f"- **{lever['lever']}**: {lever['action']} ({lever['owner']})")

    lines.extend(["", "## Warning Indicators", ""])
    for indicator in report["warning_indicators"]:
        lines.append(
            f"- **{indicator['indicator']}**: {indicator['threshold']} -> {indicator['response']}"
        )

    lines.extend(["", "## Follow-Up Experiments", ""])
    for experiment in report["follow_up_experiments"]:
        lines.extend(
            [
                f"### {experiment['id']}: {experiment['name']}",
                "",
                f"- Hypothesis: {experiment['hypothesis']}",
                f"- Method: {experiment['method']}",
                f"- Success signal: {experiment['success_signal']}",
                f"- Kill signal: {experiment['kill_signal']}",
                "",
            ]
        )

    lines.extend(["## Dimension Scores", ""])
    for dimension in report["dimension_scores"]:
        lines.append(
            f"- **{dimension['label']}**: {dimension['points']} point(s) - {dimension['summary']}"
        )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for ref in report["evidence_references"]:
            lines.append(f"- `{ref['id']}` ({ref['type']}): {ref['description']}")
    else:
        lines.append("- No stored evidence references are linked to the brief lineage.")

    return "\n".join(lines).rstrip() + "\n"


def churn_risk_report_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-churn-risk-report.{extension}"


def _context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_refs: list[dict[str, str]],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    text_values: list[str] = []
    for field in (
        "title",
        "domain",
        "theme",
        "buyer",
        "specific_user",
        "workflow_context",
        "why_this_now",
        "merged_product_concept",
        "synthesis_rationale",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
        "risks",
    ):
        text_values.extend(_string_list(design_brief.get(field)))
    for idea in source_ideas:
        for field in (
            "problem",
            "solution",
            "value_proposition",
            "specific_user",
            "buyer",
            "workflow_context",
            "current_workaround",
            "why_now",
            "validation_plan",
            "first_10_customers",
            "domain_risks",
            "tech_approach",
            "evidence_rationale",
        ):
            text_values.extend(_string_list(idea.get(field)))
    for ref in evidence_refs:
        text_values.extend(_string_list(ref.get("description")))
        text_values.extend(_string_list(ref.get("tags")))
    for evaluation in evaluations:
        text_values.extend(_string_list(evaluation.get("strengths")))
        text_values.extend(_string_list(evaluation.get("weaknesses")))
        text_values.extend(_string_list(evaluation.get("recommendation")))

    lowered = " ".join(text_values).lower()
    return {
        "text": lowered,
        "source_ideas": source_ideas,
        "evidence_refs": evidence_refs,
        "evaluations": evaluations,
        "explicit_risks": _string_list(design_brief.get("risks"))
        + _field_values(source_ideas, "domain_risks"),
        "scope_items": _string_list(design_brief.get("mvp_scope")),
        "milestones": _string_list(design_brief.get("first_milestones")),
    }


def _evidence_strength_dimension(context: dict[str, Any]) -> dict[str, Any]:
    ref_count = len(context["evidence_refs"])
    source_count = len([idea for idea in context["source_ideas"] if not idea.get("missing")])
    evaluations = len(context["evaluations"])
    if ref_count >= 4 and (source_count >= 2 or evaluations):
        points = -12
        band = "strong"
    elif ref_count >= 2 or evaluations:
        points = 4
        band = "moderate"
    elif ref_count == 1 or source_count:
        points = 12
        band = "thin"
    else:
        points = 22
        band = "missing"
    return {
        "id": "evidence_strength",
        "label": "Evidence Strength",
        "points": points,
        "band": band,
        "summary": f"{ref_count} evidence reference(s), {source_count} source idea(s), and {evaluations} evaluation(s).",
        "evidence_refs": [ref["id"] for ref in context["evidence_refs"][:4]],
    }


def _validation_status_dimension(
    design_brief: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    status = _validation_status(design_brief)
    has_plan = _has_value(design_brief.get("validation_plan")) or any(
        _has_value(idea.get("validation_plan")) for idea in context["source_ideas"]
    )
    if status in _VALIDATED_STATUSES and has_plan:
        points = -10
    elif has_plan:
        points = 4
    elif status in _WEAK_STATUSES:
        points = 18
    else:
        points = 14
    return {
        "id": "validation_status",
        "label": "Validation Status",
        "points": points,
        "band": "validated" if points < 0 else "planned" if has_plan else "missing",
        "summary": f"Status is {status or 'unknown'}; validation plan {'exists' if has_plan else 'is missing'}.",
        "evidence_refs": ["design_brief.validation_plan"] if _has_value(design_brief.get("validation_plan")) else [],
    }


def _support_burden_dimension(context: dict[str, Any]) -> dict[str, Any]:
    text = context["text"]
    matched = _matched_terms(text, _SUPPORT_BURDEN_TERMS)
    risk_count = len(context["explicit_risks"])
    scope_count = len(context["scope_items"])
    points = min(24, len(matched) * 3 + risk_count * 4 + max(0, scope_count - 2) * 2)
    return {
        "id": "support_burden",
        "label": "Support Burden",
        "points": points,
        "band": _burden_band(points),
        "summary": f"{risk_count} explicit support/risk item(s), {scope_count} scope item(s), matched terms: {_inline_terms(matched)}.",
        "evidence_refs": ["design_brief.risks"] if risk_count else [],
    }


def _pricing_friction_dimension(context: dict[str, Any]) -> dict[str, Any]:
    text = context["text"]
    matched = _matched_terms(text, _PRICING_FRICTION_TERMS)
    points = min(22, len(matched) * 4)
    if "no budget" in text:
        points = min(22, points + 6)
    return {
        "id": "pricing_friction",
        "label": "Pricing Friction",
        "points": points,
        "band": _friction_band(points),
        "summary": f"Matched pricing or ROI friction terms: {_inline_terms(matched)}.",
        "evidence_refs": [ref["id"] for ref in context["evidence_refs"] if ref.get("type") in {"signal", "source_idea_rationale"}][:4],
    }


def _retention_value_dimension(context: dict[str, Any]) -> dict[str, Any]:
    text = context["text"]
    matched = _matched_terms(text, _RETENTION_VALUE_TERMS)
    points = -min(16, len(matched) * 3)
    if not matched:
        points = 8
    return {
        "id": "retention_value",
        "label": "Retention Value",
        "points": points,
        "band": "clear" if points < 0 else "unclear",
        "summary": f"Matched retention value terms: {_inline_terms(matched)}.",
        "evidence_refs": [],
    }


def _risk_score(dimensions: list[dict[str, Any]]) -> int:
    return max(0, min(100, 38 + sum(int(item["points"]) for item in dimensions)))


def _risk_tier(score: int) -> str:
    if score >= 65:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _risk_drivers(
    dimensions: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    drivers: list[dict[str, Any]] = []
    for dimension in dimensions:
        if dimension["points"] <= 3:
            continue
        severity = "high" if dimension["points"] >= 16 else "medium"
        drivers.append(
            {
                "id": dimension["id"],
                "label": dimension["label"],
                "severity": severity,
                "summary": dimension["summary"],
                "evidence_refs": dimension["evidence_refs"],
            }
        )
    if not drivers:
        drivers.append(
            {
                "id": "no_major_driver",
                "label": "No Major Churn Driver",
                "severity": "low",
                "summary": "Persisted inputs show enough validation, evidence, and retention value to keep churn risk controlled.",
                "evidence_refs": [ref["id"] for ref in context["evidence_refs"][:4]],
            }
        )
    return drivers


def _retention_levers(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    tier: str,
) -> list[dict[str, str]]:
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(context["source_ideas"], "workflow_context"),
        default="the target workflow",
    )
    buyer = _first_text(
        design_brief.get("buyer"),
        _field_values(context["source_ideas"], "buyer"),
        default="the accountable buyer",
    )
    user = _first_text(
        design_brief.get("specific_user"),
        _field_values(context["source_ideas"], "specific_user"),
        default="the primary user",
    )
    levers = [
        {
            "id": "RL1",
            "lever": "Activation milestone",
            "action": f"Make the first successful {workflow} outcome visible within the pilot.",
            "owner": "product",
        },
        {
            "id": "RL2",
            "lever": "Buyer value proof",
            "action": f"Send {buyer} a before/after value summary tied to the user's current workaround.",
            "owner": "go-to-market",
        },
        {
            "id": "RL3",
            "lever": "Support deflection",
            "action": f"Prepare onboarding and troubleshooting paths for {user} before expansion.",
            "owner": "support",
        },
    ]
    if tier == "high":
        levers.insert(
            0,
            {
                "id": "RL0",
                "lever": "Retention gate",
                "action": "Do not expand implementation until activation, support, and willingness-to-pay thresholds are observed.",
                "owner": "product",
            },
        )
    return levers


def _warning_indicators(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    tier: str,
) -> list[dict[str, str]]:
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(context["source_ideas"], "workflow_context"),
        default="target workflow",
    )
    indicators = [
        {
            "id": "WI1",
            "indicator": "Activation miss",
            "threshold": f"Fewer than 60% of pilot users complete the first {workflow} outcome.",
            "response": "Interview non-activated users and remove the top setup blocker.",
        },
        {
            "id": "WI2",
            "indicator": "Support load",
            "threshold": "More than two avoidable support touches per active account in the first month.",
            "response": "Add onboarding checks, defaults, or in-product recovery paths.",
        },
        {
            "id": "WI3",
            "indicator": "Pricing resistance",
            "threshold": "Buyer delays renewal or pilot conversion over budget, procurement, or ROI proof.",
            "response": "Narrow packaging and quantify the value metric before expansion.",
        },
    ]
    if tier != "low":
        indicators.append(
            {
                "id": "WI4",
                "indicator": "Validation drift",
                "threshold": "Discovery calls produce objections not covered by the current validation plan.",
                "response": "Update the risk register and run a targeted follow-up experiment.",
            }
        )
    return indicators


def _follow_up_experiments(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    dimensions: list[dict[str, Any]],
) -> list[dict[str, str]]:
    weak_dimensions = {item["id"] for item in dimensions if item["points"] >= 12}
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(context["source_ideas"], "workflow_context"),
        default="the target workflow",
    )
    experiments = [
        {
            "id": "EXP1",
            "name": "Activation Cohort Test",
            "hypothesis": f"Target users will complete a meaningful {workflow} outcome without heavy support.",
            "method": "Run a five-account pilot and track first-value completion, time-to-value, and support touches.",
            "success_signal": "At least 4 of 5 accounts reach first value with no more than one avoidable support touch.",
            "kill_signal": "Most accounts fail activation or need repeated manual intervention.",
        },
        {
            "id": "EXP2",
            "name": "Renewal Objection Interview",
            "hypothesis": "The buyer can name a renewal reason and budget owner after seeing the value metric.",
            "method": "Show a one-page value summary to three buyers and ask for renewal, expansion, and procurement objections.",
            "success_signal": "Two buyers identify a budget path and value metric they would review at renewal.",
            "kill_signal": "Buyers cannot connect the product outcome to renewal or budget ownership.",
        },
    ]
    if "evidence_strength" in weak_dimensions or "validation_status" in weak_dimensions:
        experiments.insert(
            0,
            {
                "id": "EXP0",
                "name": "Evidence Threshold Sprint",
                "hypothesis": "The churn score will fall once primary validation and independent evidence are attached.",
                "method": "Collect three independent evidence references and one explicit pass/fail validation result.",
                "success_signal": "Evidence references cover problem, buyer, workflow, and willingness-to-pay claims.",
                "kill_signal": "Evidence contradicts the problem urgency or buyer value claim.",
            },
        )
    return experiments


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = list(design_brief.get("sources", []))
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(design_brief.get("source_idea_ids", []), start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

    for source in sources:
        idea_id = str(source["idea_id"])
        if idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append(
                {
                    "id": idea_id,
                    "role": source.get("role", "source"),
                    "rank": source.get("rank", 0),
                    "missing": True,
                }
            )
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _evidence_references(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    signal_ids: set[str] = set()
    insight_ids: set[str] = set()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        signal_ids.update(_string_list(idea.get("evidence_signals")))
        insight_ids.update(_string_list(idea.get("inspiring_insights")))
        if _has_value(idea.get("evidence_rationale")):
            signal_ids.add(f"{idea['id']}.evidence_rationale")

    references: list[dict[str, str]] = []
    for insight_id in sorted(insight_ids):
        insight = store.get_insight(insight_id)
        if insight:
            signal_ids.update(_string_list(getattr(insight, "evidence", [])))
            references.append(
                {
                    "id": insight_id,
                    "type": "insight",
                    "description": str(getattr(insight, "summary", "") or getattr(insight, "title", "")),
                    "tags": ", ".join(_string_list(getattr(insight, "domains", []))),
                }
            )

    for signal_id in sorted(signal_ids):
        if signal_id.endswith(".evidence_rationale"):
            references.append(
                {
                    "id": signal_id,
                    "type": "source_idea_rationale",
                    "description": "Source idea includes explicit evidence rationale.",
                    "tags": "",
                }
            )
            continue
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        references.append(
            {
                "id": signal.id,
                "type": "signal",
                "description": str(signal.title or signal.content or ""),
                "tags": ", ".join(_string_list(getattr(signal, "tags", []))),
            }
        )
    return _dedupe_references(references)


def _evaluation_records(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        evaluation = store.get_evaluation(str(idea["id"]))
        if not evaluation:
            continue
        records.append(evaluation.model_dump(mode="json"))
    return records


def _validation_status(design_brief: dict[str, Any]) -> str:
    return str(design_brief.get("design_status") or "").strip().lower()


def _burden_band(points: int) -> str:
    if points >= 16:
        return "high"
    if points >= 7:
        return "medium"
    return "low"


def _friction_band(points: int) -> str:
    if points >= 14:
        return "high"
    if points >= 6:
        return "medium"
    return "low"


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        for item in _string_list(value):
            if item:
                return item
    return default


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _inline_terms(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _dedupe_references(references: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in references:
        item_id = item["id"]
        if item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return sorted(deduped, key=lambda item: (item["type"], item["id"]))


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "design-brief"
