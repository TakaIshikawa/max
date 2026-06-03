"""JSON API renderer for publication destination latency SLO status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publication_destination_latency_slo_status.v1"
KIND = "max.api.publication_destination_latency_slo_status"


def publication_destination_latency_slo_status_to_json(payload: Mapping[str, Any]) -> str:
    default_slo = max(0.0, float_or_zero(payload.get("slo_ms"))) or 1000.0
    critical_multiplier = _float(payload.get("critical_multiplier"), 2.0)
    destinations = [_destination(row, default_slo, critical_multiplier) for row in _items(payload)]
    destinations.sort(key=lambda row: (_rank(row["status"]), row["destination"]))
    summary = _summary(destinations)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "destinations": destinations, "metadata": source_metadata(payload, destination_count=len(destinations))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("destinations")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _destination(row: Mapping[str, Any], default_slo: float, critical_multiplier: float) -> dict[str, Any]:
    slo = max(0.0, float_or_zero(row.get("slo_ms"))) or default_slo
    p50 = max(0.0, float_or_zero(row.get("p50_ms")))
    p95 = max(0.0, float_or_zero(row.get("p95_ms")))
    p99 = max(0.0, float_or_zero(row.get("p99_ms")))
    samples = max(0, int_or_zero(row.get("sample_count")))
    status = "critical" if samples == 0 or p99 > slo * critical_multiplier else "warning" if p95 > slo or p99 > slo else "ok"
    return {"destination": _bucket(row.get("destination"), "unknown_destination"), "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "slo_ms": slo, "sample_count": samples, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "destination_count": len(rows), "breached_destination_count": critical + warning, "max_p95_ms": max((row["p95_ms"] for row in rows), default=0.0), "max_p99_ms": max((row["p99_ms"] for row in rows), default=0.0)}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
