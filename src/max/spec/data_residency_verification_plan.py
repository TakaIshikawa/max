"""Generate deterministic data residency verification plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_residency_verification_plan.v1"
KIND = "max.spec.data_residency_verification_plan"


def generate_data_residency_verification_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    regions = _values(hints.get("regions"), ["us-east-1"])
    restricted_regions = _values(hints.get("restricted_regions"), [])
    data_classes = _values(hints.get("data_classes"), ["customer data", "metadata"])
    systems = _values(hints.get("systems"), ["application datastore", "object storage"])
    attestation = _truthy(hints.get("customer_attestation_required") or hints.get("attestations"))
    cadence = compact(hints.get("cadence")) or "quarterly"
    strict = bool(restricted_regions) or attestation or ctx["strictness"] == "strict"
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, approved_regions=regions, restricted_regions=restricted_regions, verification_cadence=cadence, customer_attestation_required=attestation),
        "residency_scope": [
            _item("RS1", "approved_regions", "data_owner", f"Verify data remains in approved regions: {', '.join(regions)}.", "high" if strict else "medium", evidence_ids=evidence_ids),
            _item("RS2", "data_classes", "data_owner", f"Apply residency verification to {', '.join(data_classes)}.", "medium", evidence_ids=evidence_ids),
        ],
        "data_locations": [_item(f"DL{index}", system, "platform_owner", f"Record storage, backup, log, and replica locations for {system}.", "high" if strict else "medium", evidence_ids=evidence_ids) for index, system in enumerate(systems, start=1)],
        "verification_checks": _verification_checks(regions, restricted_regions, cadence, strict, evidence_ids),
        "exception_handling": [
            _item("EH1", "restricted_region_exception", "data_owner", "Escalate any restricted-region data placement as a customer-impacting exception." if restricted_regions else "Document and approve any residency exception before production use.", "critical" if restricted_regions else "medium", evidence_ids=evidence_ids),
            _item("EH2", "evidence_capture", "compliance_owner", "Attach query output, cloud inventory, and owner approval to every exception.", "high" if strict else "medium", evidence_ids=evidence_ids),
        ],
        "customer_attestations": [
            _item("CA1", "customer_attestation", "compliance_owner", "Publish customer-facing residency attestation after each verification cycle." if attestation else "Prepare attestation evidence when requested by customers.", "high" if attestation else "medium", evidence_ids=evidence_ids)
        ],
        "remediation_steps": [
            _item("RM1", "move_data", "platform_owner", "Move misplaced data to an approved region and verify replicas, logs, and backups are corrected.", "high" if strict else "medium", evidence_ids=evidence_ids),
            _item("RM2", "customer_notice", "compliance_owner", "Notify affected customer contacts when restricted-region placement is confirmed." if restricted_regions else "Notify stakeholders when remediation changes customer commitments.", "high" if restricted_regions else "medium", evidence_ids=evidence_ids),
        ],
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _verification_checks(regions: list[str], restricted_regions: list[str], cadence: str, strict: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    checks = [
        _item("VC1", "cloud_region_inventory", "platform_owner", f"Export cloud resource regions and compare to approved regions every {cadence}.", "high" if strict else "medium", evidence_ids=evidence_ids),
        _item("VC2", "backup_and_replica_scan", "platform_owner", "Verify backups, replicas, and disaster recovery copies respect residency commitments.", "high" if strict else "medium", evidence_ids=evidence_ids),
    ]
    if restricted_regions:
        checks.append(_item("VC3", "restricted_region_scan", "compliance_owner", f"Run explicit negative checks for restricted regions: {', '.join(restricted_regions)}.", "critical", evidence_ids=evidence_ids))
    return checks


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "data_owner", "suggested_owner": ctx["buyer"], "responsibility": "Own residency scope, commitments, and exception decisions."},
        {"role": "platform_owner", "suggested_owner": "platform_owner", "responsibility": "Produce location inventory and perform remediation moves."},
        {"role": "compliance_owner", "suggested_owner": "compliance_owner", "responsibility": "Maintain attestations, evidence, and customer-facing records."},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("data_residency")
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _truthy(value: Any) -> bool:
    return value is True or compact(value).lower() in {"1", "true", "yes", "y", "required"}


def _item(item_id: str, name: str, owner: str, description: str, severity: str, *, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "description": description, "evidence_reference_ids": evidence_ids or []}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
