"""Generate deterministic change freeze plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import CSV_COLUMNS as CHANGE_FREEZE_PLAN_CSV_COLUMNS
from max.spec._planning_common import context, extend_section, markdown_header, render_csv, render_evidence, render_item, summary

SCHEMA_VERSION = "max-change-freeze-plan/v1"
KIND = "max.change_freeze_plan"
_SECTIONS = ("freeze_windows", "allowed_exceptions", "approval_paths", "dependency_checks", "thaw_criteria")


def generate_change_freeze_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = context(tact_spec)
    strict = ctx["strictness"] == "strict"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, freeze_mode="strict" if strict else "standard"),
        "freeze_windows": [
            _item("FW1", "pre_launch_validation", "freeze_window", "Freeze non-critical changes during release candidate validation.", "release_manager", "critical" if strict else "high", "24 hours before launch" if strict else "business day before launch", references=["execution.validation_plan"]),
            _item("FW2", "staffed_pilot", "freeze_window", f"Limit changes while {ctx['workflow_context']} is monitored for pilot users.", "launch_owner", "high", "pilot window", references=["project.workflow_context"]),
        ],
        "allowed_exceptions": [
            _item("AE1", "security_fix", "allowed_exception", "Security, privacy, or data-loss prevention changes with rollback evidence.", "security_owner", "critical", "exception only", references=["execution.risks"]),
            _item("AE2", "slo_recovery", "allowed_exception", "Operational fix required to restore SLO health or unblock validation.", "on_call_owner", "high", "exception only", references=["summary.strictness"]),
        ],
        "approval_paths": [
            _item("AP1", "release_manager_approval", "approval", "Release manager approves every freeze exception.", "release_manager", "required", "before merge", references=["freeze_windows"]),
            _item("AP2", "sponsor_approval", "approval", f"{ctx['buyer']} approves high-risk or customer-visible exceptions.", "product_owner", "required" if strict else "conditional", "before deploy", references=["project.buyer"]),
        ],
        "dependency_checks": [
            _item("DC1", "dependency_health", "dependency_check", "Confirm critical services, vendors, and CI are healthy before entering freeze.", "technical_owner", "required", "freeze start", references=["solution.suggested_stack"]),
            _item("DC2", "support_readiness", "dependency_check", "Confirm support coverage and escalation contacts are staffed.", "support_owner", "required" if strict else "recommended", "freeze start", references=["project.specific_user"]),
        ],
        "thaw_criteria": [
            _item("TC1", "validation_green", "thaw", "Validation passes and no critical risks remain unresolved.", "qa_owner", "required", "before thaw", references=["execution.validation_plan", "execution.risks"]),
            _item("TC2", "launch_review_complete", "thaw", "Release manager records evidence, approvals, and any exception outcomes.", "release_manager", "required", "before thaw", references=["approval_paths"]),
        ],
        "evidence_references": ctx["evidence_references"],
    }


def render_change_freeze_plan_markdown(plan: dict[str, Any]) -> str:
    lines = markdown_header(plan if isinstance(plan, dict) else {}, "Change Freeze Plan")
    for title, key in (("Freeze Windows", "freeze_windows"), ("Allowed Exceptions", "allowed_exceptions"), ("Approval Paths", "approval_paths"), ("Dependency Checks", "dependency_checks"), ("Thaw Criteria", "thaw_criteria"), ("Evidence References", "evidence_references")):
        extend_section(lines, title, (plan or {}).get(key) or [], render_evidence if key == "evidence_references" else render_item)
    return "\n".join(lines).rstrip() + "\n"


def render_change_freeze_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan if isinstance(plan, dict) else {}, _SECTIONS)


def _item(item_id: str, name: str, item_type: str, description: str, owner: str, severity: str, timing: str, *, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "type": item_type, "description": description, "owner": owner, "severity": severity, "timing": timing, "references": references}
