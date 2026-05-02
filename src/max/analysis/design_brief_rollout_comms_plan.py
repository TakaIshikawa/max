"""Deterministic rollout communications plans for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from max.store.db import Store

KIND = "max.design_brief.rollout_comms_plan"
SCHEMA_VERSION = "max.design_brief.rollout_comms_plan.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "audience",
    "channel",
    "timing",
    "owner",
    "message",
    "call_to_action",
    "details",
)


def build_design_brief_rollout_comms_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a rollout communications plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _rollout_context(design_brief, source_ideas, lead_idea)
    audiences = _target_audiences(context, source_idea_ids)
    phases = _launch_phases(design_brief, context, source_idea_ids)
    matrix = _channel_message_matrix(context, audiences, phases, source_idea_ids)
    enablement = _internal_enablement_notes(design_brief, context, source_idea_ids)
    announcements = _customer_facing_announcements(design_brief, context, source_idea_ids)
    faq_hooks = _risk_faq_hooks(design_brief, source_ideas, source_idea_ids)
    evidence = _evidence_references(design_brief, source_ideas)
    warnings = _readiness_warnings(design_brief, context, evidence)

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
            "rollout_goal": f"Coordinate rollout communications for {design_brief['title']}.",
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "value_proposition": context["value_proposition"],
            "primary_message": context["primary_message"],
            "fallbacks_used": context["fallbacks_used"],
            "audience_count": len(audiences),
            "launch_phase_count": len(phases),
            "message_count": len(matrix),
            "readiness_warning_count": len(warnings),
        },
        "target_audiences": audiences,
        "launch_phases": phases,
        "channel_message_matrix": matrix,
        "internal_enablement_notes": enablement,
        "customer_facing_announcement_drafts": announcements,
        "risk_faq_hooks": faq_hooks,
        "evidence_references": evidence,
        "readiness_warnings": warnings,
        "source_ideas": source_ideas,
    }


def render_design_brief_rollout_comms_plan(report: dict[str, Any], fmt: str = "json") -> str:
    """Render the rollout communications plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt == "csv":
        return render_design_brief_rollout_comms_plan_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported rollout communications plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Rollout Communications Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Rollout Context",
        "",
        f"- Goal: {summary['rollout_goal']}",
        f"- Target user: {summary['target_user']}",
        f"- Buyer: {summary['buyer']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Primary message: {summary['primary_message']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Target Audiences",
        "",
    ]

    for audience in report["target_audiences"]:
        lines.extend(
            [
                f"### {audience['name']}",
                "",
                f"- Type: {audience['type']}",
                f"- Need: {audience['need']}",
                f"- Message angle: {audience['message_angle']}",
                f"- Preferred channels: {', '.join(audience['preferred_channels'])}",
                "",
            ]
        )

    lines.extend(["## Launch Phase Sequencing", ""])
    for phase in report["launch_phases"]:
        lines.extend(
            [
                f"### {phase['sequence']}. {phase['name']}",
                "",
                f"- Timing: {phase['timing']}",
                f"- Objective: {phase['objective']}",
                f"- Owner: {phase['owner']}",
                f"- Exit criteria: {phase['exit_criteria']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Channel Message Matrix",
            "",
            "| Phase | Audience | Channel | Message | CTA |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["channel_message_matrix"]:
        lines.append(
            "| "
            f"{row['phase']} | {row['audience']} | {row['channel']} | "
            f"{row['message']} | {row['call_to_action']} |"
        )

    lines.extend(["", "## Internal Enablement Notes", ""])
    for note in report["internal_enablement_notes"]:
        lines.extend(
            [
                f"### {note['id']}: {note['topic']}",
                "",
                f"- Owner: {note['owner']}",
                f"- Detail: {note['detail']}",
                f"- Source fields: {', '.join(note['source_fields'])}",
                "",
            ]
        )

    lines.extend(["## Customer-Facing Announcement Drafts", ""])
    for draft in report["customer_facing_announcement_drafts"]:
        lines.extend(
            [
                f"### {draft['name']}",
                "",
                f"- Channel: {draft['channel']}",
                f"- Audience: {draft['audience']}",
                f"- Headline: {draft['headline']}",
                "",
                draft["body"],
                "",
                f"- CTA: {draft['call_to_action']}",
                "",
            ]
        )

    lines.extend(["## Risk and FAQ Hooks", ""])
    for hook in report["risk_faq_hooks"]:
        lines.extend(
            [
                f"### {hook['id']}: {hook['question']}",
                "",
                f"- Answer hook: {hook['answer_hook']}",
                f"- Source: {hook['source']}",
                "",
            ]
        )

    lines.extend(["## Evidence References", ""])
    if report["evidence_references"]:
        for item in report["evidence_references"]:
            lines.append(f"- **{item['id']}** ({item['type']}): {item['summary']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Readiness Warnings", ""])
    if report["readiness_warnings"]:
        for warning in report["readiness_warnings"]:
            lines.append(f"- **{warning['severity']}**: {warning['warning']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def rollout_comms_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a rollout communications plan export."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    title = _filename_part(str(design_brief.get("title") or "rollout-comms-plan"))
    return f"{brief_id}-{title}-rollout-comms-plan.{extension}"


def render_design_brief_rollout_comms_plan_csv(report: dict[str, Any]) -> str:
    """Render rollout communication items as deterministic CSV rows."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for audience in report.get("target_audiences") or []:
        rows.append(
            _csv_row(
                report,
                section="target_audiences",
                item_id=audience.get("id"),
                audience=audience.get("name"),
                channel=audience.get("preferred_channels"),
                message=audience.get("message_angle"),
                details={
                    "type": audience.get("type"),
                    "need": audience.get("need"),
                    "source_idea_ids": audience.get("source_idea_ids") or [],
                },
            )
        )

    for phase in report.get("launch_phases") or []:
        rows.append(
            _csv_row(
                report,
                section="launch_phases",
                item_id=phase.get("id"),
                timing=phase.get("timing"),
                owner=phase.get("owner"),
                message=phase.get("objective"),
                call_to_action=phase.get("exit_criteria"),
                details={
                    "sequence": phase.get("sequence"),
                    "name": phase.get("name"),
                    "source_idea_ids": phase.get("source_idea_ids") or [],
                },
            )
        )

    for item in report.get("channel_message_matrix") or []:
        rows.append(
            _csv_row(
                report,
                section="channel_message_matrix",
                item_id=item.get("id"),
                audience=item.get("audience"),
                channel=item.get("channel"),
                timing=item.get("phase"),
                owner=item.get("owner"),
                message=item.get("message"),
                call_to_action=item.get("call_to_action"),
                details={
                    "phase_id": item.get("phase_id"),
                    "audience_id": item.get("audience_id"),
                    "source_fields": item.get("source_fields") or [],
                    "source_idea_ids": item.get("source_idea_ids") or [],
                },
            )
        )

    for note in report.get("internal_enablement_notes") or []:
        rows.append(
            _csv_row(
                report,
                section="internal_enablement_notes",
                item_id=note.get("id"),
                channel="enablement note",
                owner=note.get("owner"),
                message=note.get("detail"),
                details={
                    "topic": note.get("topic"),
                    "source_fields": note.get("source_fields") or [],
                    "source_idea_ids": note.get("source_idea_ids") or [],
                },
            )
        )

    for draft in report.get("customer_facing_announcement_drafts") or []:
        rows.append(
            _csv_row(
                report,
                section="customer_facing_announcement_drafts",
                item_id=draft.get("id"),
                audience=draft.get("audience"),
                channel=draft.get("channel"),
                message=draft.get("body"),
                call_to_action=draft.get("call_to_action"),
                details={
                    "name": draft.get("name"),
                    "headline": draft.get("headline"),
                    "source_fields": draft.get("source_fields") or [],
                    "source_idea_ids": draft.get("source_idea_ids") or [],
                },
            )
        )

    for hook in report.get("risk_faq_hooks") or []:
        rows.append(
            _csv_row(
                report,
                section="risk_faq_hooks",
                item_id=hook.get("id"),
                channel="FAQ",
                message=hook.get("question"),
                call_to_action=hook.get("answer_hook"),
                details={
                    "source": hook.get("source"),
                    "source_idea_ids": hook.get("source_idea_ids") or [],
                },
            )
        )

    return rows


def _csv_row(report: dict[str, Any], *, section: str, **values: Any) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    row = {
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "section": section,
        "item_id": values.get("item_id"),
        "audience": values.get("audience"),
        "channel": values.get("channel"),
        "timing": values.get("timing"),
        "owner": values.get("owner"),
        "message": values.get("message"),
        "call_to_action": values.get("call_to_action"),
        "details": values.get("details"),
    }
    return {column: _csv_cell(row.get(column)) for column in CSV_COLUMNS}


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _rollout_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("rollout sponsor", "explicit_fallback"),
    )
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    value = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("value_proposition"),
        lead_idea and lead_idea.get("solution"),
        f"{title} helps {target_user} complete {workflow}.",
    )
    why_now = _first_text(
        design_brief.get("why_this_now"),
        lead_idea and lead_idea.get("why_now"),
        "The rollout is ready for a coordinated audience handoff.",
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        "Confirm rollout messages with the first launch cohort.",
    )
    primary_message = (
        f"{title} helps {target_user} improve {workflow} by {value}"
        if value != title
        else f"{title} is ready for controlled rollout to {target_user}."
    )
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "value_proposition": value,
        "why_now": why_now,
        "primary_scope": scope[0] if scope else f"first usable {title} workflow",
        "first_milestone": milestones[0] if milestones else "complete controlled rollout",
        "validation_plan": validation_plan,
        "primary_message": primary_message,
        "fallbacks_used": fallbacks,
    }


def _target_audiences(context: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "internal_product_engineering",
            "name": "Internal product and engineering",
            "type": "internal",
            "need": "Understand scope, owner handoffs, validation gates, and rollback triggers.",
            "message_angle": f"Focus rollout on {context['primary_scope']}.",
            "preferred_channels": ["launch brief", "engineering sync"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "internal_sales_success_support",
            "name": "Sales, success, and support",
            "type": "internal",
            "need": "Explain who should hear about the launch and how to answer first questions.",
            "message_angle": f"Position the launch around {context['workflow_context']}.",
            "preferred_channels": ["enablement note", "support macro"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "pilot_customers",
            "name": "Pilot customers",
            "type": "external",
            "need": "Know what changed, why it matters, and how to try it safely.",
            "message_angle": f"Help {context['target_user']} get early value in {context['workflow_context']}.",
            "preferred_channels": ["email", "in-app message"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "external_market",
            "name": "External market",
            "type": "external",
            "need": "Hear a concise announcement once validation and support readiness are confirmed.",
            "message_angle": context["why_now"],
            "preferred_channels": ["changelog", "blog"],
            "source_idea_ids": source_ids,
        },
    ]


def _launch_phases(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    gate = _launch_gate(design_brief)
    return [
        {
            "id": "prep",
            "sequence": 1,
            "name": "Prep and message lock",
            "timing": "T-10 to T-5 business days",
            "objective": "Confirm scope, audience, claims, validation proof, and support posture.",
            "owner": "Product lead",
            "exit_criteria": f"Launch gate is `{gate}` and draft messages are approved.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "internal_enablement",
            "sequence": 2,
            "name": "Internal enablement",
            "timing": "T-5 to T-2 business days",
            "objective": "Prepare customer-facing teams to describe the launch and route feedback.",
            "owner": "Go-to-market lead",
            "exit_criteria": "Enablement note, FAQ hooks, and support snippets are published internally.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "controlled_launch",
            "sequence": 3,
            "name": "Controlled customer launch",
            "timing": "T day through T+5 business days",
            "objective": f"Invite the first cohort to try {context['primary_scope']}.",
            "owner": "Customer success lead",
            "exit_criteria": context["validation_plan"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "broad_announcement",
            "sequence": 4,
            "name": "Broad announcement",
            "timing": "After controlled-launch acceptance criteria are met",
            "objective": "Publish external messaging with validated claims and support coverage.",
            "owner": "Marketing lead",
            "exit_criteria": "No launch-blocking support, adoption, or trust issue remains unresolved.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "post_launch_followup",
            "sequence": 5,
            "name": "Post-launch follow-up",
            "timing": "T+5 to T+15 business days",
            "objective": "Close the loop with adoption evidence, objections, and next rollout decision.",
            "owner": "Product lead",
            "exit_criteria": f"{context['first_milestone']} is reviewed with evidence and next action.",
            "source_idea_ids": source_ids,
        },
    ]


def _channel_message_matrix(
    context: dict[str, Any],
    audiences: list[dict[str, Any]],
    phases: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    phase_by_id = {phase["id"]: phase["name"] for phase in phases}
    audience_by_id = {audience["id"]: audience["name"] for audience in audiences}
    specs = [
        (
            "prep",
            "internal_product_engineering",
            "launch brief",
            f"Scope the rollout around {context['primary_scope']} for {context['target_user']}.",
            "Approve scope, owners, and rollback criteria.",
        ),
        (
            "internal_enablement",
            "internal_sales_success_support",
            "enablement note",
            f"Position {context['title']} around {context['workflow_context']} and route objections to product.",
            "Review FAQ hooks and customer qualification cues.",
        ),
        (
            "controlled_launch",
            "pilot_customers",
            "email",
            context["primary_message"],
            "Join the controlled rollout and share first-use feedback.",
        ),
        (
            "controlled_launch",
            "pilot_customers",
            "in-app message",
            f"Try {context['title']} for {context['primary_scope']} when you next run {context['workflow_context']}.",
            "Start the workflow and report friction.",
        ),
        (
            "broad_announcement",
            "external_market",
            "changelog",
            f"{context['title']} is available for teams managing {context['workflow_context']}.",
            "Read the launch notes and request access.",
        ),
        (
            "post_launch_followup",
            "internal_product_engineering",
            "launch review",
            f"Review adoption, objections, and evidence from {context['first_milestone']}.",
            "Decide whether to expand, revise, or pause rollout.",
        ),
    ]
    return [
        {
            "id": f"RCM{index}",
            "phase_id": phase_id,
            "phase": phase_by_id[phase_id],
            "audience_id": audience_id,
            "audience": audience_by_id[audience_id],
            "channel": channel,
            "message": message,
            "call_to_action": cta,
            "owner": _owner_for_phase(phase_id),
            "source_idea_ids": source_ids,
            "source_fields": ["mvp_scope", "workflow_context", "merged_product_concept"],
        }
        for index, (phase_id, audience_id, channel, message, cta) in enumerate(specs, start=1)
    ]


def _internal_enablement_notes(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    risks = _string_list(design_brief.get("risks"))
    return [
        {
            "id": "IEN1",
            "topic": "Positioning",
            "owner": "Product marketing",
            "detail": context["primary_message"],
            "source_idea_ids": source_ids,
            "source_fields": ["title", "specific_user", "workflow_context", "merged_product_concept"],
        },
        {
            "id": "IEN2",
            "topic": "Qualification",
            "owner": "Customer success",
            "detail": (
                f"Prioritize {context['target_user']} teams that already run "
                f"{context['workflow_context']} and can complete {context['primary_scope']}."
            ),
            "source_idea_ids": source_ids,
            "source_fields": ["specific_user", "workflow_context", "mvp_scope"],
        },
        {
            "id": "IEN3",
            "topic": "Risk handling",
            "owner": "Support lead",
            "detail": risks[0] if risks else "Capture first-use confusion and route unresolved issues to product.",
            "source_idea_ids": source_ids,
            "source_fields": ["risks", "validation_plan"],
        },
    ]


def _customer_facing_announcements(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    title = context["title"]
    return [
        {
            "id": "CFA1",
            "name": "Pilot invitation email",
            "channel": "email",
            "audience": context["target_user"],
            "headline": f"Help shape {title} for {context['workflow_context']}",
            "body": (
                f"We are rolling out {title} to a small group first. "
                f"It is designed to help {context['target_user']} with {context['workflow_context']}: "
                f"{context['value_proposition']}"
            ),
            "call_to_action": "Reply with a workflow owner and a first-use window.",
            "source_idea_ids": source_ids,
            "source_fields": ["specific_user", "workflow_context", "merged_product_concept"],
        },
        {
            "id": "CFA2",
            "name": "Changelog announcement",
            "channel": "changelog",
            "audience": "qualified customers",
            "headline": f"{title} is entering controlled rollout",
            "body": (
                f"{title} is now available for selected teams working through "
                f"{context['workflow_context']}. The first rollout focuses on {context['primary_scope']}."
            ),
            "call_to_action": "Request access if this workflow is active for your team.",
            "source_idea_ids": source_ids,
            "source_fields": ["mvp_scope", "workflow_context", "first_milestones"],
        },
    ]


def _risk_faq_hooks(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]], source_ids: list[str]
) -> list[dict[str, Any]]:
    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )
    if not risks:
        risks = ["No explicit risk captured; confirm support and rollout assumptions before launch."]
    hooks = []
    for index, risk in enumerate(risks[:5], start=1):
        hooks.append(
            {
                "id": f"FAQ{index}",
                "question": f"How are we handling: {risk}",
                "answer_hook": "Acknowledge the risk, name the mitigation owner, and point to the validation or support path.",
                "source": "design_brief.risks" if risk in _string_list(design_brief.get("risks")) else "source_ideas.domain_risks",
                "source_idea_ids": source_ids,
            }
        )
    return hooks


def _evidence_references(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
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
    design_brief: dict[str, Any], context: dict[str, Any], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    readiness = float(design_brief.get("readiness_score") or 0.0)
    status = str(design_brief.get("design_status") or "")
    if readiness < 75:
        warnings.append(
            {
                "id": "RW1",
                "severity": "medium" if readiness >= 50 else "high",
                "warning": f"Readiness score is {readiness:.1f}/100; keep rollout controlled until validation improves.",
                "recommended_action": "Limit external announcement to pilot or selected-customer channels.",
            }
        )
    if status not in {"approved", "published"}:
        warnings.append(
            {
                "id": "RW2",
                "severity": "high",
                "warning": f"Design status is `{status or 'unknown'}`; broad communications should wait for approval.",
                "recommended_action": "Use internal alignment messaging until the design brief is approved.",
            }
        )
    for fallback in context["fallbacks_used"]:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "medium",
                "warning": f"Missing {fallback}; generated messages use explicit fallback audience context.",
                "recommended_action": f"Fill design_brief.{fallback} before broad rollout.",
            }
        )
    if not evidence:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "medium",
                "warning": "No evidence references were found for rollout claims.",
                "recommended_action": "Attach validation plan, rationale, signals, or insights before public launch.",
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


def _launch_gate(design_brief: dict[str, Any]) -> str:
    status = design_brief.get("design_status")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_launch_review"
    if status in {"approved", "published"}:
        return "approved_needs_readiness_review"
    return "needs_design_approval"


def _owner_for_phase(phase_id: str) -> str:
    return {
        "prep": "Product lead",
        "internal_enablement": "Go-to-market lead",
        "controlled_launch": "Customer success lead",
        "broad_announcement": "Marketing lead",
        "post_launch_followup": "Product lead",
    }[phase_id]


def _first_with_label(
    fallbacks: list[str], field: str, *candidates: tuple[Any, str]
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


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
