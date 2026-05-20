"""Generate deterministic integration credential rotation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.integration_credential_rotation_plan.v1"
KIND = "max.spec.integration_credential_rotation_plan"


def generate_integration_credential_rotation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "integration_credential_rotation")
    credentials = unique_records(
        hints.get("credential_inventory") or hints.get("credentials") or hints.get("integrations"),
        [
            {
                "name": "integration credential",
                "owner": "integration_owner",
                "description": "Inventory credentials requiring rotation.",
            }
        ],
    )
    sequence = unique_records(
        hints.get("rotation_sequence") or hints.get("rotation_steps"),
        [
            {
                "name": "rotate credential",
                "owner": "integration_owner",
                "description": "Rotate credential, deploy dependent services, and revoke old secret.",
            }
        ],
    )
    dependencies = unique_records(
        hints.get("dependent_services") or hints.get("dependencies"),
        [
            {
                "name": ctx["stack_label"] or "application service",
                "owner": "service_owner",
                "description": "Confirm dependent service uses the rotated credential.",
            }
        ],
    )
    rollback = unique_records(
        hints.get("rollback_path") or hints.get("rollback"),
        [
            {
                "name": "credential rollback path",
                "owner": "integration_owner",
                "description": "Restore prior credential only if revocation has not completed.",
            }
        ],
    )
    approvals = unique_records(
        hints.get("owner_approvals") or hints.get("approvals"),
        [
            {
                "name": "rotation approval",
                "owner": "security_owner",
                "description": "Approve rotation order, dependencies, rollback, and validation.",
            }
        ],
    )
    notices = unique_records(
        hints.get("partner_notices")
        or hints.get("customer_partner_notices")
        or hints.get("notices"),
        [
            {
                "name": "partner credential notice",
                "owner": "partner_owner",
                "description": "Notify customers or partners when credential changes affect integration setup.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "credential rotation validation",
                "owner": "security_owner",
                "description": "Validate rotated credentials, dependent services, rollback constraints, and notices.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx, credential_count=len(credentials), dependent_service_count=len(dependencies)
        ),
        "credential_inventory": [
            _item("CRED", index, item, "integration_owner", evidence_ids)
            for index, item in enumerate(credentials, start=1)
        ],
        "rotation_sequence": [
            _item("ROT", index, item, "integration_owner", evidence_ids)
            for index, item in enumerate(sequence, start=1)
        ],
        "dependent_services": [
            _item("DEP", index, item, "service_owner", evidence_ids)
            for index, item in enumerate(dependencies, start=1)
        ],
        "rollback_path": [
            _item("RB", index, item, "integration_owner", evidence_ids)
            for index, item in enumerate(rollback, start=1)
        ],
        "owner_approvals": [
            _item("APP", index, item, "security_owner", evidence_ids)
            for index, item in enumerate(approvals, start=1)
        ],
        "partner_notices": [
            _item("NOT", index, item, "partner_owner", evidence_ids)
            for index, item in enumerate(notices, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "security_owner", evidence_ids)
            for index, item in enumerate(checks, start=1)
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _item(
    prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return row(
        prefix,
        index,
        compact(item.get("name")),
        compact(item.get("owner")) or owner,
        compact(item.get("description")) or compact(item.get("name")),
        evidence_ids,
        severity=item.get("severity"),
        status=item.get("status"),
        rotation_date=item.get("rotation_date") or item.get("due") or item.get("deadline"),
    )
