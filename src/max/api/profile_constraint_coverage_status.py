"""JSON API renderer for profile constraint coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, source_metadata

SCHEMA_VERSION = "max.api.profile_constraint_coverage_status.v1"
KIND = "max.api.profile_constraint_coverage_status"


def profile_constraint_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "undercovered_profiles": [row for row in rows if row["undercovered"]], "metadata": source_metadata(payload, profile_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["undercovered"], row["coverage_ratio"], row["profile"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    required = _strings(item.get("required_constraints"))
    satisfied = _strings(item.get("satisfied_constraints"))
    explicit_missing = _strings(item.get("missing_constraints"))
    missing = sorted(set(explicit_missing) | (set(required) - set(satisfied)))
    ratio = round(len(set(required) & set(satisfied)) / len(required), 4) if required else 1.0
    return {"profile": _bucket(item.get("profile"), "unknown_profile"), "required_constraints": required, "satisfied_constraints": satisfied, "missing_constraints": missing, "coverage_ratio": ratio, "missing_constraint_count": len(missing), "undercovered": bool(missing)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    undercovered = sum(1 for row in rows if row["undercovered"])
    return {"status": "undercovered" if undercovered else "complete", "profile_count": len(rows), "undercovered_count": undercovered, "required_constraint_count": sum(len(row["required_constraints"]) for row in rows)}


def _strings(value: Any) -> list[str]:
    return sorted({_text(item) for item in as_list(value) if _text(item)})


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
