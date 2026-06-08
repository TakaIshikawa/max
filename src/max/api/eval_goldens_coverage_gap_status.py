"""JSON API renderer for eval goldens coverage gap status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.eval_goldens_coverage_gap_status.v1"
KIND = "max.api.eval_goldens_coverage_gap_status"
STATUS_RANK = {"missing": 0, "thin": 1, "covered": 2}


def eval_goldens_coverage_gap_status_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]], *, thin_threshold: float = 80.0) -> str:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _items(payload):
        key = (_text(item.get("profile")) or "default", _text(item.get("dimension") or item.get("evaluation_dimension")) or "overall")
        group = groups.setdefault(key, {"profile": key[0], "dimension": key[1], "expected_cases": 0, "covered_cases": 0})
        group["expected_cases"] += max(0, int_or_zero(item.get("expected_cases", item.get("expected"))))
        group["covered_cases"] += max(0, int_or_zero(item.get("covered_cases", item.get("covered"))))
    rows = [_finish_group(group, thin_threshold) for group in groups.values()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["dimension"]))
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, group_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "coverage": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _finish_group(group: dict[str, Any], thin_threshold: float) -> dict[str, Any]:
    expected = group["expected_cases"]
    covered = min(group["covered_cases"], expected) if expected else 0
    missing = max(expected - covered, 0)
    coverage = round((covered / expected) * 100, 2) if expected else 100.0
    status = "missing" if expected and covered == 0 else "thin" if coverage < thin_threshold else "covered"
    return {**group, "covered_cases": covered, "missing_cases": missing, "coverage_percent": coverage, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sum(row["expected_cases"] for row in rows)
    covered = sum(row["covered_cases"] for row in rows)
    return {"status": "missing" if any(row["status"] == "missing" for row in rows) else "thin" if any(row["status"] == "thin" for row in rows) else "covered", "group_count": len(rows), "expected_cases": expected, "covered_cases": covered, "missing_cases": max(expected - covered, 0), "coverage_percent": round((covered / expected) * 100, 2) if expected else 100.0}


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("coverage") or payload.get("goldens") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
