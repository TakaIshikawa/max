"""Source adapter auth method coverage export report."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = "max.source_adapter_auth_method_coverage_report.v1"
KIND = "max.source_adapter_auth_method_coverage_report"
KNOWN_METHODS = {"token", "oauth", "none"}


def generate_source_adapter_auth_method_coverage_report(
    records: Iterable[Mapping[str, Any]],
    *,
    required_auth_sources: Iterable[str] | None = None,
    generated_at: str = "2026-06-01T00:00:00+00:00",
    source: str = "source_adapter_auth_methods",
) -> dict[str, Any]:
    required = {_text(name).lower() for name in required_auth_sources or [] if _text(name)}
    rows = [_row(record, index, required) for index, record in enumerate(records, start=1) if isinstance(record, Mapping)]
    rows.sort(key=lambda row: (_method_rank(row["auth_method"]), row["adapter"].lower()))
    counts = Counter(row["auth_method"] for row in rows)
    missing_required = [row for row in rows if row["missing_required_auth"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "source": source,
        "summary": {
            "adapter_count": len(rows),
            "required_auth_count": len(required),
            "missing_required_auth_count": len(missing_required),
        },
        "counts_by_method": {method: counts.get(method, 0) for method in ["token", "oauth", "none", "unknown"]},
        "adapters": rows,
        "missing_required_auth": missing_required,
    }


def render_source_adapter_auth_method_coverage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _row(record: Mapping[str, Any], index: int, required: set[str]) -> dict[str, Any]:
    adapter = _text(record.get("adapter") or record.get("source_adapter") or record.get("source")) or f"adapter-{index}"
    method = _method(record.get("auth_method") or record.get("authentication") or record.get("auth"))
    return {
        "adapter": adapter,
        "source": _text(record.get("source")) or adapter,
        "auth_method": method,
        "owner": _text(record.get("owner")) or "unassigned",
        "required_auth": adapter.lower() in required,
        "missing_required_auth": adapter.lower() in required and method in {"none", "unknown"},
    }


def _method(value: Any) -> str:
    method = _text(value).lower().replace("-", "_")
    return method if method in KNOWN_METHODS else "unknown"


def _method_rank(method: str) -> int:
    return {"unknown": 0, "none": 1, "token": 2, "oauth": 3}.get(method, 4)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
