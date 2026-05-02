"""Deterministic customer journey maps for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from max.store.db import Store

KIND = "max.design_brief.customer_journey_map"
SCHEMA_VERSION = "max.design_brief.customer_journey_map.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "readiness_score",
    "sequence",
    "stage_id",
    "name",
    "owner",
    "user_goals",
    "touchpoints",
    "friction_points",
    "success_signals",
    "evidence_reference_ids",
    "source_idea_ids",
)


def build_design_brief_customer_journey_map(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a customer journey map from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _journey_context(design_brief, source_ideas, lead_idea)
    evidence = _evidence_references(design_brief, source_ideas)
    warnings = _readiness_warnings(design_brief, context, evidence)
    stages = _journey_stages(design_brief, context, evidence, source_idea_ids)
    pain_points = _pain_points(stages)
    moments_of_value = _moments_of_value(stages)

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
            "journey_goal": f"Map how {context['target_user']} adopts {design_brief['title']} from problem awareness to ongoing value.",
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "current_workaround": context["current_workaround"],
            "value_proposition": context["value_proposition"],
            "fallbacks_used": context["fallbacks_used"],
            "stage_count": len(stages),
            "evidence_reference_count": len(evidence),
            "readiness_warning_count": len(warnings),
        },
        "journey_stages": stages,
        "pain_points": pain_points,
        "moments_of_value": moments_of_value,
        "follow_up_actions": _follow_up_actions(warnings, stages),
        "evidence_references": evidence,
        "readiness_warnings": warnings,
        "source_ideas": source_ideas,
    }


def render_design_brief_customer_journey_map(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render a customer journey map as JSON, CSV, or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported customer journey map format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Customer Journey Map: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Journey Context",
        "",
        f"- Goal: {summary['journey_goal']}",
        f"- Target user: {summary['target_user']}",
        f"- Buyer: {summary['buyer']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Current workaround: {summary['current_workaround']}",
        f"- Value proposition: {summary['value_proposition']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Journey Stages",
        "",
    ]

    for stage in report["journey_stages"]:
        lines.extend(
            [
                f"### {stage['sequence']}. {stage['name']}",
                "",
                f"- ID: `{stage['id']}`",
                f"- Owner: {stage['owner']}",
                f"- User goals: {_inline_list(stage['user_goals'])}",
                f"- Touchpoints: {_inline_list(stage['touchpoints'])}",
                f"- Friction points: {_inline_list(stage['friction_points'])}",
                f"- Success signals: {_inline_list(stage['success_signals'])}",
                f"- Evidence references: {_inline_ids(stage['evidence_reference_ids'])}",
                f"- Source ideas: {_inline_ids(stage['source_idea_ids'])}",
                "",
            ]
        )

    lines.extend(["## Pain Points", ""])
    for point in report.get("pain_points") or []:
        lines.append(f"- **{point['stage_name']}**: {point['pain_point']}")

    lines.extend(["", "## Moments of Value", ""])
    for moment in report.get("moments_of_value") or []:
        lines.append(f"- **{moment['stage_name']}**: {moment['moment']}")

    lines.extend(["", "## Follow-up Actions", ""])
    for action in report.get("follow_up_actions") or []:
        lines.append(f"- **{action['owner']}**: {action['action']}")

    lines.extend(["## Evidence References", ""])
    if report["evidence_references"]:
        for reference in report["evidence_references"]:
            lines.append(f"- **{reference['id']}** ({reference['type']}): {reference['summary']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Readiness Warnings", ""])
    if report["readiness_warnings"]:
        for warning in report["readiness_warnings"]:
            lines.append(f"- **{warning['severity']}**: {warning['warning']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(_csv_rows(report))
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    stages = [stage for stage in report.get("journey_stages") or [] if isinstance(stage, dict)]
    return [_csv_row(report, stage) for stage in sorted(stages, key=_stage_sequence)]


def _stage_sequence(stage: dict[str, Any]) -> tuple[int, str]:
    try:
        sequence = int(stage.get("sequence") or 0)
    except (TypeError, ValueError):
        sequence = 0
    return (sequence, str(stage.get("id") or ""))


def _csv_row(report: dict[str, Any], stage: dict[str, Any]) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    row = {
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "readiness_score": brief.get("readiness_score"),
        "sequence": stage.get("sequence"),
        "stage_id": stage.get("id"),
        "name": stage.get("name"),
        "owner": stage.get("owner"),
        "user_goals": stage.get("user_goals"),
        "touchpoints": stage.get("touchpoints"),
        "friction_points": stage.get("friction_points"),
        "success_signals": stage.get("success_signals"),
        "evidence_reference_ids": stage.get("evidence_reference_ids"),
        "source_idea_ids": stage.get("source_idea_ids") or brief.get("source_idea_ids"),
    }
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ";".join(_csv_text(item) for item in value if _csv_text(item))
    return str(value)


def _journey_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    title = str(design_brief["title"])
    fallbacks: list[str] = []
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea"),
        (_field_values(source_ideas, "specific_user"), "source_ideas"),
        (f"{title} user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea"),
        (_field_values(source_ideas, "buyer"), "source_ideas"),
        ("customer sponsor", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas"),
        (f"{title} workflow", "explicit_fallback"),
    )
    workaround = _first_with_label(
        fallbacks,
        "current_workaround",
        (lead_idea and lead_idea.get("current_workaround"), "lead_idea"),
        (_field_values(source_ideas, "current_workaround"), "source_ideas"),
        ("manual or ad hoc workflow", "explicit_fallback"),
    )
    value = _first_with_label(
        fallbacks,
        "value_proposition",
        (design_brief.get("merged_product_concept"), "design_brief"),
        (lead_idea and lead_idea.get("value_proposition"), "lead_idea"),
        (_field_values(source_ideas, "value_proposition"), "source_ideas"),
        (f"Help {target_user} improve {workflow}.", "explicit_fallback"),
    )
    validation = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        "Confirm the journey creates first value, repeat usage, and sponsor acceptance.",
    )
    return {
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "current_workaround": workaround,
        "value_proposition": value,
        "primary_scope": _first_text(_string_list(design_brief.get("mvp_scope")), f"first usable {title} workflow"),
        "first_milestone": _first_text(
            _string_list(design_brief.get("first_milestones")),
            "first successful customer journey",
        ),
        "validation_plan": validation,
        "primary_risk": _first_text(
            _string_list(design_brief.get("risks")),
            _source_risks(source_ideas),
            "Adoption may stall before repeat usage is proven.",
        ),
        "fallbacks_used": fallbacks,
    }


def _journey_stages(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    evidence: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    evidence_ids = [reference["id"] for reference in evidence]
    return [
        _stage(
            "JM1",
            1,
            "Problem Awareness",
            "Product marketing owner",
            [
                f"Recognize that {context['current_workaround']} is limiting {context['workflow_context']}.",
                f"Understand why {design_brief['title']} is relevant now.",
            ],
            [
                "problem narrative",
                "discovery conversation",
                "evidence-backed launch note",
            ],
            [
                "The pain is described too generally to trigger action.",
                f"{context['target_user']} cannot connect the message to their daily workflow.",
            ],
            [
                "Target user can restate the problem in their own words.",
                "Buyer agrees the problem belongs in the current planning cycle.",
            ],
            evidence_ids[:2] or evidence_ids,
            source_idea_ids,
        ),
        _stage(
            "JM2",
            2,
            "Solution Evaluation",
            "Product lead",
            [
                f"Decide whether the proposed value is credible for {context['workflow_context']}.",
                f"Compare the MVP boundary against {context['current_workaround']}.",
            ],
            [
                "design brief walkthrough",
                "MVP scope review",
                "buyer or champion validation call",
            ],
            [
                f"Scope around {context['primary_scope']} may feel incomplete or unclear.",
                "Sponsor and user criteria may differ before a pilot is approved.",
            ],
            [
                f"{context['buyer']} accepts the first-use success definition.",
                "Pilot stakeholders agree what is out of scope for the first journey.",
            ],
            evidence_ids,
            source_idea_ids,
        ),
        _stage(
            "JM3",
            3,
            "First Use",
            "Customer success lead",
            [
                f"Complete {context['first_milestone']} with enough guidance to reach first value.",
                "Expose blockers before they become silent abandonment.",
            ],
            [
                "kickoff session",
                "guided setup",
                "first-value checklist",
            ],
            [
                f"Existing workaround habits can pull users back to {context['current_workaround']}.",
                context["primary_risk"],
            ],
            [
                f"At least one {context['target_user']} completes the target workflow.",
                "Setup friction, support requests, and recovery actions are logged.",
            ],
            evidence_ids,
            source_idea_ids,
        ),
        _stage(
            "JM4",
            4,
            "Repeat Adoption",
            "Product enablement owner",
            [
                "Turn first use into a repeatable behavior for the same user or next teammate.",
                "Reduce dependency on concierge support.",
            ],
            [
                "quickstart guide",
                "support follow-up",
                "champion enablement",
            ],
            [
                "User may succeed once but fail to repeat the journey independently.",
                "Enablement assets may not answer buyer or support questions.",
            ],
            [
                "Customer repeats the workflow or onboards a second user.",
                "Support questions decrease or resolve through documented guidance.",
            ],
            evidence_ids[-2:] if len(evidence_ids) > 1 else evidence_ids,
            source_idea_ids,
        ),
        _stage(
            "JM5",
            5,
            "Expansion Decision",
            "Customer owner",
            [
                f"Help {context['buyer']} decide whether the journey merits broader rollout.",
                "Convert validation evidence into a clear continue, pause, or expand decision.",
            ],
            [
                "adoption review",
                "success criteria recap",
                "roadmap or expansion planning",
            ],
            [
                "Outcome evidence may not be tied back to the original design brief claims.",
                "Unresolved risks can delay rollout even after successful first use.",
            ],
            [
                context["validation_plan"],
                "Sponsor accepts the next adoption step and owner.",
            ],
            evidence_ids,
            source_idea_ids,
        ),
    ]


def _stage(
    stage_id: str,
    sequence: int,
    name: str,
    owner: str,
    user_goals: list[str],
    touchpoints: list[str],
    friction_points: list[str],
    success_signals: list[str],
    evidence_reference_ids: list[str],
    source_idea_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": stage_id,
        "sequence": sequence,
        "name": name,
        "owner": owner,
        "user_goals": user_goals,
        "touchpoints": touchpoints,
        "friction_points": friction_points,
        "success_signals": success_signals,
        "evidence_reference_ids": evidence_reference_ids,
        "source_idea_ids": source_idea_ids,
    }


def _pain_points(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{stage['id']}-P{index}",
            "stage_id": stage["id"],
            "stage_name": stage["name"],
            "pain_point": point,
            "source_idea_ids": stage["source_idea_ids"],
        }
        for stage in stages
        for index, point in enumerate(stage["friction_points"], start=1)
    ]


def _moments_of_value(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{stage['id']}-V{index}",
            "stage_id": stage["id"],
            "stage_name": stage["name"],
            "moment": signal,
            "source_idea_ids": stage["source_idea_ids"],
        }
        for stage in stages
        for index, signal in enumerate(stage["success_signals"], start=1)
    ]


def _follow_up_actions(
    warnings: list[dict[str, Any]],
    stages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions = [
        {
            "id": f"FA{index}",
            "owner": "Product lead",
            "action": warning["recommended_action"],
            "source": warning["id"],
            "stage_id": None,
        }
        for index, warning in enumerate(warnings, start=1)
    ]
    if not actions:
        actions.append(
            {
                "id": "FA1",
                "owner": stages[-1]["owner"] if stages else "Product lead",
                "action": "Review journey evidence after first use and decide whether to continue, pause, or expand.",
                "source": "journey_stages",
                "stage_id": stages[-1]["id"] if stages else None,
            }
        )
    return actions


def _evidence_references(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field in ("why_this_now", "synthesis_rationale", "validation_plan"):
        text = _first_text(design_brief.get(field))
        if text:
            refs.append(
                {
                    "id": f"design_brief.{field}",
                    "type": "brief_field",
                    "summary": text,
                    "source_idea_ids": list(design_brief.get("source_idea_ids") or []),
                }
            )
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            refs.append(
                {
                    "id": signal_id,
                    "type": "evidence_signal",
                    "summary": f"Evidence signal linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "insight",
                    "summary": f"Inspiring insight linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
    return _dedupe_refs(refs)


def _readiness_warnings(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    readiness = float(design_brief.get("readiness_score") or 0.0)
    status = str(design_brief.get("design_status") or "")
    if readiness < 75:
        warnings.append(
            {
                "id": "RW1",
                "severity": "medium" if readiness >= 50 else "high",
                "warning": f"Readiness score is {readiness:.1f}/100; validate the journey before broad adoption planning.",
                "recommended_action": "Use the journey map for controlled pilots until readiness improves.",
            }
        )
    if status not in {"approved", "published"}:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "high",
                "warning": f"Design status is `{status or 'unknown'}`; customer journey assumptions need approval.",
                "recommended_action": "Confirm design approval before treating the journey as launch guidance.",
            }
        )
    for fallback in context["fallbacks_used"]:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "medium",
                "warning": f"Missing {fallback}; journey stages use explicit fallback context.",
                "recommended_action": f"Fill design_brief.{fallback} or source idea context before customer rollout.",
            }
        )
    if not evidence:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "medium",
                "warning": "No evidence references were found for journey assumptions.",
                "recommended_action": "Attach validation plan, rationale, signals, or insights before expansion planning.",
            }
        )
    return warnings


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


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        if not idea.get("missing"):
            risks.extend(_string_list(idea.get("domain_risks")))
    return risks


def _first_with_label(
    fallbacks: list[str],
    field: str,
    *candidates: tuple[Any, str],
) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        deduped.setdefault(ref["id"], ref)
    return list(deduped.values())


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _inline_list(values: list[str]) -> str:
    return "; ".join(values) if values else "none"


def customer_journey_map_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "md" if fmt == "markdown" else fmt
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'customer-journey-map'))}-"
        f"customer-journey-map.{extension}"
    )


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "untitled"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
