"""Generate deterministic incident evidence preservation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.incident_evidence_preservation_plan.v1"
KIND = "max.spec.incident_evidence_preservation_plan"


def generate_incident_evidence_preservation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "incident_evidence_preservation")
    sources = unique_records(
        named(hints.get("evidence_sources") or hints.get("sources"), ("source", "system", "owner")),
        [{"name": "incident evidence source", "owner": "security_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, evidence_source_count=len(sources)),
        "incident_scope": section(hints, ("incident_scope", "scope"), "IEI", "incident_commander", "Confirm incident evidence scope", evidence_ids, ["incident timeline, systems, customers, and severity"]),
        "evidence_inventory": [
            item("IES", index, record, "security_owner", evidence_ids, "Preserve incident evidence source", name_keys=("name", "source", "system"), extra_keys=("source", "system", "retention", "custodian"))
            for index, record in enumerate(sources, start=1)
        ],
        "preservation_actions": section(hints, ("preservation", "preservation_actions"), "IEP", "security_owner", "Execute preservation action", evidence_ids, ["log export, snapshot, timeline, and immutable storage action"]),
        "retention_holds": section(hints, ("retention", "retention_holds"), "IER", "legal_owner", "Apply retention hold", evidence_ids, ["legal and incident retention hold"]),
        "access_controls": section(hints, ("access_controls", "access"), "IEA", "security_owner", "Restrict evidence access", evidence_ids, ["least privilege access and reviewer list"]),
        "custody_log": section(hints, ("custody", "custody_log"), "IEC", "legal_owner", "Maintain custody log", evidence_ids, ["chain-of-custody entry and transfer approval"]),
        "owners": section(hints, ("owners", "legal_security_owners"), "IEO", "incident_commander", "Assign evidence owner", evidence_ids, ["legal, security, and incident owner"]),
        "integrity_checks": section(hints, ("integrity", "integrity_checks"), "IEV", "security_owner", "Verify evidence integrity", evidence_ids, ["hash, timestamp, and access log verification"]),
        "release_criteria": section(hints, ("release", "release_criteria"), "IEX", "legal_owner", "Release preserved evidence", evidence_ids, ["legal release criteria and post-incident retention decision"]),
        "evidence_references": ctx["evidence_references"],
    }
