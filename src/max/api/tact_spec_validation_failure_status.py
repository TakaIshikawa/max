"""JSON API renderer for Tact spec validation failure status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.tact_spec_validation_failure_status.v1"
KIND = "max.api.tact_spec_validation_failure_status"
SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


def tact_spec_validation_failure_status_to_json(payload: Mapping[str, Any]) -> str:
    failures = [_failure(item, index) for index, item in enumerate(list_of_maps(payload.get("failures") or payload.get("issues")), start=1)]
    failures.sort(key=lambda row: (not row["blocking"], SEVERITY_RANK.get(row["severity"], 3), row["template"], row["field_path"]))
    blocking = sum(1 for row in failures if row["blocking"])
    warnings = sum(1 for row in failures if not row["blocking"])
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if blocking else ("warning" if warnings else "healthy"), "failure_count": len(failures), "blocking_failure_count": blocking, "nonblocking_warning_count": warnings}, "failures": failures, "field_paths": _field_paths(failures), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _failure(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    severity = _text(item.get("severity")) or "error"
    blocking = bool(item.get("blocking", severity == "error"))
    return {"id": _text(item.get("id")) or f"failure-{index}", "template": _text(item.get("template")) or "unknown_template", "field_path": _text(item.get("field_path") or item.get("path")) or "$", "severity": severity, "blocking": blocking, "message": _text(item.get("message"))}


def _field_paths(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["field_path"] for row in failures)
    return [{"field_path": path, "occurrence_count": counts[path]} for path in sorted(counts)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
