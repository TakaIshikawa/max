"""Generate deterministic data subject request runbooks."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.spec.data_subject_request_runbook.v1"
KIND = "max.spec.data_subject_request_runbook"


def generate_data_subject_request_runbook(request_context: dict[str, Any]) -> dict[str, Any]:
    """Return a stable DSR runbook from request and system context."""
    ctx = _context(request_context)
    deletion = ctx["request_type"] == "deletion"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "request_type": ctx["request_type"],
        "intake": {
            "channels": ctx["intake_channels"],
            "required_fields": ["requester", "jurisdiction", "request type", "submission timestamp"],
        },
        "identity_verification": [
            "Match requester email to account record.",
            "Require step-up verification before exporting, deleting, or disclosing personal data.",
        ],
        "request_classification": {
            "primary_type": ctx["request_type"],
            "supported_types": ["access", "export", "correction", "deletion", "restriction"],
        },
        "system_lookup": ctx["systems"],
        "fulfillment_steps": _fulfillment_steps(ctx, deletion),
        "deletion_export_handling": {
            "export_format": "machine-readable JSON and CSV where available",
            "deletion_mode": "hard delete or anonymize after retention review" if deletion else "not applicable unless requested",
        },
        "exceptions": _exceptions(deletion),
        "audit_evidence": _audit_evidence(deletion),
        "sla_tracking": {
            "acknowledgement": "same business day",
            "fulfillment": ctx["sla"],
            "extension_review": "before original due date",
        },
        "escalation": [
            {"condition": "identity cannot be verified", "owner": ctx["privacy_owner"]},
            {"condition": "legal hold, retention, or security exception applies", "owner": ctx["legal_owner"]},
            {"condition": "SLA at risk", "owner": ctx["operations_owner"]},
        ],
    }


def _fulfillment_steps(ctx: dict[str, Any], deletion: bool) -> list[str]:
    steps = [
        "Open tracked case and confirm request scope.",
        "Search account, product, support, billing, and integration records.",
        "Prepare response package and reviewer checklist.",
    ]
    if deletion:
        steps.append("Run deletion workflow only after exception and retention review.")
        steps.append("Confirm downstream processors received deletion or anonymization instruction.")
    else:
        steps.append("Generate export package and validate redaction boundaries.")
    return steps


def _exceptions(deletion: bool) -> list[str]:
    exceptions = [
        "Reject or narrow requests that fail identity verification.",
        "Document security, fraud, legal hold, and statutory retention exceptions.",
    ]
    if deletion:
        exceptions.append("Preserve records required for tax, financial, abuse-prevention, or legal obligations.")
    return exceptions


def _audit_evidence(deletion: bool) -> list[str]:
    evidence = [
        "request intake record and identity verification proof",
        "system search results and reviewer approval",
        "final response artifact and timestamped delivery record",
    ]
    if deletion:
        evidence.append("deletion job IDs, processor confirmations, and exception rationale")
    return evidence


def _context(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    request_type = (_text(raw.get("request_type")) or "access").lower()
    return {
        "request_type": request_type,
        "intake_channels": _list(raw.get("intake_channels")) or ["privacy email", "support ticket"],
        "systems": _list(raw.get("systems")) or ["application database", "support desk", "billing system", "audit logs"],
        "sla": _text(raw.get("sla")) or "30 calendar days",
        "privacy_owner": _text(raw.get("privacy_owner")) or "Privacy owner",
        "legal_owner": _text(raw.get("legal_owner")) or "Legal owner",
        "operations_owner": _text(raw.get("operations_owner")) or "Operations owner",
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
