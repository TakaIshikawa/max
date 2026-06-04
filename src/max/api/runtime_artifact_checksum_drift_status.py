"""JSON API renderer for runtime artifact checksum drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.runtime_artifact_checksum_drift_status.v1"
KIND = "max.api.runtime_artifact_checksum_drift_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def runtime_artifact_checksum_drift_status_to_json(payload: Mapping[str, Any], *, oversized_bytes: int = 100_000_000) -> str:
    rows = [_row(item, index, oversized_bytes) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["size_bytes"], row["artifact_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"checked_artifacts": len(rows), "missing_checksums": sum(1 for row in rows if row["observed_checksum"] is None), "checksum_mismatches": sum(1 for row in rows if row["checksum_match"] is False), "critical_artifacts": sum(1 for row in rows if row["status"] == "critical")}, "artifact_rows": rows, "metadata": source_metadata(payload, artifact_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("artifacts") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, oversized: int) -> dict[str, Any]:
    expected = _checksum(item.get("expected_checksum"))
    observed = _checksum(item.get("observed_checksum"))
    size = max(0, int_or_zero(item.get("size_bytes")))
    match = expected == observed if expected and observed else None
    status = "warning" if observed is None else "critical" if match is False else "ok"
    severity = "oversized_mismatch" if status == "critical" and size >= oversized else status
    return {"artifact_id": _text(item.get("artifact_id") or item.get("path")) or f"artifact-{index}", "artifact_type": _text(item.get("artifact_type")) or None, "size_bytes": size, "expected_checksum": expected, "observed_checksum": observed, "checksum_match": match, "status": status, "severity": severity}


def _checksum(value: Any) -> str | None:
    text = _text(value).casefold()
    return text or None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
