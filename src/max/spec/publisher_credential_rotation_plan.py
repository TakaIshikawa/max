"""Generate deterministic publisher credential rotation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SECRET_KEYS = {"secret", "password", "token", "api_key", "private_key", "client_secret"}
SCHEMA_VERSION = "max.spec.publisher_credential_rotation_plan.v1"
KIND = "max.spec.publisher_credential_rotation_plan"


def generate_publisher_credential_rotation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "publisher_credential_rotation")
    creds = [_redact(r) for r in unique_records(named(hints.get("credential_inventory") or hints.get("credentials") or hints.get("destinations"), ("credential", "label", "destination")), [{"name": "publisher credential", "owner": "publishing_owner"}])]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Publisher Credential Rotation Plan", "summary": source_summary(ctx, credential_count=len(creds), dry_run=bool(hints.get("dry_run"))), "affected_publishers": section(hints, ("affected_publishers", "publishers"), "PCRP", "publishing_owner", "Identify affected publisher", evidence_ids, ["publisher destinations using the rotating credential"]), "credential_inventory": [item("PCRC", i, r, "publishing_owner", evidence_ids, "Inventory publisher credential", name_keys=("label", "id", "name", "destination"), extra_keys=("id", "label", "destination", "publisher", "mode", "expires_at")) for i, r in enumerate(creds, 1)], "rotation_sequence": section(hints, ("rotation_sequence", "sequence", "steps"), "PCRS", "publishing_owner", "Rotate publisher credential", evidence_ids, ["create replacement, deploy to dry-run destination, validate publish, promote live, revoke old credential"]), "validation_checks": section(hints, ("validation_checks", "checks"), "PCRV", "publishing_owner", "Validate rotated credential", evidence_ids, ["dry-run publish, live canary publish, audit log confirmation, and failure alert check"]), "rollback_plan": section(hints, ("rollback_plan", "rollback"), "PCRB", "publishing_owner", "Prepare credential rollback", evidence_ids, ["restore prior credential only if not revoked and incident owner approves"]), "communication_plan": section(hints, ("communication_plan", "communications"), "PCRN", "publishing_owner", "Communicate rotation", evidence_ids, ["notify publisher owners, support, and release channel"]), "audit_evidence": section(hints, ("audit_evidence", "evidence"), "PCRA", "publishing_owner", "Capture audit evidence", evidence_ids, ["rotation ticket, validation output, revocation proof, and access log excerpt"]), "evidence_references": ctx["evidence_references"]}


def _redact(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in SECRET_KEYS}
