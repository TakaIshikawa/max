"""Generate deterministic source adapter credential expiry plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.source_adapter_credential_expiry_plan.v1"
KIND = "max.spec.source_adapter_credential_expiry_plan"


def generate_source_adapter_credential_expiry_plan(credentials: Any, *, as_of: str | None = None) -> dict[str, Any]:
    ctx = context({})
    now = _parse_datetime(as_of) or datetime.now(timezone.utc)
    rows = _credentials(credentials, now)
    actions = _actions(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, credential_count=len(rows), high_risk_count=sum(1 for row in rows if row["severity"] == "high"), as_of=now.isoformat()),
        "affected_adapters": rows,
        "rotation_actions": actions,
        "validation_checks": _validation_checks(actions),
        "verification_gates": _verification_gates(),
        "evidence_references": ctx["evidence_references"],
    }


def _credentials(value: Any, now: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        expires_at = _parse_datetime(item.get("expires_at") or item.get("expiry"))
        days = (expires_at - now).days if expires_at else None
        severity = _severity(days, compact(item.get("risk")))
        rows.append({
            "id": compact(item.get("credential_id") or item.get("id")) or f"credential_{index}",
            "adapter": compact(item.get("adapter") or item.get("source_adapter")) or f"adapter_{index}",
            "owner": compact(item.get("owner")) or "source_owner",
            "credential_type": compact(item.get("credential_type") or item.get("type")) or "api_key",
            "expires_at": expires_at.isoformat() if expires_at else "",
            "days_until_expiry": days,
            "severity": severity,
        })
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(rows, key=lambda row: (order[row["severity"]], row["days_until_expiry"] if row["days_until_expiry"] is not None else 999999, row["adapter"].casefold(), row["id"].casefold()))


def _severity(days: int | None, risk: str) -> str:
    if risk.casefold() in {"high", "critical"}:
        return "high"
    if days is None:
        return "medium"
    if days <= 7:
        return "high"
    if days <= 30:
        return "medium"
    return "low"


def _actions(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not rows:
        return [{"id": "SCA1", "type": "no_action", "action": "No expiring source adapter credentials were provided; keep routine credential inventory monitoring active."}]
    return [{"id": f"SCA{index}", "credential_id": row["id"], "adapter": row["adapter"], "owner": row["owner"], "severity": row["severity"], "action": "Rotate credential before expiry and verify adapter ingestion succeeds." if row["severity"] == "high" else "Schedule credential renewal and document owner confirmation."} for index, row in enumerate(rows, start=1)]


def _validation_checks(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"SCV{index}", "action_id": action["id"], "check": "Run adapter authentication smoke test after credential update."} for index, action in enumerate(actions, start=1)]


def _verification_gates() -> list[dict[str, str]]:
    return [
        {"id": "SCG1", "name": "no_high_risk_expiry", "description": "No high-risk credential remains within the rotation window."},
        {"id": "SCG2", "name": "owner_confirmation", "description": "Every affected adapter has owner confirmation for renewal or rotation."},
    ]


def _parse_datetime(value: Any) -> datetime | None:
    text = compact(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
