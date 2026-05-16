"""Generate deterministic data lineage plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, string_list


SCHEMA_VERSION = "max-data-lineage-plan/v1"
KIND = "max.data_lineage_plan"


def generate_data_lineage_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable data lineage plan with gap highlights."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    project = _section(spec, "project")
    data = _section(spec, "data")
    metadata = _section(spec, "metadata")
    datasets = _items(data.get("critical_datasets") or metadata.get("critical_datasets") or spec.get("datasets"))
    transformations = _sorted_unique(data.get("transformations") or metadata.get("transformations"))
    owners = _sorted_unique(data.get("owners") or metadata.get("owners"))
    gaps = _gaps(datasets, transformations, owners)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _first(project.get("title"), spec.get("title"), "Unknown"),
            "critical_dataset_count": len(datasets),
            "gap_count": len(gaps),
        },
        "source_systems": _items(data.get("source_systems") or metadata.get("source_systems")),
        "transformations": transformations or ["Unknown"],
        "storage_destinations": _items(data.get("storage_destinations") or metadata.get("storage_destinations")),
        "ownership": owners or ["Unknown"],
        "retention_references": _items(data.get("retention_references") or metadata.get("retention_references")),
        "downstream_consumers": _items(data.get("downstream_consumers") or metadata.get("downstream_consumers")),
        "audit_checkpoints": _items(data.get("audit_checkpoints") or ["source extract", "transform completion", "destination load"]),
        "gaps": gaps,
        "evidence": _evidence(spec, metadata),
    }


def _gaps(datasets: list[str], transformations: list[str], owners: list[str]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for dataset in datasets:
        if not transformations:
            gaps.append({"dataset": dataset, "gap": "missing transformation"})
        if not owners:
            gaps.append({"dataset": dataset, "gap": "missing owner"})
    return gaps


def _section(spec: dict[str, Any], name: str) -> dict[str, Any]:
    value = spec.get(name)
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[str]:
    return _sorted_unique(value) or ["Unknown"]


def _evidence(spec: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    refs = [item["reference"] for item in evidence_references(spec)]
    refs.extend(string_list(metadata.get("evidence_links")))
    return _sorted_unique(refs)


def _sorted_unique(value: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in string_list(value):
        if item not in seen:
            seen.add(item)
            result.append(item)
    return sorted(result, key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        text = compact(value)
        if text:
            return text
    return "Unknown"
