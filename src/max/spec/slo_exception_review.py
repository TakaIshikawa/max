"""Generate deterministic SLO exception reviews for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import (
    CSV_COLUMNS as SLO_EXCEPTION_REVIEW_CSV_COLUMNS,
    context,
    extend_section,
    markdown_header,
    render_csv,
    render_evidence,
    render_item,
    summary,
)


SLO_EXCEPTION_REVIEW_SCHEMA_VERSION = "max-slo-exception-review/v1"
KIND = "max.slo_exception_review"
_SECTIONS = (
    "exception_classes",
    "request_evidence",
    "approval_criteria",
    "temporary_mitigations",
    "expiry_checks",
    "follow_up_actions",
)


def generate_slo_exception_review(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into controlled SLO exception governance."""
    ctx = context(tact_spec)
    strict = ctx["strictness"] == "strict"
    expiry = "24 hours" if strict else "7 days"
    return {
        "schema_version": SLO_EXCEPTION_REVIEW_SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, expiry_window=expiry),
        "exception_classes": [
            _item("EXC1", "pilot_learning", "exception", "Temporary SLO relaxation for staffed pilot learning only.", "launch_owner", "medium", references=["project.workflow_context"]),
            _item("EXC2", "dependency_constraint", "exception", f"Deviation caused by a constrained dependency in {ctx['technical_approach']}.", "technical_owner", "high" if strict else "medium", references=["solution.technical_approach", "execution.risks"]),
            _item("EXC3", "acceptance_tradeoff", "exception", "Documented acceptance of a non-critical SLO miss with user-visible mitigation.", "product_owner", "critical" if strict else "high", references=["acceptance_criteria"]),
        ],
        "request_evidence": [
            _item("EVD1", "impact_statement", "evidence", f"Describe affected {ctx['target_user']} workflow and expected duration.", "requester", "required", references=["project.specific_user", "project.workflow_context"]),
            _item("EVD2", "metric_snapshot", "evidence", "Attach current SLO, error budget, support, and validation evidence.", "technical_owner", "required", references=["execution.validation_plan"]),
            _item("EVD3", "risk_disposition", "evidence", "List mitigated, accepted, and unresolved risks before approval.", "launch_owner", "required" if strict else "recommended", references=["execution.risks"]),
        ],
        "approval_criteria": [
            _item("APR1", "owner_approval", "approval", "Technical owner and launch owner approve the exception request.", "launch_owner", "required", references=["request_evidence"]),
            _item("APR2", "sponsor_approval", "approval", f"{ctx['buyer']} approves customer-visible or recurring exceptions.", "product_owner", "required" if strict else "conditional", references=["project.buyer"]),
            _item("APR3", "no_critical_escape", "approval", "No critical unresolved user impact, privacy issue, or data loss risk remains open.", "on_call_owner", "required" if strict else "recommended", references=["execution.risks"]),
        ],
        "temporary_mitigations": [
            _item("MIT1", "staffed_monitoring", "mitigation", "Staff the exception window with alert routing and support intake review.", "on_call_owner", "high", references=["summary.strictness"]),
            _item("MIT2", "rollout_cap", "mitigation", "Cap exposure until the exception expires or normal SLO policy is restored.", "launch_owner", "critical" if strict else "high", references=["project.workflow_context"]),
            _item("MIT3", "user_fallback", "mitigation", "Provide fallback guidance for impacted users during the exception.", "support_owner", "high", references=["project.specific_user"]),
        ],
        "expiry_checks": [
            _item("EXP1", "exception_expiry", "expiry", f"Exception expires after {expiry} unless re-approved with fresh evidence.", "launch_owner", "critical" if strict else "high", expiry=expiry, references=["approval_criteria"]),
            _item("EXP2", "budget_review", "expiry", "Review burn rate and open incidents before any extension.", "on_call_owner", "required", expiry=expiry, references=["temporary_mitigations"]),
        ],
        "follow_up_actions": [
            _item("FUA1", "restore_policy", "follow_up", "Restore normal SLO thresholds and remove temporary rollout caps.", "technical_owner", "required", references=["expiry_checks"]),
            _item("FUA2", "post_exception_review", "follow_up", "Record outcome, customer impact, and permanent remediation owner.", "launch_owner", "required", references=["request_evidence", "temporary_mitigations"]),
        ],
        "evidence_references": ctx["evidence_references"],
    }


def render_slo_exception_review_markdown(review: dict[str, Any]) -> str:
    lines = markdown_header(review if isinstance(review, dict) else {}, "SLO Exception Review")
    for title, key in (
        ("Exception Classes", "exception_classes"),
        ("Request Evidence", "request_evidence"),
        ("Approval Criteria", "approval_criteria"),
        ("Temporary Mitigations", "temporary_mitigations"),
        ("Expiry Checks", "expiry_checks"),
        ("Follow-up Actions", "follow_up_actions"),
        ("Evidence References", "evidence_references"),
    ):
        extend_section(lines, title, (review or {}).get(key) or [], render_evidence if key == "evidence_references" else render_item)
    return "\n".join(lines).rstrip() + "\n"


def render_slo_exception_review_csv(review: dict[str, Any]) -> str:
    return render_csv(review if isinstance(review, dict) else {}, _SECTIONS)


def _item(
    item_id: str,
    name: str,
    item_type: str,
    description: str,
    owner: str,
    severity: str,
    *,
    expiry: str | None = None,
    references: list[str] | None = None,
) -> dict[str, Any]:
    item = {"id": item_id, "name": name, "type": item_type, "description": description, "owner": owner, "severity": severity, "references": references or []}
    if expiry:
        item["expiry"] = expiry
    return item
