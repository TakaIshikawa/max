"""Generate deterministic service account lifecycle governance plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-service-account-lifecycle-plan/v1"
KIND = "max.spec.service_account_lifecycle_plan"
RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
ANCHOR_DATE = "2026-01-01"


def generate_service_account_lifecycle_plan(spec_like: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    rows = _account_rows(spec)
    rotation_actions = [
        {
            "account_id": row["id"],
            "account": row["account"],
            "owner": row["owner"],
            "action": "rotate credential and record evidence" if "rotation-overdue" in row["risk_flags"] else "confirm next rotation window",
            "due_date": row["next_review"],
        }
        for row in rows
        if "rotation-overdue" in row["risk_flags"] or row["risk"] in {"critical", "high"}
    ]
    stale_accounts = [row for row in rows if "stale" in row["risk_flags"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "account_count": len(rows),
            "critical_count": sum(1 for row in rows if row["risk"] == "critical"),
            "high_risk_count": sum(1 for row in rows if row["risk"] in {"critical", "high"}),
            "stale_count": len(stale_accounts),
            "ownerless_count": sum(1 for row in rows if "ownerless" in row["risk_flags"]),
        },
        "account_inventory": rows,
        "rotation_actions": rotation_actions,
        "stale_accounts": stale_accounts,
        "review_cadence": _review_cadence(spec),
    }


def render_service_account_lifecycle_plan_markdown(plan_or_spec: dict[str, Any] | None = None) -> str:
    plan = plan_or_spec if _is_plan(plan_or_spec) else generate_service_account_lifecycle_plan(plan_or_spec)
    lines = ["# Service Account Lifecycle Plan", "", f"Schema version: {plan['schema_version']}", "", "## Inventory", ""]
    for row in plan["account_inventory"]:
        lines.append(f"- {row['id']}: {row['account']} ({row['system']}) owner={row['owner']} risk={row['risk']} flags={', '.join(row['risk_flags']) or 'none'}")
    lines.extend(["", "## Rotation Actions", ""])
    if plan["rotation_actions"]:
        for action in plan["rotation_actions"]:
            lines.append(f"- {action['account_id']}: {action['action']} by {action['owner']} due {action['due_date']}")
    else:
        lines.append("- No rotation actions required.")
    lines.extend(["", "## Stale Accounts", ""])
    if plan["stale_accounts"]:
        for row in plan["stale_accounts"]:
            lines.append(f"- {row['id']}: {row['account']} last used {row['last_used']}")
    else:
        lines.append("- No stale accounts identified.")
    cadence = plan["review_cadence"]
    lines.extend(["", "## Review Cadence", "", f"- Cadence: {cadence['cadence']}", f"- Anchor date: {cadence['anchor_date']}", f"- Reviewer: {cadence['reviewer']}"])
    return "\n".join(lines).rstrip() + "\n"


def _account_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    identity_owner = _text(spec.get("identity_platform_owner")) or _text(_dict(spec.get("metadata")).get("identity_platform_owner")) or "identity_platform_owner"
    for index, raw in enumerate(_raw_accounts(spec), start=1):
        account = _text(raw.get("account") or raw.get("name") or raw.get("service_account")) or f"service-account-{index}"
        owner = _text(raw.get("owner")) or identity_owner
        privileges = _values(raw.get("privileges") or raw.get("roles"), ["standard"])
        last_rotated = _text(raw.get("last_rotated")) or "rotation-date-required"
        last_used = _text(raw.get("last_used")) or "last-used-date-required"
        next_review = _text(raw.get("expiry") or raw.get("next_review") or raw.get("review_due")) or "next identity review"
        flags = set(_values(raw.get("risk_flags"), []))
        if not _text(raw.get("owner")):
            flags.add("ownerless")
        if _is_stale(last_used):
            flags.add("stale")
        if _is_rotation_overdue(last_rotated):
            flags.add("rotation-overdue")
        if any(role.casefold() in {"admin", "administrator", "owner", "root", "wildcard", "*"} for role in privileges):
            flags.add("overprivileged")
        risk = _risk(flags)
        rows.append(
            {
                "id": "",
                "account": account,
                "system": _text(raw.get("system")) or "system-required",
                "owner": owner,
                "privileges": privileges,
                "last_rotated": last_rotated,
                "last_used": last_used,
                "next_review": next_review,
                "risk_flags": sorted(flags),
                "risk": risk,
            }
        )
    if not rows:
        rows.append({"id": "", "account": "service-account-intake", "system": "system-required", "owner": identity_owner, "privileges": ["standard"], "last_rotated": "rotation-date-required", "last_used": "last-used-date-required", "next_review": "next identity review", "risk_flags": ["ownerless", "rotation-overdue", "stale"], "risk": "critical"})
    rows = sorted(rows, key=lambda row: (RISK_ORDER[row["risk"]], row["last_used"], row["last_rotated"], row["account"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["id"] = f"SAL-{index:03d}"
    return rows


def _raw_accounts(spec: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(spec.get("metadata"))
    plan = _dict(metadata.get("service_account_lifecycle") or spec.get("service_account_lifecycle"))
    candidates = plan.get("accounts") or metadata.get("service_accounts") or spec.get("accounts")
    return [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []


def _risk(flags: set[str]) -> str:
    if {"ownerless", "overprivileged"} & flags or len(flags) >= 3:
        return "critical"
    if {"stale", "rotation-overdue"} & flags:
        return "high"
    if flags:
        return "medium"
    return "low"


def _is_stale(value: str) -> bool:
    return value in {"last-used-date-required", "never"} or (len(value) >= 10 and value[:10] < "2025-07-01")


def _is_rotation_overdue(value: str) -> bool:
    return value == "rotation-date-required" or (len(value) >= 10 and value[:10] < "2025-10-01")


def _review_cadence(spec: dict[str, Any]) -> dict[str, str]:
    cadence = _dict(_dict(spec.get("metadata")).get("review_cadence") or spec.get("review_cadence"))
    return {"cadence": _text(cadence.get("cadence")) or "monthly", "anchor_date": _text(cadence.get("anchor_date")) or ANCHOR_DATE, "reviewer": _text(cadence.get("reviewer")) or "identity_platform_owner"}


def _is_plan(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and value.get("kind") == KIND and "account_inventory" in value


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result = [_text(item) for item in values if _text(item)]
    return result or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
