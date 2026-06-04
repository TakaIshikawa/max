"""JSON API renderer for spec evidence citation density status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.spec_evidence_citation_density_status.v1"
KIND = "max.api.spec_evidence_citation_density_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def spec_evidence_citation_density_status_to_json(payload: Mapping[str, Any], *, warning_citations_per_block: float = 0.5, critical_citations_per_block: float = 0.25) -> str:
    rows = [_row(item, index, warning_citations_per_block, critical_citations_per_block) for index, item in enumerate(_items(payload), start=1)]
    rows = sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["citation_density"], row["spec_id"]))
    weakest = next((row for row in rows if row["status"] != "ok"), None)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"spec_count": len(rows), "under_cited_specs": sum(1 for row in rows if row["status"] != "ok"), "critical_specs": sum(1 for row in rows if row["status"] == "critical"), "lowest_density_spec_id": weakest["spec_id"] if weakest else None}, "spec_rows": rows, "metadata": source_metadata(payload, spec_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("specs") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    blocks = max(0, int_or_zero(item.get("block_count") or item.get("section_count") or len(_list(item.get("blocks")))))
    citations = max(0, int_or_zero(item.get("citation_count") or len(_list(item.get("citations") or item.get("evidence_citations")))))
    density = citations / blocks if blocks else 0.0
    status = "critical" if blocks and density < critical else "warning" if blocks and density < warning else "ok"
    return {"spec_id": _text(item.get("spec_id") or item.get("id") or item.get("unit_id")) or f"spec-{index}", "profile": _text(item.get("profile")) or None, "block_count": blocks, "citation_count": citations, "citation_density": round(density, 4), "status": status}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
