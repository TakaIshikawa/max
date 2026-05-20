"""JSON API renderer for source ingestion coverage reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.source_ingestion_coverage.v1"
KIND = "max.api.source_ingestion_coverage"
STALE_STATUSES = {"late", "stale", "expired"}


def source_ingestion_coverage_to_json(payload: Mapping[str, Any]) -> str:
    """Render source ingestion coverage data as deterministic API JSON."""
    sources = _coverage_by_source(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "run_summary": _run_summary(payload),
        "coverage_by_source": sources,
        "disabled_sources": _disabled_sources(payload, sources),
        "stale_sources": _stale_sources(payload, sources),
        "signal_counts": _signal_counts(payload, sources),
        "error_counts": _error_counts(payload, sources),
        "metadata": _metadata(payload, sources),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _run_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    run = _mapping(payload.get("run"))
    source = _mapping(payload.get("run_summary"))
    return {
        "run_id": source.get("run_id") or source.get("id") or run.get("id"),
        "status": source.get("status") or run.get("status"),
        "profile": source.get("profile") or run.get("profile"),
        "domain": source.get("domain") or run.get("domain"),
        "started_at": source.get("started_at") or run.get("started_at"),
        "completed_at": source.get("completed_at") or run.get("completed_at"),
    }


def _coverage_by_source(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("sources")
    if not isinstance(source, list):
        source = payload.get("source_coverage")
    if not isinstance(source, list):
        source = payload.get("coverage_by_source")

    rows = [
        _source_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["source_id"] or row["name"] or ""), str(row["name"] or "")))


def _source_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    status = str(item.get("status") or "unknown")
    enabled = _bool_or_default(item.get("enabled"), default=not _bool_or_default(item.get("disabled")))
    stale = _bool_or_default(item.get("stale"), default=status.lower() in STALE_STATUSES)
    errors = _errors(item)
    return {
        "source_id": item.get("source_id") or item.get("id") or f"S{index}",
        "name": item.get("name"),
        "type": item.get("type") or item.get("source_type"),
        "status": status,
        "enabled": enabled,
        "stale": stale,
        "last_ingested_at": item.get("last_ingested_at") or item.get("last_seen_at"),
        "expected_cadence": item.get("expected_cadence") or item.get("cadence"),
        "signal_count": _int_or_zero(item.get("signal_count", item.get("signals_count"))),
        "error_count": _int_or_zero(item.get("error_count", len(errors))),
        "errors": errors,
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _disabled_sources(
    payload: Mapping[str, Any],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    explicit = _list_of_maps(payload.get("disabled_sources"))
    if explicit:
        return sorted(
            [
                {
                    "source_id": item.get("source_id") or item.get("id") or f"D{index}",
                    "name": item.get("name"),
                    "reason": item.get("reason") or item.get("disabled_reason"),
                    "owner": item.get("owner"),
                }
                for index, item in enumerate(explicit, start=1)
            ],
            key=lambda row: (str(row["source_id"] or row["name"] or ""), str(row["name"] or "")),
        )

    return [
        {
            "source_id": row["source_id"],
            "name": row["name"],
            "reason": row["metadata"].get("disabled_reason"),
            "owner": row["metadata"].get("owner"),
        }
        for row in sources
        if not row["enabled"]
    ]


def _stale_sources(
    payload: Mapping[str, Any],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    explicit = _list_of_maps(payload.get("stale_sources"))
    if explicit:
        return sorted(
            [
                {
                    "source_id": item.get("source_id") or item.get("id") or f"L{index}",
                    "name": item.get("name"),
                    "last_ingested_at": item.get("last_ingested_at") or item.get("last_seen_at"),
                    "expected_cadence": item.get("expected_cadence") or item.get("cadence"),
                }
                for index, item in enumerate(explicit, start=1)
            ],
            key=lambda row: (str(row["source_id"] or row["name"] or ""), str(row["name"] or "")),
        )

    return [
        {
            "source_id": row["source_id"],
            "name": row["name"],
            "last_ingested_at": row["last_ingested_at"],
            "expected_cadence": row["expected_cadence"],
        }
        for row in sources
        if row["stale"]
    ]


def _signal_counts(payload: Mapping[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    explicit = _mapping(payload.get("signal_counts"))
    by_source = {
        str(row["source_id"]): _int_or_zero(row.get("signal_count"))
        for row in sources
    }
    return {
        "total": _int_or_zero(explicit.get("total", sum(by_source.values()))),
        "by_source": dict(sorted(by_source.items())),
    }


def _error_counts(payload: Mapping[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    explicit = _mapping(payload.get("error_counts"))
    by_source = {
        str(row["source_id"]): _int_or_zero(row.get("error_count"))
        for row in sources
    }
    return {
        "total": _int_or_zero(explicit.get("total", sum(by_source.values()))),
        "by_source": dict(sorted(by_source.items())),
    }


def _metadata(payload: Mapping[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    disabled_count = sum(1 for row in sources if not row["enabled"])
    stale_count = sum(1 for row in sources if row["stale"])
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version")
        or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "source_count": len(sources),
        "enabled_source_count": len(sources) - disabled_count,
        "disabled_source_count": disabled_count,
        "stale_source_count": stale_count,
    }


def _errors(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    errors = []
    for index, error in enumerate(_as_list(item.get("errors")), start=1):
        if isinstance(error, Mapping):
            errors.append(
                {
                    "id": error.get("id") or f"E{index}",
                    "message": error.get("message") or error.get("error"),
                    "code": error.get("code"),
                    "occurred_at": error.get("occurred_at") or error.get("created_at"),
                }
            )
        else:
            errors.append({"id": f"E{index}", "message": str(error), "code": None, "occurred_at": None})
    return errors


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bool_or_default(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
