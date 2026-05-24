"""JSON API renderer for spec dependency risk status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.spec_dependency_risk_status.v1"
KIND = "max.api.spec_dependency_risk_status"
STATUS_RANK = {"blocked": 0, "at_risk": 1, "ready": 2, "optional": 3}


def spec_dependency_risk_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    dependencies = _dependencies(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(dependencies),
        "dependencies": dependencies,
        "blocked_dependencies": [row for row in dependencies if row["status"] == "blocked"],
        "owner_totals": _totals(dependencies, "owner"),
        "spec_totals": _totals(dependencies, "spec_id"),
        "metadata": _metadata(payload, dependencies, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _dependencies(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("dependencies") if isinstance(payload.get("dependencies"), list) else payload.get("spec_dependencies")
    rows = [_dependency(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["spec_id"], row["dependency"]))
    return rows


def _dependency(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    required = _bool(item.get("required", True))
    blockers = _strings(item.get("blockers") or item.get("blocking_issues"))
    health = _health(item.get("health", item.get("status")))
    status = _status(required, health, blockers)
    return {
        "spec_id": _text(item.get("spec_id") or item.get("spec")) or f"spec-{index}",
        "dependency": _text(item.get("dependency") or item.get("name")) or f"dependency-{index}",
        "owner": _text(item.get("owner")) or "unknown-owner",
        "required": required,
        "health": health,
        "blockers": blockers,
        "status": status,
    }


def _status(required: bool, health: str, blockers: list[str]) -> str:
    if not required:
        return "optional"
    if blockers or health in {"blocked", "failed", "unhealthy"}:
        return "blocked"
    if health in {"degraded", "warning", "unknown", "at_risk"}:
        return "at_risk"
    return "ready"


def _summary(dependencies: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in dependencies)
    return {"dependency_count": len(dependencies), "ready_count": counts["ready"], "at_risk_count": counts["at_risk"], "blocked_count": counts["blocked"], "optional_count": counts["optional"]}


def _totals(dependencies: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dependencies:
        grouped[row[field]].append(row)
    return [{field: key, "dependency_count": len(items), "blocked_count": sum(1 for item in items if item["status"] == "blocked")} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], dependencies: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "dependency_count": len(dependencies)}


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return sorted(str(item).strip() for item in values if item not in (None, ""))


def _health(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_")
    return text or "unknown"


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "n", "optional"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
