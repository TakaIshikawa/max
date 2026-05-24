"""JSON API renderer for publication payload validation."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.publication_payload_validation.v1"
KIND = "max.api.publication_payload_validation"
STATUS_RANK = {"invalid": 0, "warn": 1, "valid": 2}


def publication_payload_validation_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    payloads = _payloads(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payloads),
        "payloads": payloads,
        "destination_totals": _destination_totals(payloads),
        "schema_error_summaries": _error_summaries(payloads),
        "blocked_payload_ids": [row["payload_id"] for row in payloads if row["blocking_error_count"]],
        "metadata": _metadata(payload, payloads, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _payloads(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("payloads") if isinstance(payload.get("payloads"), list) else payload.get("results")
    rows = [_payload(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["destination"], row["payload_id"]))
    return rows


def _payload(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    errors = _issues(item.get("errors"), blocking_default=True)
    warnings = _issues(item.get("warnings"), blocking_default=False)
    blocking = sum(1 for row in errors if row["blocking"])
    status = "invalid" if blocking else ("warn" if warnings or errors else "valid")
    return {"payload_id": _text(item.get("payload_id") or item.get("id")) or f"payload-{index}", "destination": _bucket(item.get("destination"), "unknown-destination"), "status": status, "errors": errors, "warnings": warnings, "blocking_error_count": blocking}


def _issues(value: Any, *, blocking_default: bool) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if isinstance(item, Mapping):
            code = _bucket(item.get("code") or item.get("error_code"), f"issue-{index}")
            message = _text(item.get("message"))
            blocking = _bool(item.get("blocking", blocking_default))
        else:
            code = _bucket(item, f"issue-{index}")
            message = _text(item)
            blocking = blocking_default
        rows.append({"code": code, "message": message, "blocking": blocking})
    rows.sort(key=lambda row: row["code"])
    return rows


def _summary(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in payloads)
    status = "invalid" if counts["invalid"] else ("warn" if counts["warn"] else "valid")
    return {"status": status, "payload_count": len(payloads), "valid_count": counts["valid"], "warn_count": counts["warn"], "invalid_count": counts["invalid"], "blocked_count": counts["invalid"]}


def _destination_totals(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in payloads:
        grouped[row["destination"]][row["status"]] += 1
    rows = [{"destination": destination, "payload_count": sum(counts.values()), "valid_count": counts["valid"], "warn_count": counts["warn"], "invalid_count": counts["invalid"]} for destination, counts in grouped.items()]
    rows.sort(key=lambda row: row["destination"])
    return rows


def _error_summaries(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in payloads:
        for error in row["errors"]:
            counts[(row["destination"], error["code"])] += 1
    rows = [{"destination": destination, "code": code, "count": count} for (destination, code), count in counts.items()]
    rows.sort(key=lambda row: (row["destination"], row["code"]))
    return rows


def _metadata(payload: Mapping[str, Any], payloads: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "payload_count": len(payloads)}


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
