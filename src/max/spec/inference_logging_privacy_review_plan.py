"""Generate deterministic inference logging privacy review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.inference_logging_privacy_review_plan.v1"
KIND = "max.spec.inference_logging_privacy_review_plan"

_RAW_FIELD_TERMS = ("raw_prompt", "prompt", "raw_response", "response", "completion", "message")
_SENSITIVE_FIELD_TERMS = (
    "prompt",
    "response",
    "completion",
    "message",
    "email",
    "phone",
    "ip",
    "address",
    "token",
    "credential",
    "secret",
    "user",
    "account",
    "session",
)


def generate_inference_logging_privacy_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "inference_logging_privacy_review")
    logged_fields = unique_records(
        named(
            hints.get("logged_fields") or hints.get("fields") or hints.get("log_fields"),
            ("field", "name", "key"),
        ),
        [
            {
                "name": "request_id",
                "field": "request_id",
                "classification": "internal",
                "exposure": "low",
                "redaction": "not required",
            },
            {
                "name": "redacted_prompt_summary",
                "field": "redacted_prompt_summary",
                "classification": "sensitive",
                "exposure": "medium",
                "redaction": "required",
            },
        ],
    )
    logged_field_items = [
        _logged_field_item(index, record, evidence_ids) for index, record in enumerate(logged_fields, start=1)
    ]
    risk_flags = _risk_flags(logged_field_items, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            logged_field_count=len(logged_field_items),
            high_risk_count=sum(1 for flag in risk_flags if flag["severity"] == "high"),
        ),
        "logged_fields": logged_field_items,
        "risk_flags": risk_flags,
        "redaction_controls": section(
            hints,
            ("redaction_controls", "redaction", "privacy_controls"),
            "ILR",
            "privacy_owner",
            "Operate inference log redaction control",
            evidence_ids,
            ["redact prompts, responses, identifiers, secrets, and tenant data before log persistence"],
        ),
        "encryption_controls": section(
            hints,
            ("encryption_controls", "encryption", "storage_controls"),
            "ILE",
            "security_owner",
            "Protect inference logs with encryption",
            evidence_ids,
            ["encrypt inference logs at rest and in transit with managed keys and rotation evidence"],
        ),
        "retention_period": section(
            hints,
            ("retention_period", "retention", "retention_window"),
            "ILT",
            "data_owner",
            "Set inference log retention period",
            evidence_ids,
            ["retain inference logs for 30 days unless an approved exception shortens or extends the window"],
            extra_keys=("duration", "expires_at", "expiry"),
        ),
        "sampling_access": section(
            hints,
            ("sampling_access", "sampling", "access_review", "reviewers"),
            "ILS",
            "security_owner",
            "Review sampled inference log access",
            evidence_ids,
            ["least-privilege sampled access for privacy, security, model, and incident reviewers"],
            extra_keys=("sampling_rate", "role", "reviewer"),
        ),
        "access_monitoring": section(
            hints,
            ("access_monitoring", "monitoring", "monitors"),
            "ILM",
            "compliance_owner",
            "Monitor inference log access",
            evidence_ids,
            ["alert on bulk export, unusual reviewer access, redaction failures, and retention breaches"],
        ),
        "incident_triggers": section(
            hints,
            ("incident_triggers", "triggers", "incident_response"),
            "ILI",
            "incident_owner",
            "Escalate inference logging privacy incident",
            evidence_ids,
            ["raw prompt or response captured unredacted, secret detected, unauthorized export, or retention breach"],
        ),
        "approval_gates": section(
            hints,
            ("approval_gates", "approvals", "gates"),
            "ILG",
            "privacy_owner",
            "Approve inference logging privacy gate",
            evidence_ids,
            ["privacy, security, data owner, and model owner approval before enabling sensitive inference logs"],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _logged_field_item(index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    row = item(
        "ILF",
        index,
        record,
        "privacy_owner",
        evidence_ids,
        "Classify inference log field",
        name_keys=("name", "field", "key"),
        extra_keys=("field", "classification", "exposure", "redaction", "encrypted", "sampling"),
    )
    name = compact(row.get("field") or row.get("name")).lower()
    classification = compact(row.get("classification")) or _classification_for(name)
    exposure = compact(row.get("exposure")) or ("high" if _is_raw_sensitive(row) else _exposure_for(name))
    return {**row, "classification": classification, "exposure": exposure}


def _risk_flags(fields: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for field in fields:
        if _is_raw_sensitive(field):
            flags.append(
                item(
                    "ILH",
                    len(flags) + 1,
                    {
                        "name": f"unredacted {field['name']}",
                        "severity": "high",
                        "field": field.get("field") or field["name"],
                        "description": "Raw prompt or response logging is enabled without redaction.",
                    },
                    "privacy_owner",
                    evidence_ids,
                    "Flag high-risk inference log exposure",
                    extra_keys=("field",),
                )
            )
    return flags or [
        item(
            "ILH",
            1,
            {
                "name": "no unredacted raw prompt or response logging identified",
                "severity": "low",
                "description": "Logged fields do not indicate unredacted raw prompt or response capture.",
            },
            "privacy_owner",
            evidence_ids,
            "Record inference logging privacy risk",
        )
    ]


def _classification_for(name: str) -> str:
    return "sensitive" if any(term in name for term in _SENSITIVE_FIELD_TERMS) else "internal"


def _exposure_for(name: str) -> str:
    return "medium" if any(term in name for term in _SENSITIVE_FIELD_TERMS) else "low"


def _is_raw_sensitive(field: dict[str, Any]) -> bool:
    name = compact(field.get("field") or field.get("name")).lower()
    redaction = compact(field.get("redaction")).lower()
    is_raw = "raw" in name or compact(field.get("raw")).lower() in {"true", "yes", "1"}
    is_prompt_or_response = any(term in name for term in _RAW_FIELD_TERMS)
    is_unredacted = redaction in {"", "none", "no", "false", "unredacted", "disabled", "not applied"}
    return is_prompt_or_response and (is_raw or "prompt" in name or "response" in name) and is_unredacted
