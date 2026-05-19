"""Generate deterministic data retention exception plans."""

from __future__ import annotations

from datetime import date
from typing import Any

from max.spec._planning_common import compact, evidence_references, markdown_header, string_list


SCHEMA_VERSION = "max-data-retention-exception-plan/v1"
KIND = "max.data_retention_exception_plan"


def generate_data_retention_exception_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable retention exception inventory and review guidance."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    exceptions = _exceptions(spec.get("exceptions") or spec.get("exception_requests"))
    pending = [item for item in exceptions if item["approval_status"] == "pending"]
    expiring = [item for item in exceptions if item["expiry_risk"] in {"expired", "expiring"}]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _title(spec),
            "exception_count": len(exceptions),
            "pending_approval_count": len(pending),
            "expiry_risk_count": len(expiring),
            "review_cadence": _first(spec.get("review_cadence"), "monthly"),
        },
        "exception_inventory": exceptions,
        "pending_approvals": pending,
        "expiring_exceptions": expiring,
        "compensating_controls": _controls(spec, exceptions),
        "review_actions": _review_actions(spec, exceptions),
        "audit_evidence": evidence_references(spec),
    }


def render_data_retention_exception_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a retention exception plan as deterministic Markdown."""
    lines = markdown_header(plan, "Data Retention Exception Plan")
    _extend(lines, "Exception Inventory", plan.get("exception_inventory") or [], _render_exception)
    _extend(lines, "Pending Approvals", plan.get("pending_approvals") or [], _render_exception)
    _extend(lines, "Expiring Exceptions", plan.get("expiring_exceptions") or [], _render_exception)
    _extend(lines, "Compensating Controls", plan.get("compensating_controls") or [], _render_control)
    _extend(lines, "Review Actions", plan.get("review_actions") or [], _render_action)
    _extend(lines, "Audit Evidence", plan.get("audit_evidence") or [], _render_evidence)
    return "\n".join(lines).rstrip() + "\n"


def _exceptions(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, row in enumerate(value if isinstance(value, list) else [], start=1):
        item = row if isinstance(row, dict) else {"request": row}
        status = _status(item.get("approval_status") or item.get("status"))
        expiry = _first(item.get("expiry_date"), item.get("expires_at"), "Unknown")
        result.append(
            {
                "id": f"EXC{index}",
                "request": _first(item.get("request"), item.get("name"), f"exception_{index}"),
                "data_class": _first(item.get("data_class"), item.get("data_category"), "Unknown"),
                "legal_basis": _first(item.get("legal_basis"), "Unknown"),
                "expiry_date": expiry,
                "expiry_risk": _expiry_risk(expiry),
                "approval_status": status,
                "approvers": _items(item.get("approvers")),
                "owner": _first(item.get("owner"), "privacy_owner"),
            }
        )
    return sorted(result, key=lambda item: (_risk_rank(item["expiry_risk"]), _status_rank(item["approval_status"]), item["expiry_date"], item["request"].casefold()))


def _controls(spec: dict[str, Any], exceptions: list[dict[str, Any]]) -> list[dict[str, str]]:
    values = _items(spec.get("compensating_controls"))
    if not values and exceptions:
        values = ["access review before renewal", "delete or re-approve by expiry", "record legal basis in audit log"]
    return [{"id": f"CTRL{index}", "control": value} for index, value in enumerate(values, start=1)]


def _review_actions(spec: dict[str, Any], exceptions: list[dict[str, Any]]) -> list[dict[str, str]]:
    cadence = _first(spec.get("review_cadence"), "monthly")
    actions = [f"Review all exceptions {cadence}."]
    if any(item["approval_status"] == "pending" for item in exceptions):
        actions.append("Route pending approvals to named approvers before data retention extends.")
    if any(item["expiry_risk"] == "expired" for item in exceptions):
        actions.append("Escalate expired exceptions for deletion or emergency re-approval.")
    if any(item["expiry_risk"] == "expiring" for item in exceptions):
        actions.append("Renew or close exceptions expiring within 30 days.")
    return [{"id": f"REV{index}", "action": value} for index, value in enumerate(actions, start=1)]


def _render_exception(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['request']}",
        "",
        f"- Data class: {item['data_class']}",
        f"- Legal basis: {item['legal_basis']}",
        f"- Expiry date: {item['expiry_date']}",
        f"- Expiry risk: {item['expiry_risk']}",
        f"- Approval status: {item['approval_status']}",
        f"- Approvers: {', '.join(item['approvers']) if item['approvers'] else 'none'}",
        f"- Owner: {item['owner']}",
    ]


def _render_control(item: dict[str, str]) -> list[str]:
    return [f"### {item['id']}", "", f"- Control: {item['control']}"]


def _render_action(item: dict[str, str]) -> list[str]:
    return [f"### {item['id']}", "", f"- Action: {item['action']}"]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Type: {item['type']}", f"- Reference: {item['reference']}"]


def _extend(lines: list[str], title: str, items: list[Any], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _expiry_risk(value: str) -> str:
    try:
        expiry = date.fromisoformat(value)
    except ValueError:
        return "unknown"
    today = date.today()
    if expiry < today:
        return "expired"
    if (expiry - today).days <= 30:
        return "expiring"
    return "active"


def _status(value: Any) -> str:
    label = compact(value).lower()
    return label if label in {"approved", "pending", "rejected"} else "pending"


def _risk_rank(value: str) -> int:
    return {"expired": 0, "expiring": 1, "unknown": 2, "active": 3}.get(value, 4)


def _status_rank(value: str) -> int:
    return {"pending": 0, "rejected": 1, "approved": 2}.get(value, 3)


def _title(spec: dict[str, Any]) -> str:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return _first(project.get("title"), spec.get("title"), "Retention Exceptions")


def _items(value: Any) -> list[str]:
    return sorted(dict.fromkeys(string_list(value)), key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        result = compact(value)
        if result:
            return result
    return "Unknown"
