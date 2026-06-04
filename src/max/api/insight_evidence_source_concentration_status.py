"""JSON API renderer for insight evidence source concentration status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.insight_evidence_source_concentration_status.v1"
KIND = "max.api.insight_evidence_source_concentration_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def insight_evidence_source_concentration_status_to_json(payload: Mapping[str, Any], *, warning_share: float = 0.7, critical_share: float = 0.9) -> str:
    rows = [_row(item, index, warning_share, critical_share) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["top_source_share"], row["insight_id"]))
    most = max(rows, key=lambda row: (row["top_source_share"], row["insight_id"]), default=None)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_insights": len(rows), "concentrated_insights": sum(1 for row in rows if row["status"] != "ok"), "critical_insights": sum(1 for row in rows if row["status"] == "critical"), "most_concentrated_insight_id": most["insight_id"] if most else None}, "insight_rows": rows, "metadata": source_metadata(payload, insight_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("insights") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    counts = _counts(item.get("source_counts") or item.get("evidence_sources"))
    total = sum(counts.values())
    top_source, top_count = max(counts.items(), key=lambda pair: (pair[1], pair[0]), default=(None, 0))
    share = top_count / total if total else 0.0
    status = "critical" if share >= critical and total else "warning" if share >= warning and total else "ok"
    return {"insight_id": _text(item.get("insight_id") or item.get("id")) or f"insight-{index}", "profile": _text(item.get("profile")) or None, "source_counts": counts, "evidence_count": total, "top_source": top_source, "top_source_share": round(share, 4), "status": status}


def _counts(value: Any) -> dict[str, int]:
    if isinstance(value, Mapping):
        return {(_text(key) or "unknown"): max(0, int_or_zero(count)) for key, count in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list):
        counts: dict[str, int] = {}
        for item in value:
            if isinstance(item, Mapping):
                source = _text(item.get("source") or item.get("source_id") or item.get("name")) or "unknown"
                count = max(0, int_or_zero(item.get("count", 1)))
            else:
                source = _text(item) or "unknown"
                count = 1
            counts[source] = counts.get(source, 0) + count
        return dict(sorted(counts.items()))
    return {}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
