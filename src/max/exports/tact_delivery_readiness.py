"""Tact delivery readiness report export."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.tact_delivery_readiness.v1"
KIND = "max.tact_delivery_readiness"

REQUIRED_FIELDS = (
    "has_spec",
    "has_acceptance_criteria",
    "has_evidence_trace",
    "has_owner",
    "has_budget",
    "has_risk_notes",
)


class TactDeliveryReadinessInput(TypedDict, total=False):
    idea_id: str
    idea: str
    name: str
    profile: str
    has_spec: bool
    has_acceptance_criteria: bool
    has_evidence_trace: bool
    has_owner: bool
    has_budget: bool
    has_risk_notes: bool
    blocked_reason: str
    priority: str


def build_tact_delivery_readiness_report(
    rows: Iterable[TactDeliveryReadinessInput | dict[str, Any]],
    *,
    title: str = "Tact Delivery Readiness Report",
) -> dict[str, Any]:
    records = _normalize_records(rows)
    ready_items = [record for record in records if record["readiness_status"] == "ready"]
    blocked_items = [record for record in records if record["readiness_status"] == "blocked"]
    ready_items.sort(key=_priority_sort_key)
    blocked_items.sort(key=_priority_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Tact Delivery Readiness Report",
        "summary": {
            "item_count": len(records),
            "ready_count": len(ready_items),
            "blocked_count": len(blocked_items),
            "readiness_rate": round((len(ready_items) / len(records)) * 100, 1) if records else 0.0,
        },
        "missing_field_frequencies": _missing_field_frequencies(blocked_items),
        "ready_items": ready_items,
        "blocked_items": blocked_items,
        "records": records,
    }


def render_tact_delivery_readiness_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Tact Delivery Readiness Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Items: {summary.get('item_count', 0)}",
        f"- Ready: {summary.get('ready_count', 0)}",
        f"- Blocked: {summary.get('blocked_count', 0)}",
        f"- Readiness rate: {summary.get('readiness_rate', 0.0)}%",
        "",
        "## Missing Field Frequencies",
        "",
    ]
    frequencies = report.get("missing_field_frequencies") or []
    if frequencies:
        for row in frequencies:
            lines.append(f"- {row['field']}: {row['count']}")
    else:
        lines.append("- No missing readiness fields were detected.")

    lines.extend(["", "## Ready Items", ""])
    ready_items = report.get("ready_items") or []
    if ready_items:
        for item in ready_items:
            lines.extend(_render_item(item))
    else:
        lines.append("- No tact-ready items were supplied.")

    lines.extend(["", "## Blocked Items", ""])
    blocked_items = report.get("blocked_items") or []
    if blocked_items:
        for item in blocked_items:
            lines.extend(_render_item(item))
    else:
        lines.append("- No blocked tact delivery items were detected.")
    return "\n".join(lines).rstrip() + "\n"


def render_tact_delivery_readiness_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(rows: Iterable[TactDeliveryReadinessInput | dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for index, raw in enumerate(rows):
        idea_id = _text(raw.get("idea_id") or raw.get("idea") or raw.get("name") or f"idea-{index + 1}")
        checks = {field: bool(raw.get(field)) for field in REQUIRED_FIELDS}
        missing_fields = [field for field in REQUIRED_FIELDS if not checks[field]]
        blocked_reason = _text(raw.get("blocked_reason"))
        ready = not blocked_reason and not missing_fields
        records.append(
            {
                "idea_id": idea_id,
                "idea": _text(raw.get("idea") or raw.get("name") or idea_id),
                "profile": _text(raw.get("profile") or "Unassigned profile"),
                "priority": _priority(raw.get("priority")),
                **checks,
                "blocked_reason": blocked_reason,
                "missing_fields": missing_fields,
                "readiness_status": "ready" if ready else "blocked",
            }
        )
    records.sort(key=_priority_sort_key)
    return records


def _missing_field_frequencies(blocked_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for item in blocked_items:
        counts.update(item["missing_fields"])
    rows = [{"field": field, "count": count} for field, count in counts.items()]
    rows.sort(key=lambda row: (-row["count"], row["field"]))
    return rows


def _render_item(item: dict[str, Any]) -> list[str]:
    missing = ", ".join(item["missing_fields"]) if item["missing_fields"] else "None"
    return [
        f"### {item['idea_id']} - {item['idea']}",
        "",
        f"- Profile: {item['profile']}",
        f"- Priority: {item['priority']}",
        f"- Status: {item['readiness_status']}",
        f"- Missing fields: {missing}",
        f"- Blocked reason: {item['blocked_reason'] or 'None'}",
        "",
    ]


_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "normal": 3, "low": 4, "unspecified": 5}


def _priority_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    return (_PRIORITY_ORDER.get(row["priority"], _PRIORITY_ORDER["unspecified"]), row["idea_id"].lower(), row["idea"].lower())


def _priority(value: Any) -> str:
    priority = _text(value).lower().replace(" ", "_")
    return priority if priority in _PRIORITY_ORDER else "unspecified"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
