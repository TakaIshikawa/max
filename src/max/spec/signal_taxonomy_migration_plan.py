"""Generate deterministic signal taxonomy migration plans."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "max.spec.signal_taxonomy_migration_plan.v1"
KIND = "max.spec.signal_taxonomy_migration_plan"


def generate_signal_taxonomy_migration_plan(
    current_taxonomy: Mapping[str, Any],
    target_taxonomy: Mapping[str, Any],
    signals: Iterable[dict[str, Any]],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    current_categories = _names(current_taxonomy.get("categories") or current_taxonomy.get("roles") or current_taxonomy)
    target_categories = _names(target_taxonomy.get("categories") or target_taxonomy.get("roles") or target_taxonomy)
    explicit_mappings = _mappings(target_taxonomy.get("mappings") or target_taxonomy.get("category_mappings") or target_taxonomy.get("role_mappings"))
    mappings = []
    for category in current_categories:
        target = explicit_mappings.get(category.casefold()) or (category if category.casefold() in {item.casefold() for item in target_categories} else "")
        mappings.append({"from": category, "to": target, "mapped": bool(target)})

    counts = Counter(_signal_category(signal) for signal in signals if isinstance(signal, dict))
    counts.pop("", None)
    affected_counts = [
        {"category": category, "signal_count": counts.get(category, 0)}
        for category in sorted(set(current_categories) | set(counts), key=str.casefold)
    ]
    unmapped = [row["from"] for row in mappings if not row["mapped"]]
    mode = "dry_run" if dry_run else "apply"
    label = "Dry-run" if dry_run else "Apply"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "mode": mode,
        "summary": {
            "current_category_count": len(current_categories),
            "target_category_count": len(target_categories),
            "mapping_count": sum(1 for row in mappings if row["mapped"]),
            "unmapped_category_count": len(unmapped),
            "affected_signal_count": sum(row["signal_count"] for row in affected_counts if row["category"] in current_categories),
            "dry_run": dry_run,
        },
        "mappings": sorted(mappings, key=lambda row: row["from"].casefold()),
        "unmapped_categories": [{"category": category, "reason": "No target taxonomy mapping defined."} for category in sorted(unmapped, key=str.casefold)],
        "affected_signal_counts": affected_counts,
        "backfill_steps": [
            {"step": f"{label}: snapshot current signal taxonomy assignments", "dry_run": dry_run},
            {"step": f"{label}: rewrite mapped signal categories in deterministic batches", "dry_run": dry_run},
            {"step": f"{label}: quarantine signals with unmapped categories for owner review", "dry_run": dry_run},
        ],
        "validation_queries": [
            "count signals grouped by category before and after migration",
            "select signals where category is not in target taxonomy",
            "compare mapped category counts against migration snapshot",
        ],
        "rollback": [
            "restore category assignments from the pre-migration snapshot",
            "re-run validation queries and compare counts to the snapshot",
        ],
    }


def _names(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        items = value.keys()
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = []
    names = []
    for item in items:
        if isinstance(item, Mapping):
            name = _text(item.get("name") or item.get("category") or item.get("role") or item.get("id"))
        else:
            name = _text(item)
        if name and name.casefold() not in {existing.casefold() for existing in names}:
            names.append(name)
    return sorted(names, key=str.casefold)


def _mappings(value: Any) -> dict[str, str]:
    mappings: dict[str, str] = {}
    if isinstance(value, Mapping):
        iterable = [{"from": key, "to": target} for key, target in value.items()]
    elif isinstance(value, (list, tuple, set)):
        iterable = value
    else:
        iterable = []
    for item in iterable:
        if not isinstance(item, Mapping):
            continue
        source = _text(item.get("from") or item.get("source") or item.get("current") or item.get("legacy"))
        target = _text(item.get("to") or item.get("target") or item.get("new"))
        if source and target:
            mappings[source.casefold()] = target
    return mappings


def _signal_category(signal: dict[str, Any]) -> str:
    return _text(signal.get("category") or signal.get("role") or signal.get("signal_category") or signal.get("signal_role"))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
