"""Generate signal payload redaction plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base

SCHEMA_VERSION = "max.spec.signal_payload_redaction_plan.v1"
KIND = "max.spec.signal_payload_redaction_plan"


def generate_signal_payload_redaction_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "signal_payload_redaction")
    findings = sorted((_finding(row, i, evidence_ids) for i, row in enumerate(_rows(hints) or _rows(spec), 1)), key=lambda row: (_rank(row["severity"]), row["field"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": {"status": "clean" if not findings else "redaction_required", "finding_count": len(findings), "critical_count": sum(1 for f in findings if f["severity"] == "critical")},
        "field_groups": [{"field": field, "finding_ids": [row["id"] for row in findings if row["field"] == field]} for field in sorted({row["field"] for row in findings})],
        "redaction_actions": findings or [{"id": "SPR0", "field": "none", "severity": "low", "owner": "data_owner", "action": "continue payload sampling for sensitive fields", "evidence_reference_ids": evidence_ids}],
        "owner_assignments": [{"id": "SPO1", "owner": "data_owner", "responsibility": "approve redaction rules and payload backfill", "evidence_reference_ids": evidence_ids}],
        "verification_gates": [{"id": "SPV1", "check": "sampled payloads no longer expose sensitive fields", "evidence_reference_ids": evidence_ids}],
        "evidence_references": ctx["evidence_references"],
    }


def _rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("findings", "fields", "rows"):
        value = source.get(key) if isinstance(source, dict) else None
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _finding(row: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    severity = compact(row.get("severity")).lower() or ("critical" if compact(row.get("field")).lower() in {"ssn", "password", "token", "secret"} else "medium")
    return {"id": f"SPR{index}", "field": compact(row.get("field") or row.get("name")) or f"field-{index}", "severity": severity, "owner": compact(row.get("owner")) or "data_owner", "action": compact(row.get("action")) or "redact field at ingestion and backfill stored payloads", "evidence_reference_ids": evidence_ids}


def _rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)
