"""Publication idempotency collision export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.publication_idempotency_collision_report.v1"
KIND = "max.publication_idempotency_collision_report"


def build_publication_idempotency_collision_report(records: Iterable[dict[str, Any]], *, title: str = "Publication Idempotency Collision Report") -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    attempt_count = 0
    for raw in records:
        attempt_count += 1
        destination = _text(raw.get("destination") or raw.get("channel") or raw.get("target")) or "unknown-destination"
        idempotency_key = _text(raw.get("idempotency_key") or raw.get("dedupe_key") or raw.get("request_key")) or "missing-idempotency-key"
        external_id = _text(raw.get("external_id") or raw.get("publication_id") or raw.get("provider_id"))
        groups[(destination, idempotency_key)].append({"external_id": external_id or "missing-external-id", "attempt_id": _text(raw.get("attempt_id") or raw.get("id"))})

    rows = [_row(destination, idempotency_key, attempts) for (destination, idempotency_key), attempts in groups.items()]
    rows.sort(key=lambda row: (_status_rank(row["collision_status"]), row["destination"].lower(), row["idempotency_key"].lower()))
    collision_rows = [row for row in rows if row["collision_status"] == "collision"]
    duplicate_rows = [row for row in rows if row["collision_status"] == "duplicate"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Publication Idempotency Collision Report",
        "summary": {
            "attempt_count": attempt_count,
            "idempotency_group_count": len(rows),
            "collision_group_count": len(collision_rows),
            "duplicate_group_count": len(duplicate_rows),
            "affected_destination_count": len({row["destination"] for row in collision_rows}),
        },
        "rows": rows,
        "collision_recommendations": [
            {"destination": row["destination"], "idempotency_key": row["idempotency_key"], "recommended_action": row["recommended_action"]}
            for row in collision_rows
        ],
    }


def render_publication_idempotency_collision_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_publication_idempotency_collision_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Publication Idempotency Collision Report'}",
        "",
        "## Summary",
        "",
        f"- Publication attempts: {summary.get('attempt_count', 0)}",
        f"- Idempotency groups: {summary.get('idempotency_group_count', 0)}",
        f"- Collision groups: {summary.get('collision_group_count', 0)}",
        f"- Duplicate groups: {summary.get('duplicate_group_count', 0)}",
        "",
        "## Collision Recommendations",
        "",
    ]
    recommendations = report.get("collision_recommendations") or []
    if not recommendations:
        lines.append("- No idempotency collisions detected.")
    else:
        for row in recommendations:
            lines.append(f"- {row['destination']} {row['idempotency_key']}: {row['recommended_action']}")
    return "\n".join(lines).rstrip() + "\n"


def _row(destination: str, idempotency_key: str, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    external_ids = sorted({attempt["external_id"] for attempt in attempts})
    duplicate_external_ids = sorted(external_id for external_id in external_ids if sum(1 for attempt in attempts if attempt["external_id"] == external_id) > 1)
    collision = len(external_ids) > 1
    duplicate = not collision and len(attempts) > 1
    return {
        "destination": destination,
        "idempotency_key": idempotency_key,
        "attempt_count": len(attempts),
        "external_ids": external_ids,
        "duplicate_external_ids": duplicate_external_ids,
        "collision_status": "collision" if collision else "duplicate" if duplicate else "unique",
        "recommended_action": "Quarantine duplicate publications and reconcile external records before retrying."
        if collision
        else "Confirm retry idempotency behavior and keep the surviving external record."
        if duplicate
        else "No action required.",
    }


def _status_rank(value: str) -> int:
    return {"collision": 0, "duplicate": 1, "unique": 2}.get(value, 3)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
