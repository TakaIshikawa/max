"""JSON API renderer for spec template compatibility status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.spec_template_compatibility_status.v1"
KIND = "max.api.spec_template_compatibility_status"
RANK = {"incompatible": 0, "migration_required": 1, "unknown": 2, "compatible": 3}


def spec_template_compatibility_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    supported = set(strings(payload.get("supported_template_versions") or payload.get("supported_versions")))
    current = _text(payload.get("current_template_version") or payload.get("target_template_version"))
    required_blocks = set(strings(payload.get("required_blocks")))
    rows = [_spec(row, i, supported, current, required_blocks) for i, row in enumerate(list_of_maps(payload.get("specs") or payload.get("generated_specs") or payload.get("items") or payload.get("rows")), start=1)]
    rows = sorted(rows, key=lambda row: (RANK[row["status"]], row["spec_id"].casefold()))
    summary = {name + "_count": sum(1 for row in rows if row["status"] == name) for name in RANK}
    status = "critical" if summary["incompatible_count"] else ("warning" if summary["migration_required_count"] or summary["unknown_count"] else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"spec_count": len(rows), **summary}, "incompatible_specs": [row for row in rows if row["status"] == "incompatible"], "specs": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _spec(item: Mapping[str, Any], index: int, supported: set[str], current: str, required_blocks: set[str]) -> dict[str, Any]:
    version = _text(item.get("template_version") or item.get("version"))
    blocks = set(strings(item.get("blocks") or item.get("present_blocks")))
    missing = sorted(set(strings(item.get("missing_blocks"))) | (required_blocks - blocks if required_blocks else set()))
    unsupported = bool(supported and version and version not in supported)
    migration = bool(current and version and version != current and not unsupported)
    unknown = not version
    incompatible = bool(missing or unsupported)
    status = "incompatible" if incompatible else ("migration_required" if migration or bool(item.get("migration_required")) else ("unknown" if unknown else "compatible"))
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "template_version": version or "unknown", "missing_blocks": missing, "unsupported_template_version": unsupported, "migration_required": status == "migration_required", "status": status, "recommended_action": "add missing required blocks" if missing else ("migrate to supported template version" if unsupported or status == "migration_required" else ("record template version" if unknown else "continue validation"))}


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
