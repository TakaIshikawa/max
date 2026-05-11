"""Generate deterministic feature flag rollout plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

FEATURE_FLAG_ROLLOUT_PLAN_SCHEMA_VERSION = "max-feature-flag-rollout-plan/v1"
KIND = "max.feature_flag_rollout_plan"
FEATURE_FLAG_ROLLOUT_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("flags", "rollout_stages", "guardrail_metrics", "rollback_triggers", "owner_handoffs")


def generate_feature_flag_rollout_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    strict = context["strictness"] == "strict"
    flags = [
        item("FF1", "primary_workflow_enabled", f"Controls exposure for {context['workflow']}.", "release_owner", evidence=["project.workflow_context"]),
        item("FF2", "integration_writes_enabled", f"Controls customer-visible writes from {context['technical_approach']}.", "engineering_owner", evidence=["solution.technical_approach"]),
    ]
    rollout_stages = [
        item("RS1", "internal_validation", f"Enable for internal testers and support owners validating {context['workflow']}.", "qa_owner", timing="0% customers", action="Exit only after smoke checks pass.", evidence=["execution.validation_plan"]),
        item("RS2", "pilot_cohort", f"Enable for selected {context['target_user']} pilot cohort.", "customer_success_owner", timing="5% cohort" if strict else "10% cohort", action="Monitor guardrails for one staffed window.", evidence=["project.target_users"]),
        item("RS3", "broad_rollout", "Expand after guardrails stay within threshold and no rollback trigger is open.", "release_owner", timing="25%, 50%, 100%" if strict else "50%, 100%", action="Pause between stages for review.", evidence=["evaluation.overall_score"]),
    ]
    guardrail_metrics = [
        item("GM1", "workflow_success_rate", f"{context['workflow']} completes successfully for enabled users.", "on_call_owner", action="Keep >= 99% during rollout." if strict else "Keep >= 97% during rollout.", evidence=["project.workflow_context"]),
        item("GM2", "support_contact_rate", f"Support contacts from {context['target_user']} stay within expected launch volume.", "support_owner", action="Review after each stage.", evidence=["support_context"]),
    ]
    rollback_triggers = [
        item("RT1", "critical_failure", "Any sev1 incident, data-loss signal, or security exposure tied to enabled traffic.", "incident_commander", severity="critical", action="Disable flags and notify stakeholders.", evidence=["execution.risks"]),
        item("RT2", "guardrail_breach", "Guardrail metric misses threshold for two consecutive checks.", "release_owner", severity="high", action="Return to previous stable cohort.", evidence=["guardrail_metrics"]),
    ]
    owner_handoffs = [
        item("OH1", "release_to_support", "Support receives flag state, cohort list, and user-facing workaround.", "release_owner", stakeholder="support team", evidence=["stakeholder_channels"]),
        item("OH2", "engineering_to_on_call", "Engineering hands dashboard links, known risks, and rollback steps to on-call.", "engineering_owner", stakeholder="on-call", evidence=["solution.technical_approach"]),
    ]
    return {"schema_version": FEATURE_FLAG_ROLLOUT_PLAN_SCHEMA_VERSION, "kind": KIND, "source": context["source"], "summary": summary(context, evaluation_score=context["evaluation_score"]), "flags": flags, "rollout_stages": rollout_stages, "guardrail_metrics": guardrail_metrics, "rollback_triggers": rollback_triggers, "owner_handoffs": owner_handoffs, "evidence_references": context["evidence_references"]}


def render_feature_flag_rollout_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Feature Flag Rollout Plan", SECTIONS)


def render_feature_flag_rollout_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)
