"""Generate deterministic cross-border signal transfer plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.cross_border_signal_transfer_plan.v1"
KIND = "max.spec.cross_border_signal_transfer_plan"


def generate_cross_border_signal_transfer_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "cross_border_signal_transfer")
    flows = unique_records(
        named(
            hints.get("signal_flows") or hints.get("flows") or hints.get("regions"),
            ("signal", "flow", "origin_region", "destination_region"),
        ),
        [
            {
                "name": "cross-border signal transfer flow",
                "owner": "privacy_owner",
                "severity": "high",
                "origin_region": "source region",
                "destination_region": "destination region",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, signal_flow_count=len(flows)),
        "signal_flows": [
            item(
                "CBF",
                index,
                record,
                "privacy_owner",
                evidence_ids,
                "Review cross-border signal transfer flow",
                name_keys=("name", "signal", "flow", "origin_region", "destination_region"),
                extra_keys=("signal", "flow", "origin_region", "destination_region", "data_class"),
            )
            for index, record in enumerate(flows, start=1)
        ],
        "transfer_basis": section(
            hints,
            ("transfer_basis", "legal_basis", "basis"),
            "CBB",
            "legal_owner",
            "Document cross-border transfer basis",
            evidence_ids,
            ["legal basis, transfer impact assessment, and customer contractual allowance"],
        ),
        "safeguards": section(
            hints,
            ("safeguards", "transfer_safeguards", "controls"),
            "CBS",
            "security_owner",
            "Operate transfer safeguard",
            evidence_ids,
            ["encryption, minimization, access controls, regional routing, and processor safeguards"],
        ),
        "residency_checks": section(
            hints,
            ("residency_checks", "residency", "data_residency"),
            "CBR",
            "privacy_owner",
            "Verify data residency",
            evidence_ids,
            ["origin/destination residency check, restricted region blocklist, and retention boundary"],
        ),
        "approval_workflow": section(
            hints,
            ("approval_workflow", "approvals", "reviewers"),
            "CBA",
            "approval_owner",
            "Approve signal transfer",
            evidence_ids,
            ["privacy, legal, security, data owner, and regional reviewer approval"],
        ),
        "monitoring": section(
            hints,
            ("monitoring", "monitors"),
            "CBM",
            "compliance_owner",
            "Monitor cross-border signal transfer",
            evidence_ids,
            ["transfer volume, regional drift, safeguard failures, and processor delivery confirmations"],
        ),
        "rollback_plan": section(
            hints,
            ("rollback_plan", "rollback", "backout"),
            "CBX",
            "privacy_owner",
            "Rollback signal transfer",
            evidence_ids,
            ["pause transfer, restore in-region routing, and purge unauthorized destination copies"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
