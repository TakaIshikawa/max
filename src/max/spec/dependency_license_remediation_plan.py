"""Generate deterministic dependency license remediation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.dependency_license_remediation_plan.v1"
KIND = "max.spec.dependency_license_remediation_plan"


def generate_dependency_license_remediation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "dependency_license_remediation")
    severity = compact(hints.get("severity")) or "unknown"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, severity=severity),
        "dependency_inventory": section(hints, ("dependencies", "dependency_inventory"), "DLR", "engineering_owner", "Inventory dependency license", evidence_ids, ["dependency name, version, license, usage, owner"]),
        "license_findings": section(hints, ("license_findings", "findings"), "DLF", "legal_owner", "Review license finding", evidence_ids, ["unknown license", "restricted license", "policy exception required"]),
        "remediation_paths": section(hints, ("remediation_paths", "replacements"), "DLP", "engineering_owner", "Remediate dependency license", evidence_ids, ["upgrade", "replace", "remove", "isolate usage"]),
        "exception_paths": section(hints, ("exception_paths", "exceptions"), "DLE", "legal_owner", "Document license exception", evidence_ids, ["business justification, scope, expiration, compensating control"]),
        "owner_assignments": section(hints, ("owners", "owner_assignments"), "DLO", "program_owner", "Assign remediation owner", evidence_ids, ["engineering owner, legal reviewer, release approver"]),
        "validation": section(hints, ("validation", "checks"), "DLV", "qa_owner", "Validate license remediation", evidence_ids, ["SBOM scan clean, build passes, replacement behavior verified"]),
        "release_sequencing": section(hints, ("release_sequencing", "release"), "DLS", "release_owner", "Sequence dependency remediation release", evidence_ids, ["branch update, staging scan, production release, post-release scan"]),
        "legal_signoff": section(hints, ("legal_signoff", "signoff"), "DLL", "legal_owner", "Approve license remediation", evidence_ids, ["legal signoff before release or exception approval"]),
        "evidence_references": ctx["evidence_references"],
    }
