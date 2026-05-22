"""Generate deterministic emergency secrets rotation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.secrets_rotation_emergency_plan.v1"
KIND = "max.spec.secrets_rotation_emergency_plan"


def generate_secrets_rotation_emergency_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "secrets_rotation_emergency")
    secrets = unique_records(
        named(hints.get("secrets") or hints.get("affected_secrets"), ("secret", "system")),
        [{"name": "emergency secret rotation item", "owner": "security_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, secret_count=len(secrets)),
        "affected_secrets": [
            item("SRE", index, record, "security_owner", evidence_ids, "Rotate affected secret", name_keys=("name", "secret", "system"), extra_keys=("secret", "system", "exposure", "rotation_order"))
            for index, record in enumerate(secrets, start=1)
        ],
        "affected_systems": section(hints, ("systems", "affected_systems"), "SRS", "system_owner", "Confirm affected system", evidence_ids, ["system consuming exposed or suspect credential"], extra_keys=("system",)),
        "owner_assignments": section(hints, ("owners", "owner_assignments"), "SRO", "security_owner", "Assign rotation owner", evidence_ids, ["security, service owner, validation, and comms owner"]),
        "rotation_phases": section(hints, ("rotation_phases", "rotation_order", "phases"), "SRP", "security_owner", "Execute emergency rotation phase", evidence_ids, ["contain, revoke, rotate, deploy, validate, and monitor"]),
        "validation_checks": section(hints, ("validation", "validation_checks"), "SRV", "qa_owner", "Validate emergency rotation", evidence_ids, ["authentication, integration, health, and access log validation"]),
        "containment_rollback": section(hints, ("rollback", "containment", "containment_rollback"), "SRB", "incident_commander", "Contain or rollback rotation", evidence_ids, ["disable suspect credential, isolate dependent service, and restore last known-good config"]),
        "communications": section(hints, ("communications",), "SRC", "incident_commander", "Coordinate emergency rotation communication", evidence_ids, ["security, engineering, support, customer, and executive communication"]),
        "evidence_references": ctx["evidence_references"],
    }
