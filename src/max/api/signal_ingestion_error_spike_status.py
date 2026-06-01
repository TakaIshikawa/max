"""JSON API renderer for signal ingestion error spike status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.signal_ingestion_error_spike_status.v1"
KIND = "max.api.signal_ingestion_error_spike_status"
STATUS_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def signal_ingestion_error_spike_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_ratio"), 2.0)
    critical = _float(payload.get("critical_ratio"), 4.0)
    absolute_warning = max(1, int_or_zero(payload.get("zero_baseline_warning_errors", 3)))
    absolute_critical = max(1, int_or_zero(payload.get("zero_baseline_critical_errors", 10)))
    items = payload.get("sources") or payload.get("rows") or payload.get("ingestion_sources")
    sources = [
        _source(row, index, warning, critical, absolute_warning, absolute_critical)
        for index, row in enumerate(list_of_maps(items), start=1)
    ]
    sources.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["spike_ratio"], -row["errors"], row["source"]))
    spiking = [row for row in sources if row["status"] != "healthy"]
    total_errors = sum(row["errors"] for row in sources)
    total_baseline = sum(row["baseline_errors"] for row in sources)
    worst = spiking[0] if spiking else None
    status = "critical" if any(row["status"] == "critical" for row in sources) else ("warning" if spiking else "healthy")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "status": status,
            "source_count": len(sources),
            "total_errors": total_errors,
            "total_baseline_errors": total_baseline,
            "affected_signal_total": sum(row["affected_signals"] for row in sources),
            "spiking_source_count": len(spiking),
            "worst_source": worst["source"] if worst else None,
        },
        "sources": sources,
        "spiking_sources": spiking,
        "worst_source": worst,
        "recommendation": _recommendation(worst),
        "metadata": source_metadata(payload),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _source(item: Mapping[str, Any], index: int, warning: float, critical: float, absolute_warning: int, absolute_critical: int) -> dict[str, Any]:
    errors = max(0, int_or_zero(item.get("errors", item.get("error_count"))))
    baseline = max(0, int_or_zero(item.get("baseline_errors", item.get("baseline_error_count"))))
    affected = max(0, int_or_zero(item.get("affected_signals", item.get("signal_count"))))
    ratio = round(errors / baseline, 4) if baseline else (float(errors) if errors else 0.0)
    if baseline:
        status = "critical" if ratio >= critical else ("warning" if ratio >= warning else "healthy")
    else:
        status = "critical" if errors >= absolute_critical else ("warning" if errors >= absolute_warning else "healthy")
    return {
        "source": _text(item.get("source") or item.get("adapter") or f"source-{index}"),
        "errors": errors,
        "baseline_errors": baseline,
        "spike_ratio": ratio,
        "affected_signals": affected,
        "status": status,
    }


def _recommendation(worst: Mapping[str, Any] | None) -> str:
    if not worst:
        return "No ingestion error spike detected."
    return f"Inspect {worst['source']} ingestion failures and pause retries if error volume continues."


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else "unknown"

