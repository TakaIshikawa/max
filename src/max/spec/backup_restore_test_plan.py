"""Generate deterministic backup restore test plans."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.spec.backup_restore_test_plan.v1"
KIND = "max.spec.backup_restore_test_plan"


def generate_backup_restore_test_plan(system_context: dict[str, Any]) -> dict[str, Any]:
    """Return a stable restore test plan from system and data context."""
    ctx = _context(system_context)
    critical = ctx["criticality"] == "critical"
    rpo = _text(ctx["rpo"]) or ("15 minutes" if critical else "24 hours")
    rto = _text(ctx["rto"]) or ("1 hour" if critical else "8 hours")

    validation_checks = [
        "Confirm restored schema, object counts, and checksums match backup manifest.",
        "Run application smoke tests against restored environment.",
        "Verify audit logs and access controls remain intact after restore.",
    ]
    if critical:
        validation_checks.append("Run business transaction replay before declaring recovery successful.")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "system": ctx["system"],
        "backup_scope": ctx["backup_scope"],
        "recovery_objectives": {"rpo": rpo, "rto": rto},
        "restore_procedure": [
            "Select latest approved backup and record backup identifier.",
            "Provision isolated restore target with production-equivalent configuration.",
            "Restore data, secrets references, and dependent storage in dependency order.",
            "Run validation checks and capture evidence before teardown.",
        ],
        "validation_checks": validation_checks,
        "evidence_capture": [
            "backup identifier and restore start/end timestamps",
            "validation output, screenshots, and command logs",
            "approver sign-off and unresolved findings",
        ],
        "rollback_criteria": [
            "Restore corrupts data or fails integrity checks.",
            "Recovery exceeds RTO target.",
            "Validation exposes access-control or encryption drift.",
        ],
        "owners": ctx["owners"],
        "test_cadence": "monthly" if critical else "quarterly",
    }


def _context(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {
        "system": _text(raw.get("system") or raw.get("system_name")) or "Primary application",
        "criticality": (_text(raw.get("criticality")) or "standard").lower(),
        "backup_scope": _list(raw.get("backup_scope"))
        or _list(raw.get("data_stores"))
        or ["application database", "object storage", "configuration"],
        "rpo": raw.get("rpo"),
        "rto": raw.get("rto"),
        "owners": {
            "service_owner": _text(raw.get("service_owner")) or "Service owner",
            "restore_owner": _text(raw.get("restore_owner")) or "Infrastructure owner",
            "validation_owner": _text(raw.get("validation_owner")) or "Quality owner",
        },
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
