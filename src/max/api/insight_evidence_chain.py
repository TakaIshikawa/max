"""JSON API renderer for one insight's evidence chain."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.insight_evidence_chain.v1"
KIND = "max.api.insight_evidence_chain"


def insight_evidence_chain_to_json(payload: Mapping[str, Any], *, as_of: Any | None = None) -> str:
    evidence = _evidence(payload)
    units = _units(payload)
    missing = [row for row in evidence if row["missing_link"]]
    source_counts = Counter(row["source"] for row in evidence)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "insight": _insight(payload),
            "summary": {
                "signal_count": len(evidence),
                "unit_count": len(units),
                "source_count": len(source_counts),
                "missing_signal_count": len(missing),
                "confidence_score": _confidence(payload),
            },
            "evidence_chain": evidence,
            "buildable_units": units,
            "source_breakdown": [{"source": source, "signal_count": count} for source, count in sorted(source_counts.items())],
            "missing_links": missing,
            "confidence_context": {"confidence_score": _confidence(payload), "as_of": as_of},
            "metadata": source_metadata(payload, as_of=as_of),
        },
        indent=2,
        sort_keys=True,
    )


def _insight(payload: Mapping[str, Any]) -> dict[str, Any]:
    insight = mapping(payload.get("insight")) or payload
    return {
        "insight_id": insight.get("insight_id") or insight.get("id"),
        "title": insight.get("title"),
        "profile": insight.get("profile"),
    }


def _evidence(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("signals")
    if not isinstance(source, list):
        source = payload.get("evidence")
    rows = [_evidence_row(item, index) for index, item in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (row["source"], row["signal_id"], row["observed_at"] or ""))


def _evidence_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    signal_id = item.get("signal_id") or item.get("id") or f"signal-{index}"
    source = item.get("source") or item.get("source_adapter") or "unknown-source"
    missing = bool(item.get("missing") or not item.get("url"))
    return {
        "signal_id": signal_id,
        "source": str(source),
        "title": item.get("title"),
        "url": item.get("url"),
        "observed_at": item.get("observed_at") or item.get("published_at") or item.get("created_at"),
        "missing_link": missing,
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _units(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("units")
    if not isinstance(source, list):
        source = payload.get("buildable_units")
    rows = [
        {"unit_id": item.get("unit_id") or item.get("id") or f"unit-{index}", "title": item.get("title") or item.get("name"), "status": item.get("status")}
        for index, item in enumerate(list_of_maps(source), start=1)
    ]
    return sorted(rows, key=lambda row: str(row["unit_id"]))


def _confidence(payload: Mapping[str, Any]) -> float:
    insight = mapping(payload.get("insight")) or payload
    return round(float_or_zero(insight.get("confidence_score") or insight.get("confidence")), 4)
