"""Generate deterministic SSO certificate rotation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, rank, source_summary, unique_records


SCHEMA_VERSION = "max.spec.sso_certificate_rotation_plan.v1"
KIND = "max.spec.sso_certificate_rotation_plan"


def generate_sso_certificate_rotation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "sso_certificate_rotation")
    certs = sorted(
        unique_records(
            named(hints.get("certificates") or hints.get("tenants") or hints.get("identity_providers"), ("tenant", "idp", "certificate")),
            [{"name": "customer SSO certificate", "owner": "identity_owner", "severity": "medium", "expiry": "not recorded"}],
        ),
        key=_certificate_sort_key,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, certificate_count=len(certs)),
        "idp_tenant_scope": [
            item("SSO", index, record, "identity_owner", evidence_ids, "Review SSO certificate scope", name_keys=("name", "tenant", "idp", "certificate"), extra_keys=("tenant", "idp", "certificate", "expiry"))
            for index, record in enumerate(certs, start=1)
        ],
        "certificate_details": section(hints, ("certificate_details", "metadata"), "SSC", "identity_owner", "Confirm certificate detail", evidence_ids, ["current and replacement certificate metadata"]),
        "customer_notices": section(hints, ("notices", "customer_notices"), "SSN", "customer_success_owner", "Send customer certificate notice", evidence_ids, ["customer notice with validation and cutover window"]),
        "validation_windows": section(hints, ("validation", "validation_windows", "tests"), "SSV", "qa_owner", "Validate SSO rotation", evidence_ids, ["successful SAML or OIDC login test and expired-certificate prevention check"]),
        "cutover_steps": section(hints, ("cutover", "cutover_steps", "rotation_steps"), "SSR", "identity_owner", "Rotate SSO certificate", evidence_ids, ["upload, activate, validate, and deprecate old certificate"]),
        "fallback_access": section(hints, ("fallback", "fallback_access"), "SSF", "support_owner", "Confirm fallback access", evidence_ids, ["break-glass admin or alternate login path"]),
        "monitoring": section(hints, ("monitoring", "monitors"), "SSM", "on_call_owner", "Monitor SSO rotation", evidence_ids, ["login success, IdP error, and certificate expiry monitor"]),
        "rollback": section(hints, ("rollback", "rollback_steps"), "SSX", "identity_owner", "Rollback SSO certificate rotation", evidence_ids, ["restore prior valid certificate within rollback window"]),
        "evidence_references": ctx["evidence_references"],
    }


def _certificate_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    expiry = compact(record.get("expiry") or record.get("expiration")).lower()
    expiry_rank = 0 if "expired" in expiry else 1 if any(term in expiry for term in ("near", "soon", "30", "14", "7")) else 2
    return (expiry_rank, rank(record.get("severity")), compact(record.get("name")).casefold())
