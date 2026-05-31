"""JSON API renderer for spec evidence citation quality status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.spec_evidence_citation_quality_status.v1"
KIND = "max.api.spec_evidence_citation_quality_status"


def spec_evidence_citation_quality_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(list_of_maps(payload.get("specs") or payload.get("items")), start=1)]
    rows.sort(key=lambda row: (_rank(row["status"]), row["spec_id"]))
    failing = [row for row in rows if row["status"] == "fail"]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "fail" if failing else "warn" if any(row["status"] == "warn" for row in rows) else "pass", "spec_count": len(rows), "failing_spec_count": len(failing), "broken_citation_count": sum(row["broken_citation_count"] for row in rows), "stale_citation_count": sum(row["stale_citation_count"] for row in rows)}, "rows": rows, "failing_specs": failing, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    citation = max(0, int_or_zero(item.get("citation_count")))
    broken = max(0, int_or_zero(item.get("broken_citation_count")))
    stale = max(0, int_or_zero(item.get("stale_citation_count")))
    unsupported = max(0, int_or_zero(item.get("unsupported_claim_count")))
    penalties = broken * 25 + stale * 10 + unsupported * 30 + (25 if citation == 0 else 0)
    score = max(0, 100 - penalties)
    status = "fail" if citation == 0 or broken or unsupported else "warn" if stale or score < 90 else "pass"
    return {"spec_id": str(item.get("spec_id") or item.get("id") or f"spec-{index}"), "citation_count": citation, "broken_citation_count": broken, "stale_citation_count": stale, "unsupported_claim_count": unsupported, "citation_quality_score": score, "status": status, "recommended_action": "repair_citations" if status == "fail" else "refresh_citations" if status == "warn" else "none"}


def _rank(value: str) -> int:
    return {"fail": 0, "warn": 1, "pass": 2}.get(value, 3)
