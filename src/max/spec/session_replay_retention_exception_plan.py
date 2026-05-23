"""Generate deterministic session replay retention exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.session_replay_retention_exception_plan.v1"
KIND = "max.spec.session_replay_retention_exception_plan"


def generate_session_replay_retention_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "session_replay_retention_exception")
    exceptions = unique_records(
        named(
            hints.get("exceptions") or hints.get("requested_exceptions") or hints.get("retention_window"),
            ("request", "window", "product", "account"),
        ),
        [{"name": "temporary session replay retention exception", "owner": "privacy_owner", "severity": "medium", "expiry": "not recorded"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions)),
        "exception_scope": [
            item(
                "SRE",
                index,
                record,
                "privacy_owner",
                evidence_ids,
                "Review session replay retention exception",
                name_keys=("name", "request", "window", "product", "account"),
                extra_keys=("window", "product", "account", "data_class"),
            )
            for index, record in enumerate(exceptions, start=1)
        ],
        "retention_windows": section(hints, ("retention_windows", "windows", "requested_windows"), "SRW", "privacy_owner", "Confirm requested replay retention window", evidence_ids, ["time-boxed replay retention window"], extra_keys=("window", "expires_at")),
        "affected_products_accounts": section(hints, ("affected_products", "products", "accounts", "affected_accounts"), "SRP", "product_owner", "Confirm affected product or account", evidence_ids, ["affected product and account cohort"], extra_keys=("product", "account")),
        "privacy_controls": section(hints, ("privacy_controls", "controls", "compensating_controls"), "SRC", "security_owner", "Operate privacy control", evidence_ids, ["masking, consent, access logging, and least-privilege review"]),
        "approval_path": section(hints, ("approval_path", "approvals", "approvers"), "SRA", "approval_owner", "Capture retention exception approval", evidence_ids, ["privacy, legal, security, product, and customer approval"]),
        "purge_criteria": section(hints, ("purge_criteria", "purge", "deletion_criteria"), "SRD", "data_owner", "Define replay purge criteria", evidence_ids, ["purge retained replays at exception expiry or purpose completion"]),
        "monitoring": section(hints, ("monitoring", "monitors"), "SRM", "compliance_owner", "Monitor replay retention exception", evidence_ids, ["retention window, replay access, masking, and purge completion monitoring"]),
        "rollback": section(hints, ("rollback", "rollback_plan", "remediation"), "SRB", "engineering_owner", "Rollback replay retention exception", evidence_ids, ["restore standard retention and purge exception replays"]),
        "evidence_references": ctx["evidence_references"],
    }
