"""Deterministic support escalation plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import brief_context, design_brief_block, join_text, list_values, source_block, text

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.support_escalation_plan"
SCHEMA_VERSION = "max.design_brief.support_escalation_plan.v1"


def build_design_brief_support_escalation_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    evidence_gaps = _evidence_gaps(context, brief)
    escalation_triggers = _escalation_triggers(brief, context)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {**design_brief_block(brief, context), "buyer": context["buyer"], "specific_user": context["target_user"], "workflow_context": context["workflow_context"]},
        "summary": {"support_posture": "support_discovery_required" if evidence_gaps else "ready_for_support_escalation_review", "high_severity_count": sum(1 for item in escalation_triggers if item["severity"] == "high"), "evidence_gap_count": len(evidence_gaps), "fallbacks_used": context["fallbacks_used"]},
        "escalation_triggers": escalation_triggers,
        "severity_levels": _severity_levels(),
        "owner_handoffs": _owner_handoffs(context),
        "runbook_requirements": _runbook_requirements(context, escalation_triggers),
        "customer_messaging": _customer_messaging(context),
        "evidence_references": _evidence_references(brief, context),
        "evidence_gaps": evidence_gaps,
        "open_questions": _open_questions(context, evidence_gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_support_escalation_plan(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported support escalation plan format: {fmt}")
    brief = report["design_brief"]
    lines = [f"# Support Escalation Plan: {brief['title']}", "", f"Schema: `{report['schema_version']}`", f"Design brief: `{brief['id']}`"]
    for key, title in (
        ("escalation_triggers", "Escalation Triggers"),
        ("severity_levels", "Severity Levels"),
        ("owner_handoffs", "Owner Handoffs"),
        ("runbook_requirements", "Runbook Requirements"),
        ("customer_messaging", "Customer Messaging"),
        ("evidence_gaps", "Evidence Gaps"),
        ("open_questions", "Open Questions"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
        for row in rows:
            label = row.get("name") or row.get("question") or row.get("id")
            detail = row.get("description") or row.get("criteria") or row.get("question") or row.get("message")
            severity = f" (`{row['severity']}`)" if row.get("severity") else ""
            lines.append(f"- **{row['id']} {label}**{severity}: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def support_escalation_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-{_filename_part(str(design_brief.get('title') or 'Support Escalation Plan'))}-support-escalation-plan.{extension}"


def _escalation_triggers(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    risks = context["risks"] or ["Unknown failure modes need support escalation discovery."]
    triggers = [
        {
            "id": f"T{idx}",
            "name": "Risk-based escalation",
            "description": risk,
            "severity": _severity(risk),
            "owner": "Support owner",
            "source_idea_id": context["primary_source_idea_id"],
        }
        for idx, risk in enumerate(risks[:5], start=1)
    ]
    blob = (text(brief) + " " + text(context["source_ideas"])).lower()
    if any(term in blob for term in ("incident", "outage", "customer impact", "high risk", "sev1", "sev 1")) and not any(item["severity"] == "high" for item in triggers):
        triggers.append({"id": f"T{len(triggers) + 1}", "name": "High-risk customer incident", "description": "High-risk support, customer, or incident text requires severe escalation handling.", "severity": "high", "owner": "Support owner", "source_idea_id": context["primary_source_idea_id"]})
    return triggers


def _severity(value: str) -> str:
    lowered = value.lower()
    if any(term in lowered for term in ("incident", "outage", "customer impact", "security", "data loss", "blocked", "high risk", "sev1", "sev 1")):
        return "high"
    if any(term in lowered for term in ("delay", "failure", "support", "customer")):
        return "medium"
    return "low"


def _severity_levels() -> list[dict[str, str]]:
    return [
        {"id": "S1", "name": "High", "description": "Customer-impacting incident, blocked workflow, security concern, or data loss risk.", "criteria": "Immediate owner handoff and customer messaging required.", "severity": "high"},
        {"id": "S2", "name": "Medium", "description": "Workflow degradation, repeat support issue, or unclear owner handoff.", "criteria": "Same-day triage and workaround required.", "severity": "medium"},
        {"id": "S3", "name": "Low", "description": "Question, documentation issue, or non-blocking defect.", "criteria": "Track through normal support queue.", "severity": "low"},
    ]


def _owner_handoffs(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "H1", "name": "Support to product", "description": f"Support escalates recurring {context['workflow_context']} issues with reproduction and customer impact.", "owner": "Product owner"},
        {"id": "H2", "name": "Support to engineering", "description": "Engineering receives high-severity incidents with logs, severity, and rollback context.", "owner": "Engineering owner"},
        {"id": "H3", "name": "Support to customer owner", "description": f"{context['buyer']} receives customer-facing status and decision requests.", "owner": context["buyer"]},
    ]


def _runbook_requirements(context: dict[str, Any], triggers: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"id": "R1", "name": "Triage checklist", "description": f"Identify account, user, workflow step, trigger, severity, and owner for {len(triggers)} trigger(s)."},
        {"id": "R2", "name": "Reproduction and logs", "description": "Capture reproduction steps, event IDs, timestamps, and error state before handoff."},
        {"id": "R3", "name": "Workaround and rollback", "description": f"Document workaround or rollback path for {join_text(context['mvp_scope'], 'the MVP workflow')}."},
    ]


def _customer_messaging(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "M1", "name": "Initial acknowledgement", "message": "Confirm receipt, severity, affected workflow, and next update time."},
        {"id": "M2", "name": "Status update", "message": f"Explain impact to {context['target_user']}, workaround, owner, and expected resolution."},
        {"id": "M3", "name": "Resolution closeout", "message": "Summarize root cause, customer action required, and follow-up prevention work."},
    ]


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for field in ("validation_plan", "risks", "synthesis_rationale"):
        values = list_values(brief.get(field))
        if values:
            refs.append({"id": f"design_brief.{field}", "type": field, "description": join_text(values, "")})
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        for field in ("domain_risks", "workflow_context", "evidence_signals", "problem"):
            values = list_values(idea.get(field))
            if values:
                refs.append({"id": f"{idea['id']}.{field}", "type": field, "description": join_text(values, "")})
    return refs


def _evidence_gaps(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if "buyer" in context["fallbacks_used"]:
        gaps.append({"id": "missing_support_owner", "description": "Support owner or accountable buyer is missing."})
    if not context["risks"]:
        gaps.append({"id": "missing_failure_modes", "description": "Failure modes and escalation triggers are missing."})
    blob = (text(brief) + " " + text(context["source_ideas"])).lower()
    if not context["risks"] or not any(term in blob for term in ("customer", "message", "communication", "notice", "status")):
        gaps.append({"id": "missing_customer_communication", "description": "Customer communication criteria are missing."})
    return gaps


def _open_questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    questions = [{"id": "Q1", "question": f"Who is the named support owner for {context['workflow_context']}?"}, {"id": "Q2", "question": "What update cadence applies to high-severity customer incidents?"}]
    questions.extend({"id": f"Q{idx + 2}", "question": gap["description"]} for idx, gap in enumerate(gaps))
    return questions


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
