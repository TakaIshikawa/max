"""Ideation input concentration export report."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

SCHEMA_VERSION = "max.ideation_input_concentration_report.v1"
KIND = "max.ideation_input_concentration_report"


def generate_ideation_input_concentration_report(
    units: Iterable[dict[str, Any]],
    *,
    concentration_threshold: float = 0.6,
) -> dict[str, Any]:
    threshold = _float(concentration_threshold)
    rows = []
    for index, unit in enumerate(units, start=1):
        unit_id = _text(unit.get("unit_id") or unit.get("id")) or f"unit-{index}"
        evidence = _evidence(unit)
        source_ratio, source = _dominant(evidence, "source")
        category_ratio, category = _dominant(evidence, "category")
        profile_ratio, profile = _dominant(evidence, "profile")
        concentration_ratio = max(source_ratio, category_ratio, profile_ratio)
        dominant_inputs = []
        if source_ratio == concentration_ratio and source:
            dominant_inputs.append({"type": "source", "value": source, "ratio": source_ratio})
        if category_ratio == concentration_ratio and category:
            dominant_inputs.append({"type": "category", "value": category, "ratio": category_ratio})
        if profile_ratio == concentration_ratio and profile:
            dominant_inputs.append({"type": "profile", "value": profile, "ratio": profile_ratio})
        rows.append(
            {
                "unit_id": unit_id,
                "evidence_count": len(evidence),
                "dominant_source": source,
                "dominant_source_ratio": source_ratio,
                "dominant_category": category,
                "dominant_category_ratio": category_ratio,
                "dominant_profile": profile,
                "dominant_profile_ratio": profile_ratio,
                "concentration_ratio": concentration_ratio,
                "flagged": concentration_ratio >= threshold,
                "dominant_inputs": dominant_inputs,
            }
        )
    rows.sort(key=lambda row: (-row["concentration_ratio"], row["unit_id"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "unit_count": len(rows),
            "flagged_unit_count": sum(1 for row in rows if row["flagged"]),
            "concentration_threshold": threshold,
        },
        "units": rows,
        "flagged_units": [row for row in rows if row["flagged"]],
    }


def _evidence(unit: dict[str, Any]) -> list[dict[str, Any]]:
    raw = unit.get("evidence_chain") or unit.get("evidence") or unit.get("inputs") or unit.get("signals") or []
    if isinstance(raw, dict):
        raw = raw.values()
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return []
    records = []
    for item in raw:
        if isinstance(item, dict):
            records.append(item)
        else:
            records.append({"source": item})
    return records


def _dominant(records: list[dict[str, Any]], field: str) -> tuple[float, str]:
    values = [_text(record.get(field) or record.get(f"{field}_id")) for record in records]
    values = [value for value in values if value]
    if not values:
        return 0.0, ""
    count = Counter(values)
    value, total = sorted(count.items(), key=lambda item: (-item[1], item[0].casefold()))[0]
    return round(total / len(values), 4), value


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
