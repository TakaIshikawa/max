"""Deterministic GTM channel plans for persisted design briefs."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from max.store.db import Store

KIND = "max.design_brief.gtm_channel_plan"
SCHEMA_VERSION = "max.design_brief.gtm_channel_plan.v1"

_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("buyer", "Buyer is needed to shape sales-assisted and enablement motions."),
    ("specific_user", "Specific user is needed to target acquisition and community channels."),
    ("workflow_context", "Workflow context is needed to make channel messaging concrete."),
    ("validation_plan", "Validation plan is needed to define channel exit criteria."),
    ("risks", "Risks are needed to set launch guardrails."),
    ("source_idea_ids", "Source ideas are needed for traceable channel evidence."),
)


def build_design_brief_gtm_channel_plan(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a deterministic go-to-market channel plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    evidence_refs = _evidence_references(store, source_ideas)
    market_signals = _market_signal_counts(evidence_refs)
    missing_inputs = _missing_inputs(design_brief, source_ideas)
    brief_context = _brief_context(design_brief, source_ideas)
    recommendations = _ranked_recommendations(
        brief_context,
        market_signals=market_signals,
        evidence_refs=evidence_refs,
        source_ideas=source_ideas,
    )
    sequencing = _sequencing(recommendations, design_brief)
    risks = _risk_plan(design_brief, recommendations)

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
            "buyer": brief_context["buyer"],
            "specific_user": brief_context["target_user"],
            "workflow_context": brief_context["workflow"],
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": _source_idea_ids(design_brief, source_ideas),
        },
        "summary": {
            "primary_audience": brief_context["target_user"],
            "buyer": brief_context["buyer"],
            "workflow_context": brief_context["workflow"],
            "positioning": brief_context["positioning"],
            "recommended_channel_count": len(recommendations),
            "primary_channel": recommendations[0]["channel"],
            "confidence": _overall_confidence(recommendations, missing_inputs),
        },
        "channels": _channel_groups(recommendations, brief_context, evidence_refs),
        "channel_recommendations": recommendations,
        "sequencing": sequencing,
        "launch_sequence": sequencing,
        "measurement_plan": _measurement_plan(brief_context, recommendations),
        "risks": risks,
        "missing_inputs": missing_inputs,
        "market_signals": market_signals,
        "evidence_refs": evidence_refs,
        "source_ideas": source_ideas,
    }


def render_design_brief_gtm_channel_plan(report: dict[str, Any], fmt: str = "json") -> str:
    """Render the GTM channel plan as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported GTM channel plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# GTM Channel Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Primary channel: {summary['primary_channel']}",
        f"Confidence: {summary['confidence']}",
        "",
        "## Channel Recommendations",
        "",
    ]
    for recommendation in report["channel_recommendations"]:
        lines.extend(
            [
                f"### {recommendation['priority']}. {recommendation['channel']}",
                "",
                f"- **Type**: {recommendation['type']}",
                f"- **Audience**: {recommendation['audience']}",
                f"- **Owner**: {recommendation['owner']}",
                f"- **Confidence**: {recommendation['confidence']}",
                f"- **Rationale**: {recommendation['rationale']}",
                f"- **CTA**: {recommendation['call_to_action']}",
                f"- **Evidence refs**: {_inline_ids(recommendation['evidence_refs'])}",
                f"- **Success metric**: {recommendation['success_metric']['metric']} - {recommendation['success_metric']['target']}",
                "",
            ]
        )
        for tactic in recommendation["tactics"]:
            lines.append(f"- Tactic: {tactic['name']} - {tactic['description']} ({tactic['owner']})")
        lines.append("")

    lines.extend(["## Sequencing Guidance", ""])
    for phase in report["sequencing"]:
        lines.extend(
            [
                f"### {phase['phase'].title()}",
                "",
                f"- Goal: {phase['goal']}",
                f"- Channels: {', '.join(phase['channels'])}",
                f"- Exit criteria: {phase['exit_criteria']}",
                "",
            ]
        )

    lines.extend(["## Measurement Plan", ""])
    for metric in report["measurement_plan"]:
        lines.append(f"- **{metric['metric']}**: {metric['definition']} Target: {metric['target']}.")

    lines.extend(["", "## Risks", ""])
    lines.extend(f"- **{risk['risk']}**: {risk['mitigation']}" for risk in report["risks"] or [])
    if not report["risks"]:
        lines.append("- None")

    lines.extend(["", "## Missing Inputs", ""])
    if report["missing_inputs"]:
        lines.extend(f"- **{item['field']}**: {item['reason']}" for item in report["missing_inputs"])
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def gtm_channel_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a GTM channel plan export."""
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    return f"{brief_id}-gtm-channel-plan.{extension}"


def _ranked_recommendations(
    context: dict[str, str],
    *,
    market_signals: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    evidence_ids = [reference["id"] for reference in evidence_refs]
    domain = context["domain"].lower()
    readiness = float(context["readiness_score"] or 0.0)
    channel_specs = [
        _channel_spec(
            "GTM1",
            "design partner outreach",
            "acquisition",
            "direct validation",
            context["target_user"],
            "product marketing",
            40 + _readiness_points(readiness) + _signal_points(market_signals, ("survey", "forum")),
            f"Direct outreach is the fastest way to confirm {context['workflow']} urgency with named users.",
            "Schedule a 30-minute workflow review.",
            "qualified_conversation_rate",
            "25%+ positive replies from qualified accounts",
            ["specific_user", "workflow_context", "validation_plan"],
            evidence_ids,
            source_idea_ids,
            [
                {
                    "name": "warm account list",
                    "description": f"Identify existing relationships with {context['target_user']} ownership.",
                    "owner": "product marketing",
                },
                {
                    "name": "problem-led email",
                    "description": f"Lead with the {context['workflow']} pain and request validation.",
                    "owner": "founder or product lead",
                },
            ],
        ),
        _channel_spec(
            "GTM2",
            "buyer enablement content",
            "sales-assisted",
            "education",
            context["buyer"],
            "go-to-market lead",
            32 + _readiness_points(readiness) + _signal_points(market_signals, ("funding", "survey")),
            f"{context['buyer']} needs a concise business case before sponsoring rollout.",
            "Review the pilot business case.",
            "buyer_review_rate",
            "10+ buyer reviews before broad launch",
            ["buyer", "merged_product_concept", "readiness_score"],
            evidence_ids,
            source_idea_ids,
            [
                {
                    "name": "one-page business case",
                    "description": "Translate the design brief into pain, outcome, proof, and next step.",
                    "owner": "go-to-market lead",
                }
            ],
        ),
        _channel_spec(
            "GTM3",
            "community proof loop",
            "community",
            "credible demand capture",
            context["target_user"],
            "developer relations" if "developer" in domain else "community lead",
            28 + _signal_points(market_signals, ("forum", "social")),
            "Community posts can test wording and collect proof points without paid spend.",
            "Join the pilot waitlist.",
            "waitlist_quality_rate",
            "50%+ of signups match the target workflow",
            ["specific_user", "workflow_context", "why_this_now"],
            evidence_ids,
            source_idea_ids,
            [
                {
                    "name": "workflow teardown post",
                    "description": "Publish a practical before-and-after workflow example.",
                    "owner": "developer relations" if "developer" in domain else "community lead",
                }
            ],
        ),
    ]
    channel_specs.sort(key=lambda item: (-item["score"], item["id"]))
    for priority, recommendation in enumerate(channel_specs, 1):
        recommendation["priority"] = priority
        recommendation["confidence"] = _confidence(recommendation["score"], bool(evidence_refs))
        recommendation["message_angle"] = context["positioning"]
    return channel_specs


def _channel_spec(
    id: str,
    channel: str,
    type: str,
    motion: str,
    audience: str,
    owner: str,
    score: int,
    rationale: str,
    call_to_action: str,
    metric: str,
    target: str,
    source_fields: list[str],
    evidence_refs: list[str],
    source_idea_ids: list[str],
    tactics: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": id,
        "channel": channel,
        "type": type,
        "priority": 0,
        "score": min(score, 100),
        "audience": audience,
        "owner": owner,
        "motion": motion,
        "rationale": rationale,
        "call_to_action": call_to_action,
        "message_angle": "",
        "tactics": tactics,
        "success_metric": {"metric": metric, "target": target},
        "source_fields": source_fields,
        "evidence_refs": evidence_refs,
        "source_idea_ids": source_idea_ids,
        "confidence": "low",
    }


def _brief_context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "domain": _clean(design_brief.get("domain")) or "general",
        "readiness_score": str(float(design_brief.get("readiness_score") or 0.0)),
        "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "economic buyer"),
        "target_user": _first_text(
            design_brief.get("specific_user"),
            _field_values(source_ideas, "specific_user"),
            "target user",
        ),
        "workflow": _first_text(
            design_brief.get("workflow_context"),
            _field_values(source_ideas, "workflow_context"),
            design_brief.get("theme"),
            "target workflow",
        ),
        "positioning": _first_text(
            design_brief.get("merged_product_concept"),
            _field_values(source_ideas, "value_proposition"),
            design_brief.get("why_this_now"),
            design_brief.get("title"),
        ),
    }


def _sequencing(recommendations: list[dict[str, Any]], design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    validation_plan = _clean(design_brief.get("validation_plan")) or "Confirm channel-message fit."
    return [
        {
            "phase": "validation",
            "goal": "Prove message-channel fit with named users before broad spend.",
            "channels": [recommendations[0]["channel"], recommendations[1]["channel"]],
            "guidance": validation_plan,
            "exit_criteria": "At least three qualified conversations confirm urgency and wording.",
        },
        {
            "phase": "repeatability",
            "goal": "Turn confirmed demand into a repeatable pipeline source.",
            "channels": [recommendations[1]["channel"], recommendations[2]["channel"]],
            "guidance": "Reuse validated language and compare channel conversion by audience quality.",
            "exit_criteria": "One repeatable source produces qualified follow-up meetings for two consecutive cycles.",
        },
        {
            "phase": "scale",
            "goal": "Expand through partner or sales-assisted motion only after validation metrics hold.",
            "channels": [recommendations[2]["channel"], "integration partner co-sell"],
            "guidance": "Scale the highest-confidence channel and keep partner motion gated by proof.",
            "exit_criteria": "Acquisition cost and pilot conversion remain inside launch guardrails.",
        },
    ]


def _measurement_plan(context: dict[str, str], recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
    primary = recommendations[0]["success_metric"]
    return [
        {
            "metric": primary["metric"],
            "definition": f"Share of {recommendations[0]['channel']} responses that match {context['target_user']} and {context['workflow']}.",
            "target": primary["target"],
        },
        {
            "metric": "pilot_conversion_rate",
            "definition": "Share of qualified conversations that convert to a pilot or design partner.",
            "target": "20%+ before scaling spend",
        },
        {
            "metric": "channel_learning_cycle_time",
            "definition": "Days from first channel touch to a decision to continue, revise, or stop that channel.",
            "target": "14 days or less during validation",
        },
    ]


def _risk_plan(design_brief: dict[str, Any], recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
    risks = _string_list(design_brief.get("risks"))
    if not risks:
        risks = ["Channel response may not prove willingness to adopt."]
    return [
        {
            "id": f"R{index}",
            "risk": risk,
            "mitigation": f"Validate through {recommendations[0]['channel']} before scaling {recommendations[-1]['channel']}.",
            "owner": recommendations[0]["owner"],
        }
        for index, risk in enumerate(risks, 1)
    ]


def _channel_groups(
    recommendations: list[dict[str, Any]],
    context: dict[str, str],
    evidence_refs: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "acquisition": [],
        "partner": [],
        "community": [],
        "sales_assisted": [],
    }
    for recommendation in recommendations:
        key = "sales_assisted" if recommendation["type"] == "sales-assisted" else recommendation["type"]
        groups.setdefault(key, []).append(
            {
                "id": recommendation["id"],
                "channel": recommendation["channel"],
                "priority": recommendation["priority"],
                "owner": recommendation["owner"],
                "confidence": recommendation["confidence"],
            }
        )
    groups["partner"].append(
        {
            "id": "GTM-P1",
            "channel": "integration partner co-sell",
            "priority": len(recommendations) + 1,
            "owner": "partnerships",
            "confidence": "medium" if evidence_refs else "low",
            "rationale": (
                f"Partners near {context['workflow']} can introduce trusted accounts once "
                "validation language is stable."
            ),
        }
    )
    return groups


def _missing_inputs(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for field, reason in _REQUIRED_FIELDS:
        value = design_brief.get(field)
        if field == "source_idea_ids":
            is_missing = not source_ideas
        elif field == "risks":
            is_missing = not _string_list(value)
        else:
            is_missing = not _clean(value)
        if is_missing:
            missing.append({"field": field, "reason": reason})
    return missing


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_by_id = {
        source["idea_id"]: source
        for source in design_brief.get("sources", [])
        if source.get("idea_id")
    }
    ordered_ids = list(
        dict.fromkeys(
            [
                design_brief.get("lead_idea_id"),
                *list(design_brief.get("source_idea_ids") or []),
                *relationship_by_id.keys(),
            ]
        )
    )

    ideas: list[dict[str, Any]] = []
    for idea_id in ordered_ids:
        if not idea_id:
            continue
        unit = store.get_buildable_unit(str(idea_id))
        if not unit:
            ideas.append({"id": str(idea_id), "missing": True})
            continue
        data = unit.model_dump(mode="json")
        relationship = relationship_by_id.get(str(idea_id), {})
        data["role"] = relationship.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = relationship.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _evidence_references(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signal_ids: set[str] = set()
    insight_ids: set[str] = set()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        signal_ids.update(_string_list(idea.get("evidence_signals")))
        insight_ids.update(_string_list(idea.get("inspiring_insights")))

    for insight_id in sorted(insight_ids):
        insight = store.get_insight(insight_id)
        if insight:
            signal_ids.update(_string_list(getattr(insight, "evidence", [])))

    references: list[dict[str, Any]] = []
    for signal_id in sorted(signal_ids):
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        references.append(
            {
                "id": signal.id,
                "source_type": _source_type(signal),
                "source_adapter": str(getattr(signal, "source_adapter", "") or "unknown"),
                "title": signal.title,
                "url": signal.url,
                "credibility": round(float(signal.credibility or 0.0), 2),
                "tags": list(signal.tags),
                "signal_role": str(getattr(signal, "signal_role", "") or ""),
            }
        )
    references.sort(key=lambda item: item["id"])
    return references


def _market_signal_counts(evidence_refs: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = Counter(reference["source_type"] for reference in evidence_refs)
    by_role = Counter(reference.get("signal_role") or "unknown" for reference in evidence_refs)
    return {
        "total": len(evidence_refs),
        "survey": by_type.get("survey", 0),
        "funding": by_type.get("funding", 0),
        "forum": by_type.get("forum", 0),
        "social": by_type.get("social", 0),
        "by_source_type": dict(sorted(by_type.items())),
        "by_signal_role": dict(sorted(by_role.items())),
    }


def _source_type(signal: Any) -> str:
    source_type = getattr(signal, "source_type", "")
    return str(getattr(source_type, "value", source_type) or "unknown")


def _source_idea_ids(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    return ids or [str(idea_id) for idea_id in design_brief.get("source_idea_ids") or []]


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [_clean(idea.get(field)) for idea in source_ideas if _clean(idea.get(field))]


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _readiness_points(readiness: float) -> int:
    if readiness >= 80:
        return 16
    if readiness >= 60:
        return 10
    if readiness >= 40:
        return 5
    return 0


def _signal_points(market_signals: dict[str, Any], signal_types: tuple[str, ...]) -> int:
    return min(12, sum(int(market_signals.get(signal_type, 0)) for signal_type in signal_types) * 4)


def _confidence(score: int, has_evidence: bool) -> str:
    if score >= 56 and has_evidence:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _overall_confidence(recommendations: list[dict[str, Any]], missing_inputs: list[dict[str, str]]) -> str:
    if missing_inputs:
        return "low"
    if recommendations[0]["confidence"] == "high":
        return "high"
    return "medium"


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
