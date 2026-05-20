"""Shared normalization helpers for mapping-style design brief plans."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


JsonDict = dict[str, Any]


def text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return " ".join(value.split()) or default
    if isinstance(value, Mapping):
        return json.dumps(dict(value), sort_keys=True, separators=(",", ":")) if value else default
    if isinstance(value, (list, tuple, set)):
        values = [text(item) for item in value]
        return ", ".join(item for item in values if item) or default
    return " ".join(str(value).split()) or default


def list_of_dicts(value: Any) -> list[JsonDict]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, Mapping):
        return [f"{key}={text(value[key])}" for key in sorted(value) if text(value[key])]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [text(item) for item in value if text(item)]
    return [text(value)] if text(value) else []


def section(brief: Mapping[str, Any], name: str) -> JsonDict:
    metadata = brief.get("metadata")
    if isinstance(metadata, Mapping):
        for key in (name, f"design_brief_{name}"):
            value = metadata.get(key)
            if isinstance(value, Mapping):
                return dict(value)
    value = brief.get(name)
    if isinstance(value, Mapping):
        return dict(value)
    return dict(brief)


def first_text(*values: Any, default: str = "") -> str:
    for value in values:
        candidate = text(value)
        if candidate:
            return candidate
    return default


def evidence(value: Any) -> list[str]:
    refs: list[str] = []
    for candidate in list_values(value):
        key = candidate.lower()
        if key not in {item.lower() for item in refs}:
            refs.append(candidate)
    return sorted(refs, key=str.casefold)


def sorted_rows(rows: list[JsonDict], *keys: str) -> list[JsonDict]:
    return sorted(rows, key=lambda row: tuple(text(row.get(key)).casefold() for key in keys))


def row_id(prefix: str, index: int) -> str:
    return f"{prefix}{index}"


def gap(gap_id: str, description: str, severity: str = "high") -> JsonDict:
    return {"id": gap_id, "description": description, "severity": severity}
