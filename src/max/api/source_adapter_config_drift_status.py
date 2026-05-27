"""JSON API renderer for source adapter config drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import source_metadata

SCHEMA_VERSION = "max.api.source_adapter_config_drift_status.v1"
KIND = "max.api.source_adapter_config_drift_status"


def source_adapter_config_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "drifted_adapters": [row for row in rows if row["drifted"]], "metadata": source_metadata(payload, adapter_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adapters") if isinstance(payload.get("adapters"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["drifted"], row["source"], row["adapter"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    deployed = _text(item.get("deployed_config_hash") or item.get("deployed_hash"))
    expected = _text(item.get("expected_config_hash") or item.get("expected_hash"))
    drifted = bool(deployed and expected and deployed != expected)
    return {"adapter": _bucket(item.get("adapter"), "unknown_adapter"), "source": _bucket(item.get("source"), "unknown_source"), "deployed_config_hash": deployed or None, "expected_config_hash": expected or None, "drifted": drifted, "last_checked_at": _text(item.get("last_checked_at")) or None, "remediation": _text(item.get("remediation")) or ("redeploy adapter config" if drifted else "none")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    drifted = [row for row in rows if row["drifted"]]
    return {"status": "drift_detected" if drifted else "in_sync", "adapter_count": len(rows), "drifted_count": len(drifted), "healthy_count": len(rows) - len(drifted), "sources_affected": sorted({row["source"] for row in drifted})}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
