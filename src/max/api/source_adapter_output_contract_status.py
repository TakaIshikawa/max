"""JSON API renderer for source adapter output contract status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata, strings

SCHEMA_VERSION = "max.api.source_adapter_output_contract_status.v1"
KIND = "max.api.source_adapter_output_contract_status"
SEVERITY_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def source_adapter_output_contract_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    non_compliant = [row for row in rows if row["status"] != "healthy"]
    counts = Counter(row["status"] for row in rows)
    status = "no_data" if not rows else ("critical" if counts["critical"] else ("warning" if counts["warning"] else "healthy"))
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "adapter_count": len(rows),
            "non_compliant_count": len(non_compliant),
            "critical_count": counts["critical"],
            "warning_count": counts["warning"],
            "healthy_count": counts["healthy"],
            "status": status,
        },
        "adapters": rows,
        "non_compliant_adapters": non_compliant,
        "source_metadata": source_metadata(payload),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adapters") or payload.get("contracts") or payload.get("rows")
    expected_version = _text(payload.get("expected_schema_version") or payload.get("schema_version_expected"))
    required = strings(payload.get("required_fields") or ["id", "title", "content", "url", "published_at"])
    rows = [_row(item, index, expected_version, required) for index, item in enumerate(list_of_maps(source), start=1)]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["status"]], row["adapter"].casefold()))
    return rows


def _row(item: Mapping[str, Any], index: int, default_expected: str, default_required: list[str]) -> dict[str, Any]:
    contract = mapping(item.get("contract"))
    required = strings(item.get("required_fields") or contract.get("required_fields") or default_required)
    present = set(strings(item.get("fields") or item.get("output_fields") or item.get("present_fields")))
    explicit_missing = strings(item.get("missing_required_fields") or item.get("missing_fields"))
    missing = sorted(set(explicit_missing) | ({field for field in required if present and field not in present}))
    expected = _text(item.get("expected_schema_version") or contract.get("schema_version") or default_expected) or "unknown"
    observed = _text(item.get("schema_version") or item.get("observed_schema_version") or item.get("output_schema_version")) or "unknown"
    invalid_count = int_or_zero(item.get("invalid_payload_count") or item.get("invalid_count") or item.get("payload_errors"))
    schema_mismatch = expected != "unknown" and observed != "unknown" and expected != observed
    if missing or schema_mismatch:
        status = "critical"
    elif invalid_count:
        status = "warning"
    else:
        status = "healthy"
    return {
        "adapter": _text(item.get("adapter") or item.get("name") or item.get("id")) or f"adapter-{index}",
        "source": _text(item.get("source") or item.get("provider")) or "unknown",
        "expected_schema_version": expected,
        "observed_schema_version": observed,
        "missing_required_fields": missing,
        "schema_version_mismatch": schema_mismatch,
        "invalid_payload_count": invalid_count,
        "sample_count": int_or_zero(item.get("sample_count") or item.get("payload_count")),
        "status": status,
    }


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
