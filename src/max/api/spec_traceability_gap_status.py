"""JSON API renderer for spec traceability gap status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, int_or_zero, source_metadata, strings

SCHEMA_VERSION = "max.api.spec_traceability_gap_status.v1"
KIND = "max.api.spec_traceability_gap_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def spec_traceability_gap_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    specs = _specs(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(specs), "specs": specs, "status_totals": _status_totals(specs), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, spec_count=len(specs))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _specs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("specs") if isinstance(payload.get("specs"), list) else payload.get("traceability")
    rows = [_spec(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -len(row["missing_links"]), row["spec_id"]))


def _spec(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    unit_id = _text(item.get("unit_id") or item.get("unit"))
    insight_ids = strings(item.get("insight_ids", item.get("insights")))
    signal_ids = strings(item.get("signal_ids", item.get("signals")))
    missing = set(strings(item.get("missing_links")))
    if not unit_id:
        missing.add("unit_id")
    if not insight_ids:
        missing.add("insight_ids")
    if not signal_ids:
        missing.add("signal_ids")
    depth = max(0, int_or_zero(item.get("evidence_depth", len(insight_ids) + len(signal_ids))))
    status = _status(item.get("status"), sorted(missing), depth)
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "unit_id": unit_id or None, "insight_ids": insight_ids, "signal_ids": signal_ids, "missing_links": sorted(missing), "evidence_depth": depth, "publication_target": _text(item.get("publication_target") or item.get("target")) or None, "status": status}


def _status(value: Any, missing: list[str], depth: int) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if len(missing) >= 3:
        return "critical"
    if missing:
        return "high"
    if depth < 2:
        return "medium"
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "spec_count": len(rows), "gap_count": sum(1 for row in rows if row["missing_links"] or row["status"] != "low"), "critical_gap_count": counts["critical"]}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "spec_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
