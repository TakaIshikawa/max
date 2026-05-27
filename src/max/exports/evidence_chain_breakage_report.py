"""Evidence chain breakage export report."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "max.evidence_chain_breakage_report.v1"
KIND = "max.evidence_chain_breakage_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_evidence_chain_breakage_report(
    payload: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    """Validate signal-to-insight-to-buildable-unit-to-spec references."""

    source = payload or {}
    signals = _records(source, "signals")
    insights = _records(source, "insights")
    units = _records(source, "units", "buildable_units")
    specs = _records(source, "specs", "specifications")

    signal_ids = set(signals)
    insight_ids = set(insights)
    unit_ids = set(units)

    broken_links = []
    checked_links = 0
    referenced_signals: set[str] = set()
    referenced_insights: set[str] = set()
    referenced_units: set[str] = set()
    missing_evidence_records = []

    for insight_id, insight in insights.items():
        signal_refs = _ids(insight, "signal_ids", "signals", "evidence_signal_ids", "evidence_signals")
        checked_links += len(signal_refs)
        if not signal_refs:
            missing_evidence_records.append(_missing_evidence("insight", insight_id, "signals"))
        for signal_id in signal_refs:
            referenced_signals.add(signal_id)
            if signal_id not in signal_ids:
                broken_links.append(_broken_link("insight", insight_id, "signal", signal_id))

    for unit_id, unit in units.items():
        insight_refs = _ids(unit, "insight_ids", "insights", "inspiring_insights")
        signal_refs = _ids(unit, "signal_ids", "signals", "evidence_signal_ids", "evidence_signals")
        checked_links += len(insight_refs) + len(signal_refs)
        if not insight_refs and not signal_refs:
            missing_evidence_records.append(_missing_evidence("unit", unit_id, "insights_or_signals"))
        for insight_id in insight_refs:
            referenced_insights.add(insight_id)
            if insight_id not in insight_ids:
                broken_links.append(_broken_link("unit", unit_id, "insight", insight_id))
        for signal_id in signal_refs:
            referenced_signals.add(signal_id)
            if signal_id not in signal_ids:
                broken_links.append(_broken_link("unit", unit_id, "signal", signal_id))

    for spec_id, spec in specs.items():
        unit_refs = _ids(spec, "unit_ids", "units", "buildable_unit_ids", "buildable_units")
        checked_links += len(unit_refs)
        if not unit_refs:
            missing_evidence_records.append(_missing_evidence("spec", spec_id, "units"))
        for unit_id in unit_refs:
            referenced_units.add(unit_id)
            if unit_id not in unit_ids:
                broken_links.append(_broken_link("spec", spec_id, "unit", unit_id))

    orphaned_records = (
        _orphaned("signal", signal_ids - referenced_signals)
        + _orphaned("insight", insight_ids - referenced_insights)
        + _orphaned("unit", unit_ids - referenced_units)
    )
    broken_links.sort(
        key=lambda row: (
            row["record_type"],
            row["record_id"].casefold(),
            row["missing_reference_type"],
            row["missing_reference_id"].casefold(),
        )
    )
    orphaned_records.sort(key=lambda row: (row["record_type"], row["record_id"].casefold()))
    missing_evidence_records.sort(key=lambda row: (row["record_type"], row["record_id"].casefold(), row["missing_evidence"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "metadata": _jsonable(metadata if metadata is not None else source.get("metadata", {})),
        "summary": {
            "signal_count": len(signals),
            "insight_count": len(insights),
            "unit_count": len(units),
            "spec_count": len(specs),
            "checked_link_count": checked_links,
            "broken_link_count": len(broken_links),
            "orphaned_record_count": len(orphaned_records),
            "missing_evidence_count": len(missing_evidence_records),
        },
        "broken_links": broken_links,
        "orphaned_records": orphaned_records,
        "missing_evidence_records": missing_evidence_records,
    }


def render_evidence_chain_breakage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _records(source: Mapping[str, Any], *keys: str) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    raw_items = next((source.get(key) for key in keys if isinstance(source.get(key), list)), [])
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, Mapping):
            continue
        record_id = _text(item.get("id") or item.get(f"{keys[0][:-1]}_id")) or f"{keys[0][:-1]}-{index}"
        rows[record_id] = item
    return dict(sorted(rows.items(), key=lambda item: item[0].casefold()))


def _ids(item: Mapping[str, Any], *keys: str) -> list[str]:
    values = []
    for key in keys:
        values.extend(_list(item.get(key)))
    return sorted({_text(value) for value in values if _text(value)}, key=str.casefold)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _broken_link(record_type: str, record_id: str, missing_reference_type: str, missing_reference_id: str) -> dict[str, str]:
    return {
        "record_type": record_type,
        "record_id": record_id,
        "missing_reference_type": missing_reference_type,
        "missing_reference_id": missing_reference_id,
    }


def _orphaned(record_type: str, record_ids: set[str]) -> list[dict[str, str]]:
    return [{"record_type": record_type, "record_id": record_id} for record_id in record_ids]


def _missing_evidence(record_type: str, record_id: str, missing_evidence: str) -> dict[str, str]:
    return {"record_type": record_type, "record_id": record_id, "missing_evidence": missing_evidence}


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
