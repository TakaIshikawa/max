"""Generate deterministic data processing agreement review plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_processing_agreement_review_plan.v1"
DATA_PROCESSING_AGREEMENT_REVIEW_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.data_processing_agreement_review_plan"


def generate_data_processing_agreement_review_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic DPA review planning data."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _dpa_hints(spec)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    strictness = "strict" if hints["regulated"] or hints["sensitive_data"] or hints["external_processors"] else ctx["strictness"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            review_strictness=strictness,
            processor_count=len(hints["vendors"]),
            regulated_regions=hints["regions"],
            data_categories=hints["data_categories"],
        ),
        "review_scope": _review_scope(ctx, hints, strictness, evidence_ids),
        "processor_inventory": _processor_inventory(hints, strictness, evidence_ids),
        "clause_checks": _clause_checks(hints, strictness, evidence_ids),
        "transfer_assessment": _transfer_assessment(hints, strictness, evidence_ids),
        "approval_path": _approval_path(ctx, hints, strictness, evidence_ids),
        "remediation_items": _remediation_items(hints, strictness, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _dpa_hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    dpa = metadata.get("dpa") if isinstance(metadata.get("dpa"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}

    vendors = _ordered(
        string_list(dpa.get("vendors"))
        + string_list(metadata.get("vendors"))
        + string_list(dpa.get("processors"))
        + string_list(metadata.get("processors"))
    ) or ["primary processor under review"]
    regions = _ordered(
        string_list(dpa.get("regions"))
        + string_list(dpa.get("regulatory_regions"))
        + string_list(metadata.get("regulatory_regions"))
        + string_list(metadata.get("regions"))
    ) or ["unconfirmed processing region"]
    explicit_data_categories = _ordered(
        string_list(dpa.get("data_categories"))
        + string_list(metadata.get("data_categories"))
        + string_list(project.get("data_categories"))
    )
    data_categories = explicit_data_categories or ["customer data"]
    users = _ordered(string_list(project.get("target_users")) + string_list(project.get("specific_user"))) or ["primary user"]
    text = " ".join(
        vendors
        + regions
        + explicit_data_categories
        + users
        + string_list(execution.get("risks"))
        + [
            compact(dpa.get("risk")),
            compact(dpa.get("transfer_mechanism")),
            compact(project.get("workflow_context")),
            compact(project.get("summary")),
        ]
    ).lower()
    regulated = any(term in text for term in ("gdpr", "ccpa", "cpra", "hipaa", "dpa", "scc", "subprocessor", "regulated"))
    sensitive_data = any(term in text for term in ("personal", "pii", "payment", "health", "credential", "biometric"))
    external_processors = bool(string_list(metadata.get("vendors")) or string_list(dpa.get("vendors")) or string_list(dpa.get("processors")))

    return {
        "vendors": vendors,
        "regions": regions,
        "data_categories": data_categories,
        "target_users": users,
        "regulated": regulated or regions != ["unconfirmed processing region"],
        "sensitive_data": sensitive_data,
        "external_processors": external_processors,
        "transfer_mechanism": compact(dpa.get("transfer_mechanism")) or ("standard contractual clauses" if regulated else "contractual processing terms"),
        "review_deadline": compact(dpa.get("review_deadline")) or ("before launch or vendor onboarding"),
    }


def _review_scope(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": "RS1",
        "name": "DPA launch and onboarding review",
        "owner": "legal_owner",
        "strictness": strictness,
        "deadline": hints["review_deadline"],
        "description": f"Review processor terms for {ctx['workflow_context']} before launch or vendor onboarding.",
        "data_categories": hints["data_categories"],
        "target_users": hints["target_users"],
        "evidence_reference_ids": evidence_ids,
    }


def _processor_inventory(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"PI{index}",
            "processor": vendor,
            "role": "processor or subprocessor",
            "strictness": strictness,
            "data_categories": hints["data_categories"],
            "required_artifacts": ["signed DPA", "security exhibit", "subprocessor list"] if strictness == "strict" else ["DPA review note", "security contact"],
            "evidence_reference_ids": evidence_ids,
        }
        for index, vendor in enumerate(hints["vendors"], start=1)
    ]


def _clause_checks(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    checks = [
        ("CC1", "Processing instructions", "Confirm processing is limited to documented customer instructions."),
        ("CC2", "Confidentiality and security", "Confirm confidentiality duties, technical controls, and incident notice commitments."),
        ("CC3", "Subprocessor controls", "Confirm subprocessor approval, notice, and flow-down obligations."),
        ("CC4", "Deletion and return", "Confirm data return, deletion, and certification duties at termination."),
    ]
    if strictness == "strict":
        checks.extend(
            [
                ("CC5", "Audit and assistance rights", "Confirm audit cooperation, DPIA assistance, and data subject request support."),
                ("CC6", "Regulated transfer terms", "Confirm SCCs or equivalent safeguards for restricted transfers."),
            ]
        )
    return [
        {
            "id": item_id,
            "name": name,
            "owner": "legal_owner" if item_id in {"CC1", "CC3", "CC6"} else "security_owner",
            "required": True,
            "strictness": strictness,
            "description": description,
            "data_categories": hints["data_categories"],
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, name, description in checks
    ]


def _transfer_assessment(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    timing = "complete before production data transfer" if strictness == "strict" else "complete before approval"
    return [
        {
            "id": "TA1",
            "region": region,
            "transfer_mechanism": hints["transfer_mechanism"],
            "strictness": strictness,
            "timing": timing,
            "action": "validate restricted transfer safeguards and residual risk" if strictness == "strict" else "confirm transfer terms are documented",
            "evidence_reference_ids": evidence_ids,
        }
        for region in hints["regions"]
    ]


def _approval_path(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    approvals = [
        ("AP1", "legal_owner", "Approve DPA clause coverage and transfer assessment."),
        ("AP2", "security_owner", "Approve processor security exhibit and evidence gaps."),
        ("AP3", ctx["buyer"], "Approve launch or onboarding decision with accepted remediation."),
    ]
    if strictness == "strict":
        approvals.insert(2, ("AP3", "privacy_owner", "Approve regulated data category and data subject obligations."))
        approvals[-1] = ("AP4", ctx["buyer"], "Approve launch or onboarding decision with accepted remediation.")
    return [
        {
            "id": item_id,
            "owner": owner,
            "decision": description,
            "strictness": strictness,
            "condition": f"required for {', '.join(hints['vendors'])}",
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, owner, description in approvals
    ]


def _remediation_items(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "RI1",
            "name": "Missing or stale DPA artifacts",
            "owner": "legal_owner",
            "severity": "high" if strictness == "strict" else "medium",
            "action": "Block launch or onboarding until signed terms, subprocessors, and transfer safeguards are complete."
            if strictness == "strict"
            else "Track missing artifacts before approval.",
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "RI2",
            "name": "Processor evidence gaps",
            "owner": "security_owner",
            "severity": "high" if hints["sensitive_data"] else "medium",
            "action": "Collect security exhibit, breach notice language, and deletion evidence for reviewed processors.",
            "evidence_reference_ids": evidence_ids,
        },
    ]


def _ordered(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)
