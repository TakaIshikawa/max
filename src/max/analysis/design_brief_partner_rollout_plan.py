"""Deterministic partner rollout plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import brief_context, design_brief_block, join_text, list_values, source_block, text

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.partner_rollout_plan"
SCHEMA_VERSION = "max.design_brief.partner_rollout_plan.v1"


def build_design_brief_partner_rollout_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    evidence_gaps = _evidence_gaps(context, brief)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {**design_brief_block(brief, context), "buyer": context["buyer"], "specific_user": context["target_user"], "workflow_context": context["workflow_context"]},
        "summary": {"rollout_posture": "partner_discovery_required" if evidence_gaps else "ready_for_partner_rollout", "fallbacks_used": context["fallbacks_used"], "evidence_gap_count": len(evidence_gaps)},
        "partner_segments": _partner_segments(brief, context),
        "enablement_assets": _enablement_assets(context),
        "integration_dependencies": _integration_dependencies(brief, context),
        "launch_gates": _launch_gates(context),
        "support_handoffs": _support_handoffs(context),
        "evidence_references": _evidence_references(brief, context),
        "evidence_gaps": evidence_gaps,
        "open_questions": _open_questions(context, evidence_gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_partner_rollout_plan(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported partner rollout plan format: {fmt}")
    brief = report["design_brief"]
    lines = [f"# Partner Rollout Plan: {brief['title']}", "", f"Schema: `{report['schema_version']}`", f"Design brief: `{brief['id']}`"]
    for key, title in (
        ("partner_segments", "Partner Scope"),
        ("launch_gates", "Rollout Gates"),
        ("integration_dependencies", "Dependencies"),
        ("support_handoffs", "Support Handoffs"),
        ("enablement_assets", "Enablement Assets"),
        ("evidence_gaps", "Evidence Gaps"),
        ("open_questions", "Open Questions"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
        for row in rows:
            label = row.get("name") or row.get("question") or row.get("id")
            detail = row.get("description") or row.get("criteria") or row.get("question") or row.get("action")
            lines.append(f"- **{row['id']} {label}**: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def partner_rollout_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-{_filename_part(str(design_brief.get('title') or 'Partner Rollout Plan'))}-partner-rollout-plan.{extension}"


def _partner_segments(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    blob = (text(brief) + " " + text(context["source_ideas"])).lower()
    segments = [{"id": "P1", "name": context["buyer"], "description": f"Sponsors rollout for {context['target_user']} partners in {context['workflow_context']}."}]
    if "agency" in blob:
        segments.append({"id": "P2", "name": "Agency partners", "description": "Agencies that configure or operate the workflow for customers."})
    if "reseller" in blob or "channel" in blob:
        segments.append({"id": "P3", "name": "Channel partners", "description": "Resellers or channel teams responsible for customer enablement."})
    if "integration" in blob or "api" in blob:
        segments.append({"id": "P4", "name": "Integration partners", "description": "Technical partners that connect APIs, webhooks, or shared data flows."})
    return segments


def _enablement_assets(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "E1", "name": "Partner one-pager", "description": f"Explain {context['product_concept']} and partner value.", "owner": "Partner owner"},
        {"id": "E2", "name": "Implementation guide", "description": f"Document setup for {join_text(context['mvp_scope'], 'the MVP scope')}.", "owner": "Solutions owner"},
        {"id": "E3", "name": "FAQ and objection handling", "description": "Prepare answers for rollout scope, support, and customer impact.", "owner": context["buyer"]},
    ]


def _integration_dependencies(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    deps = [{"id": "D1", "name": "Partner access path", "description": f"Partners can access {context['workflow_context']} with approved permissions."}]
    blob = (text(brief) + " " + text(context["source_ideas"])).lower()
    if "api" in blob or "integration" in blob or "webhook" in blob:
        deps.append({"id": "D2", "name": "API or integration readiness", "description": "API credentials, sandbox, webhook handling, and error states are ready for partner testing."})
    return deps


def _launch_gates(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "G1", "name": "Pilot partner selected", "criteria": f"At least one partner matches {context['buyer']} and can test the workflow."},
        {"id": "G2", "name": "Enablement approved", "criteria": "Partner-facing guide, FAQ, and support path are reviewed."},
        {"id": "G3", "name": "Evidence reviewed", "criteria": join_text(context["evidence"], "Partner validation evidence is still pending.")},
    ]


def _support_handoffs(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "H1", "name": "Partner success handoff", "description": "Partner owner receives onboarding status, open issues, and launch gate results."},
        {"id": "H2", "name": "Support escalation handoff", "description": f"Support team owns partner issues that block {context['target_user']} workflows."},
    ]


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for field in ("validation_plan", "why_this_now", "synthesis_rationale"):
        value = text(brief.get(field))
        if value:
            refs.append({"id": f"design_brief.{field}", "type": field, "description": value})
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        for field in ("buyer", "workflow_context", "evidence_signals", "domain_risks"):
            values = list_values(idea.get(field))
            if values:
                refs.append({"id": f"{idea['id']}.{field}", "type": field, "description": join_text(values, "")})
    return refs


def _evidence_gaps(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if "buyer" in context["fallbacks_used"]:
        gaps.append({"id": "missing_partner_owner", "description": "Partner owner or buyer is missing."})
    if "workflow_context" in context["fallbacks_used"]:
        gaps.append({"id": "missing_partner_workflow", "description": "Partner workflow context is missing."})
    if not text(brief.get("validation_plan")):
        gaps.append({"id": "missing_partner_validation", "description": "Partner rollout validation plan is missing."})
    return gaps


def _open_questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    questions = [{"id": "Q1", "question": f"Which partner cohort should {context['buyer']} launch first?"}, {"id": "Q2", "question": "What partner support SLA applies during rollout?"}]
    questions.extend({"id": f"Q{idx + 2}", "question": gap["description"]} for idx, gap in enumerate(gaps))
    return questions


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
