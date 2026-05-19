"""Generate deterministic customer data export plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.customer_data_export_plan.v1"
CUSTOMER_DATA_EXPORT_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.customer_data_export_plan"


def generate_customer_data_export_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic planning data for customer data exports."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _export_hints(spec)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    strictness = "strict" if hints["regulated"] or hints["sensitive"] else ctx["strictness"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            export_strictness=strictness,
            data_categories=hints["data_categories"],
            source_system_count=len(hints["source_systems"]),
            delivery_path=hints["delivery_path"],
            export_format=hints["format"],
        ),
        "export_scope": _export_scope(ctx, hints, strictness, evidence_ids),
        "data_sources": _data_sources(hints, evidence_ids),
        "format_and_delivery": _format_and_delivery(ctx, hints, strictness, evidence_ids),
        "access_controls": _access_controls(hints, strictness, evidence_ids),
        "validation_checks": _validation_checks(ctx, hints, strictness, evidence_ids),
        "retention_and_cleanup": _retention_and_cleanup(hints, strictness, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _export_hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    export = metadata.get("data_export") if isinstance(metadata.get("data_export"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    integrations = _ordered(
        string_list(metadata.get("integrations"))
        + string_list(export.get("integrations"))
        + string_list(export.get("source_systems"))
    )
    source_systems = _ordered(integrations + string_list(execution.get("mvp_scope")) + string_list(export.get("systems")))
    data_categories = _ordered(
        string_list(metadata.get("data_categories"))
        + string_list(export.get("data_categories"))
        + string_list(project.get("data_categories"))
    )
    regions = _ordered(string_list(metadata.get("regulatory_regions")) + string_list(export.get("regulatory_regions")))
    text = " ".join(
        data_categories
        + regions
        + string_list(execution.get("risks"))
        + string_list(metadata.get("risks"))
        + [
            compact(export.get("scope")),
            compact(export.get("format")),
            compact(project.get("workflow_context")),
            compact(project.get("summary")),
        ]
    ).lower()
    sensitive = any(
        term in text
        for term in (
            "pii",
            "personal data",
            "email",
            "payment",
            "health",
            "credential",
            "financial",
            "customer data",
            "sensitive",
        )
    )
    regulated = bool(regions) or any(term in text for term in ("gdpr", "ccpa", "cpra", "hipaa", "sox", "regulated", "compliance"))

    return {
        "scope": compact(export.get("scope")) or "customer-requested account export",
        "requester": compact(export.get("requester") or export.get("audience")) or "verified customer requester",
        "data_categories": data_categories or ["profile data", "account activity"],
        "source_systems": source_systems or ["primary application database"],
        "integrations": integrations,
        "format": compact(export.get("format")) or "CSV and JSON package",
        "delivery_path": compact(export.get("delivery_path") or export.get("delivery")) or "time-limited secure download link",
        "retention_period": compact(export.get("retention_period")) or "7 days after delivery",
        "regulated_regions": regions,
        "sensitive": sensitive,
        "regulated": regulated,
    }


def _export_scope(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": "ES1",
        "name": "Customer export scope",
        "owner": "privacy_owner",
        "strictness": strictness,
        "scope": hints["scope"],
        "requester": hints["requester"],
        "workflow_context": ctx["workflow_context"],
        "included_data_categories": hints["data_categories"],
        "excluded_data_categories": ["internal risk notes", "third-party confidential data", "security secrets"],
        "evidence_reference_ids": evidence_ids,
    }


def _data_sources(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"DS{index}",
            "system": system,
            "owner": "data_owner",
            "extraction_method": "audited read-only export job",
            "data_categories": hints["data_categories"],
            "evidence_reference_ids": evidence_ids,
        }
        for index, system in enumerate(hints["source_systems"], start=1)
    ]


def _format_and_delivery(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": "FD1",
        "name": "Export package and delivery",
        "owner": "technical_owner",
        "format": hints["format"],
        "delivery_path": hints["delivery_path"],
        "encryption": "per-request encrypted archive with separate credential channel" if strictness == "strict" else "encrypted archive",
        "customer_guidance": f"Include schema notes and field descriptions for {ctx['target_user']}.",
        "evidence_reference_ids": evidence_ids,
    }


def _access_controls(hints: dict[str, Any], strictness: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    controls = [
        _control("AC1", "Requester verification", "support_owner", "verify requester identity before export generation", evidence_ids),
        _control("AC2", "Least-privilege export job", "technical_owner", "run export with scoped read-only credentials and audit logging", evidence_ids),
        _control("AC3", "Time-limited delivery access", "security_owner", "expire the delivery path after the configured retention window", evidence_ids),
    ]
    if strictness == "strict":
        controls.extend(
            [
                _control("AC4", "Dual approval", "privacy_owner", "require privacy and data-owner approval before releasing regulated or sensitive exports", evidence_ids),
                _control("AC5", "Out-of-band delivery verification", "security_owner", "send access credentials through a separate verified channel", evidence_ids),
            ]
        )
    return controls


def _validation_checks(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    checks = [
        _check("VC1", "Scope completeness", "data_owner", f"confirm export includes approved {ctx['workflow_context']} records only", evidence_ids),
        _check("VC2", "Format integrity", "qa_owner", f"validate {hints['format']} files open, parse, and match documented schema", evidence_ids),
        _check("VC3", "Delivery audit trail", "security_owner", "record generation, approval, delivery, access, and expiry timestamps", evidence_ids),
    ]
    if strictness == "strict":
        checks.extend(
            [
                _check("VC4", "Sensitive-data redaction review", "privacy_owner", "confirm secrets, internal notes, and unrelated third-party data are excluded", evidence_ids),
                _check("VC5", "Record-count reconciliation", "data_owner", "reconcile source counts against package manifests before release", evidence_ids),
            ]
        )
    return checks


def _retention_and_cleanup(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "RC1",
            "name": "Package retention",
            "owner": "privacy_owner",
            "retention_period": hints["retention_period"],
            "cleanup_action": "delete export package, temporary files, and delivery credentials",
            "verification": "deletion proof required" if strictness == "strict" else "cleanup log required",
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "RC2",
            "name": "Audit record retention",
            "owner": "security_owner",
            "retention_period": "policy audit window",
            "cleanup_action": "retain audit metadata without customer export payload",
            "verification": "privacy owner reviews retained metadata",
            "evidence_reference_ids": evidence_ids,
        },
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "privacy_owner", "suggested_owner": ctx["buyer"], "responsibility": "Own export scope, approval policy, and customer data handling requirements."},
        {"role": "data_owner", "suggested_owner": "data_owner", "responsibility": "Map source systems, reconcile counts, and confirm data category completeness."},
        {"role": "technical_owner", "suggested_owner": "technical_owner", "responsibility": "Build export package, schema, delivery path, and cleanup automation."},
        {"role": "security_owner", "suggested_owner": "security_owner", "responsibility": "Own encryption, access expiry, audit logging, and delivery verification controls."},
        {"role": "support_owner", "suggested_owner": "support_owner", "responsibility": "Verify requester identity and coordinate customer-facing fulfillment."},
    ]


def _control(item_id: str, name: str, owner: str, description: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "description": description,
        "evidence_reference_ids": evidence_ids,
    }


def _check(item_id: str, name: str, owner: str, description: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "description": description,
        "evidence_reference_ids": evidence_ids,
    }


def _ordered(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)
