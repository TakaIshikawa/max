"""JSON API renderer for source payload size anomaly status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_payload_size_anomaly_status.v1"
KIND = "max.api.source_payload_size_anomaly_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def source_payload_size_anomaly_status_to_json(payload: Mapping[str, Any], *, warning_ratio: float = 1.5, critical_ratio: float = 2.5) -> str:
    rows = _rows(payload, warning_ratio, critical_ratio)
    anomalous = [row for row in rows if row["status"] != "ok"]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"total_sources": len(rows), "anomalous_sources": len(anomalous), "critical_sources": sum(1 for row in rows if row["status"] == "critical"), "largest_anomaly_source": anomalous[0]["source"] if anomalous else None}, "source_rows": rows, "metadata": source_metadata(payload, source_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], warning: float, critical: float) -> list[dict[str, Any]]:
    source = payload.get("sources") or payload.get("items") or payload
    if isinstance(source, Mapping):
        items = [{**dict(value), "source": value.get("source") or key} for key, value in source.items() if isinstance(value, Mapping)]
    elif isinstance(source, list):
        items = [item for item in source if isinstance(item, Mapping)]
    else:
        items = []
    rows = [_row(item, index, warning, critical) for index, item in enumerate(items, start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -(row["size_ratio"] if row["size_ratio"] is not None else float("inf")), row["source"]))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    latest = max(0, int_or_zero(item.get("latest_payload_bytes", item.get("payload_bytes"))))
    baseline = max(0, int_or_zero(item.get("baseline_payload_bytes", item.get("median_payload_bytes"))))
    ratio = latest / baseline if baseline else (1.0 if latest == 0 else float("inf"))
    status = "critical" if ratio >= critical else "warning" if ratio >= warning else "ok"
    return {"source": _text(item.get("source") or item.get("name")) or f"source-{index}", "latest_payload_bytes": latest, "baseline_payload_bytes": baseline, "size_ratio": None if ratio == float("inf") else round(ratio, 4), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
