"""Generate source adapter token rotation plans."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from max.spec._planning_common import compact, context, summary

SCHEMA_VERSION = "max.spec.source_adapter_token_rotation_plan.v1"
KIND = "max.spec.source_adapter_token_rotation_plan"


def generate_source_adapter_token_rotation_plan(spec_like: Any, *, as_of: str | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    now = _parse(as_of) or datetime.now(timezone.utc)
    inventory = _inventory(spec.get("adapters") or spec.get("tokens") or spec.get("rows"), now)
    issues = [issue for row in inventory for issue in row["validation_issues"]]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "summary": summary(ctx, adapter_count=len(inventory), validation_issue_count=len(issues), risk_level="high" if issues else ctx["risk_level"]), "inventory": inventory, "credential_groups": _groups(inventory), "preflight_checks": [{"id": "PF1", "check": "Confirm token owner and secret path."}], "rotation_steps": [{"id": f"RT{idx}", "adapter": row["adapter"], "owner": row["credential_owner"], "action": "Update secret value and reload adapter credentials."} for idx, row in enumerate(inventory, start=1)], "validation_fetches": [{"id": f"VF{idx}", "adapter": row["adapter"], "action": "Run authenticated validation fetch and compare payload shape."} for idx, row in enumerate(inventory, start=1)], "rollback_steps": [{"id": "RB1", "action": "Restore previous token version from secret history and rerun validation fetches."}], "audit_evidence": [{"id": "AE1", "reference": "secret-manager-version-history"}, *ctx["evidence_references"]], "validation_issues": issues}


def _inventory(value: Any, now: datetime) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        expires = _parse(item.get("token_expires_at") or item.get("expires_at"))
        issues = []
        if not compact(item.get("token_id") or item.get("secret_ref")):
            issues.append("missing_token_metadata")
        if expires and expires <= now:
            issues.append("expired_token")
        rows.append({"adapter": compact(item.get("adapter") or item.get("name")) or f"adapter_{index}", "credential_owner": compact(item.get("credential_owner") or item.get("owner")) or "source_owner", "rotation_window": compact(item.get("rotation_window")) or "standard", "secret_ref": compact(item.get("secret_ref")) or "", "token_expires_at": expires.isoformat() if expires else "", "validation_issues": issues, "risk": "high" if issues else "standard"})
    return sorted(rows, key=lambda row: (row["credential_owner"].casefold(), row["rotation_window"], row["adapter"].casefold()))


def _groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        grouped[(row["credential_owner"], row["rotation_window"])].append(row["adapter"])
    return [{"credential_owner": owner, "rotation_window": window, "adapters": sorted(adapters, key=str.casefold)} for (owner, window), adapters in sorted(grouped.items())]


def _parse(value: Any) -> datetime | None:
    text = compact(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
