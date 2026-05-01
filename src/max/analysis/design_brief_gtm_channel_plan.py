"""Deterministic GTM channel plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any

from max.store.db import Store

KIND = "max.design_brief.gtm_channel_plan"
SCHEMA_VERSION = "max.design_brief.gtm_channel_plan.v1"


def build_design_brief_gtm_channel_plan(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a GTM channel plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [str(idea["id"]) for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = [str(idea_id) for idea_id in design_brief.get("source_idea_ids") or []]

    buyer = _first_text(design_brief.get("buyer"), "economic buyer")
    target_user = _first_text(design_brief.get("specific_user"), "target user")
    workflow = _first_text(design_brief.get("workflow_context"), design_brief.get("theme"), "workflow")
    value_proposition = _first_text(
        design_brief.get("merged_product_concept"),
        design_brief.get("why_this_now"),
        design_brief.get("title"),
    )
    recommendations = _channel_recommendations(
        buyer=buyer,
        target_user=target_user,
        workflow=workflow,
        value_proposition=value_proposition,
        source_idea_ids=source_idea_ids,
    )

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
        },
        "summary": {
            "primary_audience": target_user,
            "buyer": buyer,
            "workflow_context": workflow,
            "positioning": value_proposition,
            "recommended_channel_count": len(recommendations),
            "primary_channel": recommendations[0]["channel"],
        },
        "channel_recommendations": recommendations,
        "launch_sequence": [
            {
                "phase": "validation",
                "goal": "Prove message-channel fit with named users before broad spend.",
                "channels": [recommendations[0]["channel"], recommendations[1]["channel"]],
                "exit_criteria": "At least three qualified conversations confirm urgency and wording.",
            },
            {
                "phase": "pipeline",
                "goal": "Convert confirmed demand into repeatable qualified opportunities.",
                "channels": [recommendations[1]["channel"], recommendations[2]["channel"]],
                "exit_criteria": "A repeatable source produces qualified follow-up meetings.",
            },
        ],
        "measurement_plan": [
            {
                "metric": "qualified_conversation_rate",
                "definition": "Share of channel responses that match the target user and workflow.",
                "target": "25%+ during validation",
            },
            {
                "metric": "pilot_conversion_rate",
                "definition": "Share of qualified conversations that convert to a pilot or design partner.",
                "target": "20%+ before scaling spend",
            },
        ],
        "source_ideas": source_ideas,
    }


def render_design_brief_gtm_channel_plan(report: dict[str, Any], fmt: str = "json") -> str:
    """Render the GTM channel plan as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported GTM channel plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# GTM Channel Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        "",
        "## Summary",
        "",
        f"- Primary audience: {summary['primary_audience']}",
        f"- Buyer: {summary['buyer']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Primary channel: {summary['primary_channel']}",
        "",
        "## Channel Recommendations",
        "",
    ]
    for recommendation in report["channel_recommendations"]:
        lines.extend(
            [
                f"### {recommendation['priority']}. {recommendation['channel']}",
                "",
                f"- Audience: {recommendation['audience']}",
                f"- Motion: {recommendation['motion']}",
                f"- Rationale: {recommendation['rationale']}",
                f"- CTA: {recommendation['call_to_action']}",
                f"- Success metric: {recommendation['success_metric']['metric']} - {recommendation['success_metric']['target']}",
                "",
            ]
        )
        for tactic in recommendation["tactics"]:
            lines.append(f"- Tactic: {tactic['name']} - {tactic['description']}")
        lines.append("")

    lines.extend(["## Launch Sequence", ""])
    for phase in report["launch_sequence"]:
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

    return "\n".join(lines).rstrip() + "\n"


def gtm_channel_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a GTM channel plan export."""
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    return f"{brief_id}-gtm-channel-plan.{extension}"


def _channel_recommendations(
    *,
    buyer: str,
    target_user: str,
    workflow: str,
    value_proposition: str,
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "GTM1",
            "channel": "design partner outreach",
            "priority": 1,
            "audience": target_user,
            "motion": "direct validation",
            "rationale": f"Direct outreach is the fastest way to confirm {workflow} urgency.",
            "call_to_action": "Schedule a 30-minute workflow review.",
            "message_angle": value_proposition,
            "tactics": [
                {
                    "name": "warm account list",
                    "description": f"Identify existing relationships with {target_user} ownership.",
                    "owner": "product marketing",
                },
                {
                    "name": "problem-led email",
                    "description": f"Lead with the {workflow} pain and request validation.",
                    "owner": "founder or product lead",
                },
            ],
            "success_metric": {
                "metric": "qualified_conversation_rate",
                "target": "25%+ positive replies from qualified accounts",
            },
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "GTM2",
            "channel": "buyer enablement content",
            "priority": 2,
            "audience": buyer,
            "motion": "education",
            "rationale": f"{buyer} needs a concise business case before sponsoring rollout.",
            "call_to_action": "Review the pilot business case.",
            "message_angle": value_proposition,
            "tactics": [
                {
                    "name": "one-page business case",
                    "description": "Translate the design brief into pain, outcome, proof, and next step.",
                    "owner": "go-to-market lead",
                }
            ],
            "success_metric": {
                "metric": "buyer_review_rate",
                "target": "10+ buyer reviews before broad launch",
            },
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "GTM3",
            "channel": "community proof loop",
            "priority": 3,
            "audience": target_user,
            "motion": "credible demand capture",
            "rationale": "Community posts can test wording and collect proof points without paid spend.",
            "call_to_action": "Join the pilot waitlist.",
            "message_angle": value_proposition,
            "tactics": [
                {
                    "name": "workflow teardown post",
                    "description": "Publish a practical before-and-after workflow example.",
                    "owner": "developer relations",
                }
            ],
            "success_metric": {
                "metric": "waitlist_quality_rate",
                "target": "50%+ of signups match the target workflow",
            },
            "source_idea_ids": source_idea_ids,
        },
    ]


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas = []
    for idea_id in design_brief.get("source_idea_ids") or []:
        unit = store.get_buildable_unit(str(idea_id))
        if not unit:
            ideas.append({"id": str(idea_id), "missing": True})
            continue
        ideas.append(
            {
                "id": unit.id,
                "title": unit.title,
                "role": "lead" if unit.id == design_brief.get("lead_idea_id") else "supporting",
                "buyer": unit.buyer,
                "specific_user": unit.specific_user,
                "workflow_context": unit.workflow_context,
                "status": unit.status,
            }
        )
    return ideas


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
