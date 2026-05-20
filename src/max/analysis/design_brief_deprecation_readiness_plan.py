"""Deterministic deprecation readiness plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import (
    brief_context,
    design_brief_block,
    join_text,
    list_values,
    source_block,
    text,
)

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.deprecation_readiness_plan"
SCHEMA_VERSION = "max.design_brief.deprecation_readiness_plan.v1"


def build_design_brief_deprecation_readiness_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    evidence_references = _evidence_references(brief, context)
    compatibility_risks = _compatibility_risks(brief, context)
    evidence_gaps = _evidence_gaps(context, brief)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "buyer": context["buyer"],
            "specific_user": context["target_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "readiness_posture": "deprecation_discovery_required" if evidence_gaps else "ready_for_deprecation_review",
            "compatibility_risk_count": len(compatibility_risks),
            "evidence_gap_count": len(evidence_gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "replacement_path": _replacement_path(context),
        "impacted_users": _impacted_users(context),
        "compatibility_risks": compatibility_risks,
        "migration_steps": _migration_steps(context),
        "communication_checkpoints": _communication_checkpoints(context),
        "rollback_criteria": _rollback_criteria(context, compatibility_risks),
        "acceptance_checks": _acceptance_checks(context),
        "evidence_references": evidence_references,
        "evidence_gaps": evidence_gaps,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_deprecation_readiness_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported deprecation readiness plan format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# Deprecation Readiness Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
    ]
    for key, title in (
        ("replacement_path", "Replacement Path"),
        ("impacted_users", "Impacted Users"),
        ("compatibility_risks", "Compatibility Risks"),
        ("migration_steps", "Migration Steps"),
        ("communication_checkpoints", "Communication Checkpoints"),
        ("rollback_criteria", "Rollback Criteria"),
        ("acceptance_checks", "Acceptance Checks"),
        ("evidence_gaps", "Evidence Gaps"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
        for row in rows:
            label = row.get("name") or row.get("description") or row.get("id")
            detail = row.get("description") or row.get("action") or row.get("criteria") or row.get("check")
            lines.append(f"- **{row['id']} {label}**: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def deprecation_readiness_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'Deprecation Readiness Plan'))}-"
        f"deprecation-readiness-plan.{extension}"
    )


def _replacement_path(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "R1",
            "name": "Target replacement workflow",
            "description": f"Move {context['target_user']} from deprecated behavior to {context['product_concept']}.",
            "owner": context["buyer"],
            "evidence": context["primary_source_idea_id"],
        }
    ]


def _impacted_users(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "U1", "name": context["target_user"], "description": f"Users operating in {context['workflow_context']}.", "owner": context["buyer"]}
    ]


def _compatibility_risks(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    blob = _blob(brief, context)
    risk_specs = [
        ("legacy", "Legacy behavior dependency", "Existing legacy workflows may not map cleanly to the replacement path."),
        ("migration", "Migration completeness", "Migration records may be incomplete or hard to reconcile."),
        ("api", "API contract break", "API consumers may depend on deprecated fields, responses, or timing."),
        ("integration", "Integration dependency break", "External integrations may require versioning or partner coordination."),
        ("customer", "Customer adoption risk", "Customer teams may need explicit notice, enablement, and opt-out handling."),
        ("rollback", "Rollback ambiguity", "Rollback ownership and criteria may be unclear during cutover."),
    ]
    risks = [
        {
            "id": f"K{idx}",
            "name": name,
            "description": description,
            "severity": "high" if keyword in {"api", "integration", "rollback"} else "medium",
            "keyword": keyword,
            "source_idea_id": context["primary_source_idea_id"],
        }
        for idx, (keyword, name, description) in enumerate(risk_specs, start=1)
        if keyword in blob
    ]
    if not risks:
        risks.append({"id": "K1", "name": "Unknown compatibility surface", "description": "No explicit deprecation keywords were found; compatibility discovery is required.", "severity": "medium", "keyword": "unknown", "source_idea_id": context["primary_source_idea_id"]})
    return risks


def _migration_steps(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "M1", "name": "Inventory usage", "action": f"Identify active {context['workflow_context']} usage and owners.", "owner": "Product owner"},
        {"id": "M2", "name": "Map replacement", "action": f"Map each impacted workflow to {join_text(context['mvp_scope'], 'the replacement MVP scope')}.", "owner": "Engineering owner"},
        {"id": "M3", "name": "Cutover validation", "action": "Verify migrated records, integrations, and customer acceptance before disabling the old path.", "owner": context["buyer"]},
    ]


def _communication_checkpoints(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "C1", "name": "Internal readiness", "action": "Support, sales, and success teams can explain the replacement path.", "owner": context["buyer"]},
        {"id": "C2", "name": "Customer notice", "action": f"Notify impacted {context['target_user']} cohorts with dates, migration actions, and support path.", "owner": "Customer success owner"},
    ]


def _rollback_criteria(context: dict[str, Any], risks: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"id": "B1", "name": "Customer-blocking failure", "criteria": "Rollback if migrated users cannot complete the critical workflow.", "owner": context["buyer"]},
        {"id": "B2", "name": "Compatibility threshold", "criteria": f"Rollback or pause if any high severity compatibility risk remains unresolved across {len(risks)} tracked risk(s).", "owner": "Engineering owner"},
    ]


def _acceptance_checks(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "A1", "name": "Usage inventory complete", "check": "Active users, accounts, APIs, and integrations are mapped before deprecation."},
        {"id": "A2", "name": "Replacement validated", "check": f"{context['target_user']} can complete the replacement workflow without legacy access."},
        {"id": "A3", "name": "Rollback tested", "check": "Rollback owner, trigger, and communications are rehearsed before cutover."},
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
        for field in ("problem", "solution", "domain_risks", "workflow_context"):
            values = list_values(idea.get(field))
            if values:
                refs.append({"id": f"{idea['id']}.{field}", "type": field, "description": join_text(values, "")})
    return refs


def _evidence_gaps(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if "specific_user" in context["fallbacks_used"]:
        gaps.append({"id": "missing_impacted_users", "description": "Impacted user cohort is missing."})
    if "mvp_scope" in context["fallbacks_used"]:
        gaps.append({"id": "missing_replacement_scope", "description": "Replacement scope is missing."})
    if not text(brief.get("validation_plan")):
        gaps.append({"id": "missing_migration_validation", "description": "Migration validation plan is missing."})
    return gaps


def _blob(brief: dict[str, Any], context: dict[str, Any]) -> str:
    return " ".join([text(brief), text(context["source_ideas"]), *context["risks"], *context["evidence"]]).lower()


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
