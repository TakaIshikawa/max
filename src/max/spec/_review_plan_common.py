"""Small deterministic helpers for review-plan spec modules."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


def base(spec_like: Any, metadata_key: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    return spec, ctx, hints(spec, metadata_key), evidence_ids(ctx)


def hints(spec: dict[str, Any], metadata_key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get(metadata_key)
    return value if isinstance(value, dict) else {}


def source_summary(ctx: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return summary(ctx, **extra)


def evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]


def ordered(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(item for item in values if item), key=str.casefold)


def values(value: Any, fallback: list[str]) -> list[str]:
    items: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                items.append(compact(item.get("name") or item.get("title") or item.get("id") or item.get("description")))
            else:
                items.append(compact(item))
    elif isinstance(value, dict):
        items.append(compact(value.get("name") or value.get("title") or value.get("id") or value.get("description")))
    else:
        items.extend(string_list(value))
    return ordered(items) or fallback


def records(value: Any, fallback: list[Any]) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else ([value] if value else fallback)
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            name = compact(item.get("name") or item.get("title") or item.get("id") or item.get("description"))
            record = {key: item[key] for key in sorted(item) if item[key] not in (None, "")}
            record["name"] = name or "unnamed item"
        else:
            record = {"name": compact(item) or "unnamed item"}
        result.append(record)
    return sorted(result, key=lambda item: (rank(item.get("severity")), due_rank(item), compact(item.get("name")).casefold()))


def rank(value: Any) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3}.get(compact(value).lower(), 4)


def due_rank(item: dict[str, Any]) -> int:
    text = " ".join(compact(item.get(key)).lower() for key in ("status", "expiration", "expiry", "due", "deadline"))
    if any(term in text for term in ("expired", "overdue", "past due")):
        return 0
    if any(term in text for term in ("missing", "unknown", "tbd")):
        return 1
    return 2


def truthy(value: Any) -> bool:
    return value is True or compact(value).lower() in {"1", "true", "yes", "y", "required", "blocked", "missing", "expired"}


def row(prefix: str, index: int, name: str, owner: str, description: str, evidence_reference_ids: list[str], **extra: Any) -> dict[str, Any]:
    data = {
        "id": f"{prefix}{index}",
        "name": name,
        "owner": owner,
        "description": description,
        "evidence_reference_ids": evidence_reference_ids,
    }
    data.update({key: value for key, value in extra.items() if value not in (None, "")})
    return data
