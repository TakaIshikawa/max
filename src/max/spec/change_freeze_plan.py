"""Generate deterministic change freeze plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

CHANGE_FREEZE_PLAN_SCHEMA_VERSION = "max-change-freeze-plan/v1"
KIND = "max.change_freeze_plan"
CHANGE_FREEZE_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("freeze_windows", "allowed_exceptions", "approval_paths", "dependency_checks", "thaw_criteria")


def generate_change_freeze_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    strict = context["strictness"] == "strict"
    freeze_windows = [
        item("FW1", "pre_launch_freeze", f"Freeze non-critical changes to {context['workflow']} before launch validation.", "release_manager", timing="48 hours before launch" if strict else "24 hours before launch", evidence=["execution.validation_plan"]),
        item("FW2", "launch_observation_freeze", "Hold discretionary changes while support and telemetry confirm stable adoption.", "launch_owner", timing="first 24 hours after launch" if strict else "first staffed launch window", evidence=["project.workflow_context"]),
    ]
    allowed_exceptions = [
        item("AE1", "sev1_mitigation", "Emergency fix for active customer impact, data risk, or security exposure.", "incident_commander", severity="critical", action="Require rollback note and post-change validation.", evidence=["execution.risks"]),
        item("AE2", "launch_blocker", "Small change required to pass launch-critical validation.", "release_manager", severity="high", action="Attach failed check, reviewer, and rollback plan.", evidence=["execution.validation_plan"]),
    ]
    approval_paths = [
        item("AP1", "standard_exception", "Release manager and engineering owner approve freeze exceptions.", "release_manager", action="Record decision before merge or deploy.", evidence=["freeze_windows"]),
        item("AP2", "business_exception", f"{context['buyer']} approves customer-visible promise or timing changes.", "product_owner", stakeholder=context["buyer"], action="Capture sponsor approval and customer message owner.", evidence=["project.buyer"]),
    ]
    dependency_checks = [
        item("DC1", "stack_dependency_health", f"Confirm readiness of {context['stack']} for frozen launch scope.", "engineering_owner", evidence=["solution.suggested_stack"]),
        item("DC2", "support_readiness", f"Confirm {context['support_context']} is staffed for exception intake.", "support_owner", evidence=["execution.support_context"]),
    ]
    thaw_criteria = [
        item("TC1", "validation_clean", f"{context['validation_plan']} passes with no critical regression.", "qa_owner", evidence=["execution.validation_plan"]),
        item("TC2", "stakeholder_signoff", f"{context['buyer']} and {context['target_user']} have no open launch-blocking communications.", "launch_owner", evidence=["project.buyer", "project.target_users"]),
    ]
    return {"schema_version": CHANGE_FREEZE_PLAN_SCHEMA_VERSION, "kind": KIND, "source": context["source"], "summary": summary(context), "freeze_windows": freeze_windows, "allowed_exceptions": allowed_exceptions, "approval_paths": approval_paths, "dependency_checks": dependency_checks, "thaw_criteria": thaw_criteria, "evidence_references": context["evidence_references"]}


def render_change_freeze_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Change Freeze Plan", SECTIONS)


def render_change_freeze_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)
