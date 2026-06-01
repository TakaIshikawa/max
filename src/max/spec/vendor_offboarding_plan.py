"""Generate deterministic vendor offboarding plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.vendor_offboarding_plan.v1"
KIND = "max.spec.vendor_offboarding_plan"


def generate_vendor_offboarding_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    vendor = _required(hints, "vendor_name", "vendor name")
    owner = _required(hints, "owner", "owner")
    credentials = _list(hints.get("credentials"), [])
    retained_data = _list(hints.get("retained_data"), [])
    dependencies = _list(hints.get("downstream_dependencies"), [])
    attestations = _list(hints.get("owner_attestations"), [])
    active_credentials = [item for item in credentials if "active" in item.casefold()]
    blockers = active_credentials + retained_data + dependencies + ([] if attestations else ["missing owner attestations"])
    refs = [item["id"] for item in ctx["evidence_references"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, vendor=vendor, blocker_count=len(blockers), final_approval_blocked=bool(blockers)),
        "dependency_review": [_row("VOD", i, item, owner, f"Resolve downstream dependency before offboarding {vendor}: {item}.", refs, status="blocked") for i, item in enumerate(dependencies or ["no downstream dependencies recorded"], 1)],
        "credential_revocation": [_row("VOC", i, item, owner, f"Revoke credential for {vendor}: {item}.", refs, status="blocked" if item in active_credentials else "planned") for i, item in enumerate(credentials or ["credential inventory"], 1)],
        "data_return_deletion": [_row("VOR", i, item, "privacy_owner", f"Return or delete retained vendor data: {item}.", refs, status="blocked") for i, item in enumerate(retained_data or ["data deletion attestation"], 1)],
        "communication_steps": [_row("VOM", 1, "Stakeholder communication", owner, f"Notify business, legal, security, and support teams for {vendor} offboarding.", refs)],
        "evidence_capture": [_row("VOE", 1, "Evidence capture", owner, "Capture revocation, deletion, attestations, and final approval evidence.", refs)],
        "blockers": [_row("VOB", i, item, owner, f"Clear offboarding blocker: {item}.", refs, status="blocked") for i, item in enumerate(blockers, 1)],
        "final_approval": [_row("VOA", 1, "Final offboarding approval", owner, "Approve only when blockers are cleared and evidence is complete.", refs, status="blocked" if blockers else "ready")],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("vendor_offboarding")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    value = compact(hints.get(key))
    if not value:
        raise ValueError(f"vendor_offboarding requires {label}")
    return value


def _list(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(item for item in values if item), key=str.casefold) or fallback


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
