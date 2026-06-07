"""JSON API renderer for spec citation quality status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.spec_citation_quality_status.v1"
KIND = "max.api.spec_citation_quality_status"


def spec_citation_quality_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = max(1, int_or_zero(payload.get("warning_issue_threshold") or 1))
    critical = max(warning, int_or_zero(payload.get("critical_issue_threshold") or 3))
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (-row["issue_score"], row["spec_id"]))
    total_issues = sum(row["issue_count"] for row in rows)
    status = "critical" if total_issues >= critical else "warning" if total_issues >= warning else "ok"
    worst = rows[0] if rows and rows[0]["issue_count"] else None
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "spec_count": len(rows),
            "missing_citation_count": sum(row["missing_citation_count"] for row in rows),
            "stale_citation_count": sum(row["stale_citation_count"] for row in rows),
            "unsupported_criteria_count": sum(row["unsupported_criteria_count"] for row in rows),
            "worst_spec_id": worst["spec_id"] if worst else None,
            "specs": rows,
            "metadata": source_metadata(payload, spec_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("specs") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    missing = max(0, int_or_zero(item.get("missing_citation_count") or item.get("missing_count")))
    stale = max(0, int_or_zero(item.get("stale_citation_count") or item.get("stale_count")))
    unsupported = max(0, int_or_zero(item.get("unsupported_criteria_count") or item.get("unsupported_count")))
    return {
        "spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}",
        "missing_citation_count": missing,
        "stale_citation_count": stale,
        "unsupported_criteria_count": unsupported,
        "issue_count": missing + stale + unsupported,
        "issue_score": (unsupported * 3) + (missing * 2) + stale,
    }


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
