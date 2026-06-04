"""Source adapter config completeness export report."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = "max.source_adapter_config_completeness_report.v1"
KIND = "max.source_adapter_config_completeness_report"


def generate_source_adapter_config_completeness_report(
    adapter_configs: Iterable[Mapping[str, Any]],
    required_keys_by_adapter: Mapping[str, Iterable[str]],
    *,
    generated_at: str = "2026-06-01T00:00:00+00:00",
    source: str = "source_adapter_configs",
) -> dict[str, Any]:
    rows = [
        _adapter_row(record, index, required_keys_by_adapter)
        for index, record in enumerate(adapter_configs, start=1)
        if isinstance(record, Mapping)
    ]
    rows.sort(key=lambda row: (-row["missing_key_count"], row["adapter"].lower()))
    incomplete = [row for row in rows if row["missing_key_count"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "source": source,
        "summary": {
            "adapter_count": len(rows),
            "complete_count": len(rows) - len(incomplete),
            "incomplete_count": len(incomplete),
            "missing_key_count": sum(row["missing_key_count"] for row in rows),
        },
        "adapters": rows,
        "incomplete_adapters": incomplete,
        "missing_key_counts": [
            {"adapter": row["adapter"], "missing_key_count": row["missing_key_count"]}
            for row in rows
            if row["missing_key_count"]
        ],
    }


def render_source_adapter_config_completeness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _adapter_row(
    record: Mapping[str, Any],
    index: int,
    required_keys_by_adapter: Mapping[str, Iterable[str]],
) -> dict[str, Any]:
    adapter = _text(record.get("adapter") or record.get("name") or record.get("source_adapter")) or f"adapter-{index}"
    config = record.get("config") if isinstance(record.get("config"), Mapping) else record
    config_keys = sorted(str(key) for key in config.keys() if key not in {"adapter", "name", "source_adapter"})
    required_keys = [_text(key) for key in required_keys_by_adapter.get(adapter, []) if _text(key)]
    missing_keys = [key for key in required_keys if _missing(config.get(key))]
    return {
        "adapter": adapter,
        "config": dict(config),
        "config_keys": config_keys,
        "required_keys": required_keys,
        "missing_keys": missing_keys,
        "missing_key_count": len(missing_keys),
        "complete": not missing_keys,
    }


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
