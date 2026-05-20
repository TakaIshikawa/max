"""Procurement approval readiness packet export."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.procurement_approval_packet.v1"
KIND = "max.procurement_approval_packet"

ApprovalStatus = Literal["blocked", "pending", "ready"]
GroupBy = Literal["status", "owner", "department"]


class ProcurementApprovalInput(TypedDict, total=False):
    request: str
    vendor: str
    department: str
    status: str
    required_artifacts: str | list[str]
    missing_artifacts: str | list[str]
    blockers: str | list[str]
    owner: str
    deadline: str


def build_procurement_approval_packet(
    records: Iterable[ProcurementApprovalInput | dict[str, Any]],
    *,
    title: str = "Procurement Approval Packet",
    group_by: GroupBy = "status",
    as_of: str = "2026-05-20",
) -> dict[str, Any]:
    items = _normalize_items(records, as_of=as_of)
    groups = _groups(items, group_by)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Procurement Approval Packet",
        "group_by": group_by,
        "as_of": as_of,
        "summary": _summary(items, groups),
        "groups": groups,
        "items": items,
    }


def render_procurement_approval_packet_markdown(packet: dict[str, Any]) -> str:
    summary = packet.get("summary", {})
    lines = [
        f"# {packet.get('title') or 'Procurement Approval Packet'}",
        "",
        f"Schema: `{packet.get('schema_version', SCHEMA_VERSION)}`",
        f"As of: {packet.get('as_of') or 'Unspecified'}",
        "",
        "## Summary",
        "",
        f"- Ready items: {summary.get('ready_count', 0)}",
        f"- Blocked items: {summary.get('blocked_count', 0)}",
        f"- Pending items: {summary.get('pending_count', 0)}",
        f"- Overdue owner actions: {summary.get('overdue_count', 0)}",
        f"- Missing documents: {summary.get('missing_document_count', 0)}",
        "",
        "## Approval Register",
        "",
    ]
    groups = packet.get("groups") or []
    if groups:
        for group in groups:
            lines.extend([f"### {group['name']}", ""])
            for item in group["items"]:
                lines.extend(
                    [
                        f"#### {item['request']}",
                        f"- Vendor: {item['vendor']}",
                        f"- Department: {item['department']}",
                        f"- Status: {item['status']}",
                        f"- Required artifacts: {', '.join(item['required_artifacts']) or 'None supplied'}",
                        f"- Missing artifacts: {', '.join(item['missing_artifacts']) or 'None'}",
                        f"- Blockers: {', '.join(item['blockers']) or 'None'}",
                        f"- Owner: {item['owner']}",
                        f"- Deadline: {item['deadline'] or 'Unscheduled'}",
                        f"- Overdue: {'yes' if item['overdue'] else 'no'}",
                        "",
                    ]
                )
    else:
        lines.append("- No procurement approval items were supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_procurement_approval_packet_json(packet: dict[str, Any]) -> str:
    return json.dumps(packet, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_items(records: Iterable[ProcurementApprovalInput | dict[str, Any]], *, as_of: str) -> list[dict[str, Any]]:
    as_of_date = _parse_date(as_of)
    items = []
    for raw in records:
        required = _items(raw.get("required_artifacts"))
        missing = _items(raw.get("missing_artifacts"))
        blockers = _items(raw.get("blockers"))
        deadline = _text(raw.get("deadline"))
        overdue = bool(deadline and _parse_date(deadline) < as_of_date)
        status = _status(raw.get("status"), missing_artifacts=missing, blockers=blockers, overdue=overdue)
        items.append(
            {
                "request": _text(raw.get("request") or "Untitled procurement request"),
                "vendor": _text(raw.get("vendor") or "Unspecified vendor"),
                "department": _text(raw.get("department") or "Unassigned department"),
                "status": status,
                "required_artifacts": required,
                "missing_artifacts": missing,
                "blockers": blockers,
                "owner": _text(raw.get("owner") or "Unassigned"),
                "deadline": deadline,
                "overdue": overdue,
            }
        )
    items.sort(key=_item_sort_key)
    return items


def _groups(items: list[dict[str, Any]], group_by: GroupBy) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item[group_by]].append(item)
    groups = [{"name": name, "item_count": len(rows), "items": rows} for name, rows in grouped.items()]
    groups.sort(key=lambda group: (_group_worst_key(group["items"]), group["name"].lower()))
    return groups


def _summary(items: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "item_count": len(items),
        "group_count": len(groups),
        "ready_count": sum(1 for item in items if item["status"] == "ready"),
        "blocked_count": sum(1 for item in items if item["status"] == "blocked"),
        "pending_count": sum(1 for item in items if item["status"] == "pending"),
        "overdue_count": sum(1 for item in items if item["overdue"]),
        "missing_document_count": sum(len(item["missing_artifacts"]) for item in items),
    }


_STATUS_ORDER = {"blocked": 0, "pending": 1, "ready": 2}


def _item_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str, str]:
    return (
        _STATUS_ORDER[item["status"]],
        0 if item["blockers"] else 1,
        0 if item["missing_artifacts"] or item["overdue"] else 1,
        item["deadline"] or "9999-12-31",
        item["request"].lower(),
    )


def _group_worst_key(items: list[dict[str, Any]]) -> tuple[int, int, int, str]:
    first = min(items, key=_item_sort_key)
    return (_STATUS_ORDER[first["status"]], 0 if first["blockers"] else 1, 0 if first["missing_artifacts"] or first["overdue"] else 1, first["deadline"] or "9999-12-31")


def _status(value: Any, *, missing_artifacts: list[str], blockers: list[str], overdue: bool) -> ApprovalStatus:
    text = _text(value).lower()
    if text in {"blocked", "rejected", "on hold"} or blockers:
        return "blocked"
    if text in {"ready", "approved", "complete"} and not missing_artifacts and not overdue:
        return "ready"
    if missing_artifacts or overdue:
        return "pending"
    if text == "ready":
        return "ready"
    return "pending"


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return sorted({_text(item) for item in values if _text(item)}, key=str.lower)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.max


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
