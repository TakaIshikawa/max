"""Generate deterministic SLO exception review reports for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

SLO_EXCEPTION_REVIEW_SCHEMA_VERSION = "max-slo-exception-review/v1"
KIND = "max.slo_exception_review"
SLO_EXCEPTION_REVIEW_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("exception_classes", "request_evidence", "approval_criteria", "temporary_mitigations", "expiry_checks", "follow_up_actions")


def generate_slo_exception_review(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    strict = context["strictness"] == "strict"
    exception_classes = [
        item("EC1", "launch_learning_exception", f"Temporary SLO deviation while validating {context['workflow']}.", "launch_owner", timing="7 days" if strict else "14 days", evidence=["project.workflow_context"]),
        item("EC2", "dependency_exception", f"Temporary deviation caused by dependency behavior in {context['stack']}.", "engineering_owner", timing="3 days" if strict else "7 days", evidence=["solution.suggested_stack"]),
    ]
    request_evidence = [
        item("RE1", "impact_statement", f"Describe affected {context['target_user']}, customer impact, and workaround.", "requester", evidence=["project.target_users"]),
        item("RE2", "telemetry_snapshot", "Attach current SLO measurement, error budget impact, and mitigation owner.", "on_call_owner", evidence=["execution.validation_plan"]),
    ]
    approval_criteria = [
        item("AC1", "bounded_duration", "Exception has explicit expiry, owner, and rollback condition.", "release_manager", action="Required" if strict else "Required for customer-visible SLOs.", evidence=["summary.strictness"]),
        item("AC2", "sponsor_awareness", f"{context['buyer']} is aware of customer-visible promise changes.", "product_owner", stakeholder=context["buyer"], action="Required" if strict else "Recommended", evidence=["project.buyer"]),
    ]
    temporary_mitigations = [
        item("TM1", "manual_watch", "Assign staffed monitoring while the exception is active.", "on_call_owner", timing="active exception window", evidence=["request_evidence"]),
        item("TM2", "customer_workaround", f"Publish workaround through {context['support_context']}.", "support_owner", timing="before approval", evidence=["support_context"]),
    ]
    expiry_checks = [
        item("EX1", "daily_expiry_review" if strict else "scheduled_expiry_review", "Review exception status before expiry and close, renew, or escalate.", "release_manager", timing="daily" if strict else "twice weekly", evidence=["exception_classes"]),
        item("EX2", "budget_recovery_check", "Confirm SLO and error budget have recovered before normal release flow resumes.", "on_call_owner", timing="at closure", evidence=["telemetry_snapshot"]),
    ]
    follow_up_actions = [
        item("FA1", "root_cause_followup", "Capture cause, prevention action, and owner after the exception closes.", "engineering_owner", evidence=["expiry_checks"]),
        item("FA2", "promise_update", "Update launch promises or support docs if the exception changes expected service behavior.", "product_owner", evidence=["support_context"]),
    ]
    return {"schema_version": SLO_EXCEPTION_REVIEW_SCHEMA_VERSION, "kind": KIND, "source": context["source"], "summary": summary(context, exception_expiry="3 days" if strict else "7-14 days"), "exception_classes": exception_classes, "request_evidence": request_evidence, "approval_criteria": approval_criteria, "temporary_mitigations": temporary_mitigations, "expiry_checks": expiry_checks, "follow_up_actions": follow_up_actions, "evidence_references": context["evidence_references"]}


def render_slo_exception_review_markdown(review: dict[str, Any]) -> str:
    return render_markdown(review, "SLO Exception Review", SECTIONS)


def render_slo_exception_review_csv(review: dict[str, Any]) -> str:
    return render_csv(review, SECTIONS)
