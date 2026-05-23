"""Generate deterministic OAuth app decommission plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.oauth_app_decommission_plan.v1"
KIND = "max.spec.oauth_app_decommission_plan"


def generate_oauth_app_decommission_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "oauth_app_decommission")
    apps = unique_records(
        named(hints.get("app_inventory") or hints.get("apps") or hints.get("oauth_apps"), ("app", "client_id", "name")),
        [{"name": "legacy OAuth application", "owner": "identity_owner", "severity": "high"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, app_count=len(apps)),
        "app_inventory": [item("OAI", index, record, "identity_owner", evidence_ids, "Inventory OAuth app", name_keys=("name", "app", "client_id"), extra_keys=("app", "client_id", "environment")) for index, record in enumerate(apps, start=1)],
        "scope_review": section(hints, ("scopes", "scope_review"), "OAS", "security_owner", "Review OAuth scopes", evidence_ids, ["least-privilege scope review and unused scope removal"], extra_keys=("scope",)),
        "dependency_review": section(hints, ("dependent_integrations", "dependencies", "dependency_review"), "OAD", "integration_owner", "Review OAuth app dependency", evidence_ids, ["dependent integrations and user impact"]),
        "communications": section(hints, ("communications", "customer_communication", "user_communication"), "OAC", "customer_owner", "Communicate OAuth decommission", evidence_ids, ["user and customer decommission notice"]),
        "token_revocation": section(hints, ("token_revocation", "revocation"), "OAT", "identity_owner", "Revoke OAuth tokens", evidence_ids, ["token inventory, revocation checklist, and post-revocation audit"]),
        "replacement_mapping": section(hints, ("replacement_mapping", "replacement_apps", "replacements"), "OAR", "integration_owner", "Map replacement OAuth app", evidence_ids, ["replacement app or integration owner mapping"]),
        "validation": section(hints, ("validation", "validation_checks"), "OAV", "qa_owner", "Validate OAuth decommission", evidence_ids, ["authentication, integration, and audit validation"]),
        "rollback_limits": section(hints, ("rollback_limits", "rollback"), "OAL", "identity_owner", "Document rollback limit", evidence_ids, ["rollback window and reauthorization limits"]),
        "evidence_references": ctx["evidence_references"],
    }
