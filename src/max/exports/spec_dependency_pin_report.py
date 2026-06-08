"""Spec dependency pin export report."""

from __future__ import annotations

import re
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_dependency_pin_report.v1"
KIND = "max.spec_dependency_pin_report"
_PINNED = re.compile(r"^(==|=)?v?\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9_.-]+)?$")
_RANGE_PREFIXES = ("^", "~", ">=", "<=", ">", "<")
_FLOATING = {"*", "latest", "main", "master", "next", "stable"}


def generate_spec_dependency_pin_report(records: Iterable[dict[str, Any]], *, allow_ranges: bool = False) -> dict[str, Any]:
    rows = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            continue
        spec_id = _text(raw.get("spec_id") or raw.get("id") or raw.get("name")) or f"spec-{index}"
        counts = {"pinned": 0, "ranged": 0, "floating": 0, "missing": 0}
        offenders = []
        for dep in _dependencies(raw):
            name = _text(dep.get("name") or dep.get("dependency") or dep.get("package")) or "unknown-dependency"
            version = _text(dep.get("version") or dep.get("constraint") or dep.get("specifier"))
            kind = _classify(version)
            counts[kind] += 1
            if kind in {"floating", "missing"} or (kind == "ranged" and not allow_ranges):
                offenders.append(name)
        status = "noncompliant" if offenders else "compliant"
        rows.append({"spec_id": spec_id, "dependency_count": sum(counts.values()), "pinned_count": counts["pinned"], "ranged_count": counts["ranged"], "floating_count": counts["floating"], "missing_count": counts["missing"], "offending_dependencies": sorted(set(offenders), key=str.lower), "status": status})
    rows.sort(key=lambda row: (row["status"] != "noncompliant", row["spec_id"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "noncompliant_count": sum(1 for row in rows if row["status"] == "noncompliant"), "compliant_count": sum(1 for row in rows if row["status"] == "compliant"), "allow_ranges": allow_ranges}, "rows": rows}


def _classify(version: str) -> str:
    text = version.strip().lower()
    if not text:
        return "missing"
    if text in _FLOATING:
        return "floating"
    if "," in text or " - " in text or text.startswith(_RANGE_PREFIXES):
        return "ranged"
    return "pinned" if _PINNED.match(text) else "floating"


def _dependencies(raw: dict[str, Any]) -> list[dict[str, Any]]:
    value = raw.get("dependencies") or raw.get("dependency_declarations") or raw.get("deps")
    if isinstance(value, dict):
        return [{"name": key, "version": item} if not isinstance(item, dict) else dict({"name": key}, **item) for key, item in value.items()]
    if isinstance(value, list | tuple | set):
        return [item if isinstance(item, dict) else {"name": item} for item in value]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
