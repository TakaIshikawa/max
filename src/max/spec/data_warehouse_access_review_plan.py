"""Generate deterministic data warehouse access review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.data_warehouse_access_review_plan.v1"
KIND = "max.spec.data_warehouse_access_review_plan"


def generate_data_warehouse_access_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_warehouse_access_review")
    roles = unique_records(
        named(hints.get("roles") or hints.get("access_roles") or hints.get("users"), ("role", "user", "group")),
        [
            {
                "name": "warehouse reader",
                "role": "warehouse reader",
                "owner": "data_owner",
                "dataset": "exported signals, insights, evaluations, and generated specs",
            }
        ],
    )
    datasets = unique_records(
        named(
            hints.get("datasets") or hints.get("tables") or hints.get("exports"),
            ("dataset", "table", "export"),
        ),
        [
            {
                "name": "exported signals, insights, evaluations, and generated specs",
                "classification": "internal",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, role_count=len(roles), dataset_count=len(datasets)),
        "scope": section(
            hints,
            ("scope", "review_scope"),
            "DWS",
            "data_governance_owner",
            "Define warehouse access review scope",
            evidence_ids,
            ["exported signals, insights, evaluations, and generated specs in the warehouse"],
        ),
        "access_inventory": [
            item(
                "DWI",
                index,
                record,
                "data_owner",
                evidence_ids,
                "Inventory data warehouse role",
                name_keys=("name", "role", "user", "group"),
                extra_keys=("role", "user", "group", "dataset", "purpose", "classification"),
            )
            for index, record in enumerate(roles, start=1)
        ],
        "dataset_inventory": [
            item(
                "DWD",
                index,
                record,
                "data_owner",
                evidence_ids,
                "Inventory reviewed warehouse dataset",
                name_keys=("name", "dataset", "table", "export"),
                extra_keys=("dataset", "table", "export", "classification", "retention"),
            )
            for index, record in enumerate(datasets, start=1)
        ],
        "review_procedure": section(
            hints,
            ("review_procedure", "procedure", "review_steps"),
            "DWP",
            "data_governance_owner",
            "Run warehouse access review",
            evidence_ids,
            [
                "compare active grants to business need, source ownership, dataset sensitivity, "
                "and last access evidence"
            ],
        ),
        "least_privilege_checks": section(
            hints,
            ("least_privilege_checks", "least_privilege", "checks"),
            "DWL",
            "security_owner",
            "Check warehouse least privilege",
            evidence_ids,
            ["remove broad read, admin, export, or service-account grants without current justification"],
        ),
        "exception_handling": section(
            hints,
            ("exception_handling", "exceptions", "exception_register"),
            "DWX",
            "risk_owner",
            "Handle warehouse access exception",
            evidence_ids,
            ["time-box retained access with owner approval, compensating controls, and expiry review"],
            extra_keys=("role", "dataset", "expiry", "reason"),
        ),
        "remediation_schedule": section(
            hints,
            ("remediation_schedule", "remediation", "remediation_actions"),
            "DWR",
            "data_owner",
            "Schedule warehouse access remediation",
            evidence_ids,
            ["revoke stale grants, narrow roles, rotate service credentials, and confirm removal evidence"],
            extra_keys=("deadline", "role", "dataset"),
        ),
        "audit_artifacts": section(
            hints,
            ("audit_artifacts", "audit_evidence", "evidence"),
            "DWA",
            "data_governance_owner",
            "Capture warehouse access audit artifact",
            evidence_ids,
            ["grant export, reviewer attestation, exception register, removal proof, and final signoff"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
