"""Generate deterministic third-party LLM subprocessor review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.third_party_llm_subprocessor_review_plan.v1"
KIND = "max.spec.third_party_llm_subprocessor_review_plan"


def generate_third_party_llm_subprocessor_review_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "third_party_llm_subprocessor_review")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    subprocessors = unique_records(
        named(
            hints.get("subprocessors")
            or hints.get("llm_subprocessors")
            or hints.get("providers")
            or hints.get("vendors"),
            ("subprocessor", "provider", "vendor", "model"),
        ),
        [
            {
                "name": "proposed LLM subprocessor",
                "purpose": "LLM inference support",
                "data_access": "customer prompts and metadata",
                "region": "region pending review",
                "owner": "vendor_owner",
                "severity": "medium",
            }
        ],
    )
    contractual_risks = _contractual_risks(subprocessors, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Third Party LLM Subprocessor Review Plan",
        "summary": source_summary(
            ctx,
            subprocessor_count=len(subprocessors),
            contractual_risk_count=len(contractual_risks),
        ),
        "subprocessors": [
            item(
                "TLS",
                index,
                record,
                "vendor_owner",
                evidence_ids,
                "Review third-party LLM subprocessor",
                name_keys=("name", "subprocessor", "provider", "vendor", "model"),
                extra_keys=(
                    "subprocessor",
                    "provider",
                    "vendor",
                    "purpose",
                    "data_access",
                    "data_categories",
                    "region",
                ),
            )
            for index, record in enumerate(subprocessors, start=1)
        ],
        "data_categories": section(
            hints,
            ("data_categories", "data_category", "shared_data", "data_access"),
            "TLD",
            "privacy_owner",
            "Classify subprocessor data category",
            evidence_ids,
            ["customer prompts, outputs, metadata, embeddings, support attachments, and account identifiers"],
        ),
        "regions": section(
            hints,
            ("regions", "region_review", "residency", "data_residency"),
            "TLR",
            "privacy_owner",
            "Review subprocessor processing region",
            evidence_ids,
            ["primary processing, failover, support access, and transfer mechanism by region"],
            extra_keys=("region",),
        ),
        "contractual_controls": section(
            hints,
            ("contractual_controls", "contracts", "controls"),
            "TLC",
            "legal_owner",
            "Confirm LLM subprocessor contractual control",
            evidence_ids,
            ["DPA, SCCs or transfer terms, no-training commitment, retention limits, audit rights, and deletion SLA"],
        ),
        "security_review": section(
            hints,
            ("security_review", "security", "security_questionnaire"),
            "TLQ",
            "security_owner",
            "Complete subprocessor security questionnaire",
            evidence_ids,
            ["security questionnaire, SOC 2 or ISO evidence, encryption, access logging, and incident notice path"],
        ),
        "customer_notification": section(
            hints,
            ("customer_notification", "customer_notice", "notification"),
            "TLN",
            "customer_comms_owner",
            "Prepare customer subprocessor notice",
            evidence_ids,
            ["customer notice, objection window, trust center update, and account team enablement"],
        ),
        "fallback_provider": section(
            hints,
            ("fallback_provider", "fallback_plan", "fallback"),
            "TLF",
            "ml_platform_owner",
            "Confirm fallback LLM provider",
            evidence_ids,
            ["approved provider route, local model, degraded workflow, or manual review fallback"],
        ),
        "approval_checklist": section(
            hints,
            ("approval_checklist", "approvals", "approval_gates"),
            "TLA",
            "program_owner",
            "Gate LLM subprocessor approval",
            evidence_ids,
            ["legal, privacy, security, model owner, customer communications, and executive approval"],
        ),
        "contractual_risks": contractual_risks,
        "evidence_references": ctx["evidence_references"],
    }


def _contractual_risks(
    subprocessors: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for record in subprocessors:
        if _has_contractual_controls(record):
            continue
        name = (
            compact(record.get("name"))
            or compact(record.get("subprocessor"))
            or compact(record.get("provider"))
            or "proposed LLM subprocessor"
        )
        risks.append(
            row(
                "TLX",
                len(risks) + 1,
                f"missing contractual controls for {name}",
                compact(record.get("owner")) or "legal_owner",
                f"Resolve DPA, no-training, retention, audit, and deletion terms before approving {name}.",
                evidence_ids,
                severity="high",
                subprocessor=name,
                status="missing_contractual_controls",
            )
        )
    return risks


def _has_contractual_controls(record: dict[str, Any]) -> bool:
    value = (
        record.get("contractual_controls")
        or record.get("controls")
        or record.get("dpa")
        or record.get("dpa_status")
    )
    text = compact(value).lower()
    return bool(text) and text not in {"missing", "none", "false", "no", "tbd", "unknown"}
