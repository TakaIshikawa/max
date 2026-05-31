"""Generate deterministic source credential rotation remediation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._compact_plan_common import named
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.source_credential_rotation_plan.v1"
KIND = "max.spec.source_credential_rotation_plan"


def generate_source_credential_rotation_plan(spec_like: Any) -> dict[str, Any]:
    """Return a tact-compatible plan for rotating source ingestion credentials."""
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "source_credential_rotation")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    credentials = _credentials(
        hints.get("credential_health")
        or hints.get("credentials")
        or hints.get("source_credentials")
        or hints.get("sources")
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Source Credential Rotation Plan",
        "summary": source_summary(
            ctx,
            credential_count=len(credentials),
            urgent_count=sum(1 for item in credentials if item["status"] in {"expired", "expiring", "missing"}),
        ),
        "steps": [_rotation_step(index, item, evidence_ids) for index, item in enumerate(credentials, start=1)],
        "validation": _validation(credentials, evidence_ids),
        "risks": _risks(credentials, evidence_ids),
        "acceptance_criteria": _acceptance(evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _credentials(value: Any) -> list[dict[str, Any]]:
    fallback = [
        {
            "source_name": "primary ingestion source",
            "credential_id": "source-credential",
            "owner": "source_owner",
            "status": "missing",
            "severity": "high",
        }
    ]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(unique_records(named(value, ("source_name", "source", "credential_id", "secret_id", "key_id")), fallback), start=1):
        source_name = (
            compact(item.get("source_name"))
            or compact(item.get("source"))
            or compact(item.get("adapter"))
            or compact(item.get("name"))
            or f"source {index}"
        )
        credential_id = (
            compact(item.get("credential_id"))
            or compact(item.get("secret_id"))
            or compact(item.get("key_id"))
            or compact(item.get("id"))
            or f"credential-{index}"
        )
        status = _status(item)
        rows.append(
            {
                "source_name": source_name,
                "credential_id": credential_id,
                "name": f"{source_name} credential {credential_id}",
                "owner": compact(item.get("owner")) or compact(item.get("source_owner")) or "source_owner",
                "status": status,
                "severity": compact(item.get("severity")) or _severity(status),
                "expires_at": compact(item.get("expires_at") or item.get("expiry") or item.get("expiration")),
                "dependent_adapter": compact(item.get("dependent_adapter") or item.get("adapter")),
                "rollback_secret_id": compact(item.get("rollback_secret_id") or item.get("previous_credential_id")),
            }
        )
    return sorted(rows, key=lambda item: (_status_rank(item["status"]), item["source_name"].casefold(), item["credential_id"].casefold()))


def _rotation_step(index: int, item: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    action = "Rotate credential immediately" if item["status"] in {"expired", "missing"} else "Schedule credential rotation"
    if item["status"] == "healthy":
        action = "Verify credential remains healthy and document next rotation window"
    description = (
        f"{action} for source {item['source_name']} using credential {item['credential_id']}; "
        "update secret storage, deploy dependent ingestion adapter, validate reads, then revoke superseded material."
    )
    return row(
        "SCR",
        index,
        item["name"],
        item["owner"],
        description,
        evidence_ids,
        source_name=item["source_name"],
        credential_id=item["credential_id"],
        status=item["status"],
        severity=item["severity"],
        expires_at=item["expires_at"],
        dependent_adapter=item["dependent_adapter"],
        rollback_note=_rollback_note(item),
    )


def _validation(credentials: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    checks = [
        ("source_auth_smoke_test", "Authenticate to each rotated source and fetch a representative ingestion page."),
        ("ingestion_delta_check", "Confirm post-rotation ingestion deltas match source-side record counts."),
        ("old_secret_revocation_check", "Verify expired or replaced credentials no longer authenticate."),
    ]
    if any(item["status"] == "healthy" for item in credentials):
        checks.append(("healthy_credential_review", "Record next rotation date for healthy credentials not changed in this cycle."))
    return [row("SCV", index, name, "source_owner", description, evidence_ids) for index, (name, description) in enumerate(checks, start=1)]


def _risks(credentials: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    risk_rows = [
        ("source_ingestion_outage", "Expired, missing, or revoked credentials can block source ingestion until replacement secrets deploy."),
        ("stale_secret_reuse", "Old source credentials may remain active if revocation is not verified after cutover."),
    ]
    if any(item["status"] == "missing" for item in credentials):
        risk_rows.append(("unknown_credential_owner", "Missing credential metadata requires manual owner confirmation before rotation."))
    return [row("SCK", index, name, "security_owner", description, evidence_ids) for index, (name, description) in enumerate(risk_rows, start=1)]


def _acceptance(evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        row("SCA", 1, "all expired and expiring source credentials rotated", "source_owner", "Every expired, expiring, or missing credential has a replacement, validation evidence, and revocation record.", evidence_ids),
        row("SCA", 2, "traceability preserved", "security_owner", "Each remediation record preserves source name, credential identifier, owner, validation outcome, and rollback note.", evidence_ids),
    ]


def _status(item: dict[str, Any]) -> str:
    text = " ".join(
        compact(item.get(key)).lower()
        for key in ("status", "health", "expiry_status", "rotation_status", "expires_at", "expiry", "expiration")
        if compact(item.get(key))
    )
    if any(term in text for term in ("missing", "unknown", "not found")):
        return "missing"
    if any(term in text for term in ("expired", "overdue", "revoked")):
        return "expired"
    if any(term in text for term in ("expiring", "soon", "near", "30d", "14d", "7d")):
        return "expiring"
    if any(term in text for term in ("healthy", "valid", "ok", "active")):
        return "healthy"
    return "missing"


def _status_rank(status: str) -> int:
    return {"expired": 0, "expiring": 1, "missing": 2, "healthy": 3}.get(status, 4)


def _severity(status: str) -> str:
    return {"expired": "critical", "expiring": "high", "missing": "high", "healthy": "low"}.get(status, "medium")


def _rollback_note(item: dict[str, Any]) -> str:
    if item["rollback_secret_id"]:
        return f"Repoint {item['source_name']} adapter to rollback credential {item['rollback_secret_id']} only before old secret revocation."
    return f"Keep prior {item['source_name']} credential available until validation passes, then revoke it."
