"""JSON API renderer for profile source coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.profile_source_coverage_status.v1"
KIND = "max.api.profile_source_coverage_status"
STATUS_RANK = {"missing": 0, "underrepresented": 1, "healthy": 2}


def profile_source_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    observed = {_text(item.get("source") or item.get("name")): int_or_zero(item.get("count", item.get("activity_count", 1))) for item in list_of_maps(payload.get("observed_sources") or payload.get("sources"))}
    required = strings(payload.get("required_sources")) or sorted(observed)
    total = sum(observed.values())
    minimum = float(payload.get("minimum_share", 0.1))
    sources = [_source(name, observed.get(name, 0), total, minimum) for name in required]
    sources.sort(key=lambda row: (STATUS_RANK[row["status"]], row["source"]))
    status = "missing_coverage" if any(row["status"] == "missing" for row in sources) else ("low_coverage" if any(row["status"] == "underrepresented" for row in sources) else ("healthy" if sources else "empty_profile"))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "required_source_count": len(required), "observed_source_count": sum(1 for row in sources if row["count"]), "missing_source_count": sum(1 for row in sources if row["status"] == "missing"), "underrepresented_source_count": sum(1 for row in sources if row["status"] == "underrepresented")}, "sources": sources, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _source(name: str, count: int, total: int, minimum: float) -> dict[str, Any]:
    share = round(count / total, 4) if total else 0.0
    status = "missing" if count <= 0 else ("underrepresented" if share < minimum else "healthy")
    return {"source": name, "count": count, "share": share, "minimum_share": minimum, "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
