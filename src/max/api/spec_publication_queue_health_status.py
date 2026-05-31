"""JSON API renderer for spec publication queue health."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.spec_publication_queue_health_status.v1"
KIND = "max.api.spec_publication_queue_health_status"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def spec_publication_queue_health_status_to_json(payload: Mapping[str, Any]) -> str:
    targets = _targets(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(targets), "targets": targets, "metadata": source_metadata(payload, target_count=len(targets))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _targets(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    explicit = payload.get("targets")
    if isinstance(explicit, list):
        rows = [_target(item) for item in explicit if isinstance(item, Mapping)]
    else:
        grouped: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"pending": 0, "failed": 0, "retrying": 0, "blocked": 0})
        for item in payload.get("queued_specs") if isinstance(payload.get("queued_specs"), list) else []:
            if not isinstance(item, Mapping):
                continue
            key = (_text(item.get("target_type")) or "unknown", _text(item.get("target_name") or item.get("target")) or "unknown")
            status = _text(item.get("status")).lower()
            bucket = "retrying" if status in {"retry", "retrying"} else status
            if bucket in grouped[key]:
                grouped[key][bucket] += 1
            else:
                grouped[key]["pending"] += 1
        rows = [{"target_type": key[0], "target_name": key[1], **counts} for key, counts in grouped.items()]
    for row in rows:
        row["severity"] = _severity(row)
    return sorted(rows, key=lambda row: (SEVERITY_RANK[row["severity"]], row["target_type"], row["target_name"]))


def _target(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_type": _text(item.get("target_type") or item.get("type")) or "unknown",
        "target_name": _text(item.get("target_name") or item.get("name") or item.get("target")) or "unknown",
        "pending": int_or_zero(item.get("pending")),
        "failed": int_or_zero(item.get("failed")),
        "retrying": int_or_zero(item.get("retrying")),
        "blocked": int_or_zero(item.get("blocked")),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"target_count": len(rows), "pending": sum(row["pending"] for row in rows), "failed": sum(row["failed"] for row in rows), "retrying": sum(row["retrying"] for row in rows), "blocked": sum(row["blocked"] for row in rows), "severity": min((row["severity"] for row in rows), key=lambda value: SEVERITY_RANK[value], default="ok")}


def _severity(row: Mapping[str, Any]) -> str:
    if int_or_zero(row.get("blocked")) > 0 or int_or_zero(row.get("failed")) >= 5:
        return "critical"
    if int_or_zero(row.get("failed")) > 0 or int_or_zero(row.get("retrying")) >= 3:
        return "warn"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
