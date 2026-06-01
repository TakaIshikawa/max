"""JSON API renderer for runtime artifact retention status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.runtime_artifact_retention_status.v1"
KIND = "max.api.runtime_artifact_retention_status"


def runtime_artifact_retention_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_artifact(row, index) for index, row in enumerate(list_of_maps(payload.get("artifacts") or payload.get("rows")), start=1)]
    total = len(rows)
    breaches = [row for row in rows if row["retention_status"] != "retained"]
    breach_rate = round(len(breaches) / total, 4) if total else 0.0
    warning = _float(payload.get("warning_breach_rate"), 0.05)
    critical = _float(payload.get("critical_breach_rate"), 0.2)
    status = "critical" if breach_rate >= critical and breaches else ("degraded" if breach_rate >= warning and breaches else "healthy")
    by_type = _by_type(rows)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"health": status, "status": status, "artifact_count": total, "retained_count": total - len(breaches), "expired_count": sum(1 for row in rows if row["retention_status"] == "expired"), "oversized_count": sum(1 for row in rows if row["retention_status"] == "oversized"), "missing_count": sum(1 for row in rows if row["retention_status"] == "missing"), "breach_count": len(breaches), "breach_rate": breach_rate, "highest_risk_artifact_type": by_type[0]["artifact_type"] if by_type else None}, "artifact_types": by_type, "top_breach_reasons": _top_reasons(breaches), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _artifact(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    state = _text(item.get("retention_status") or item.get("status") or ("retained" if item.get("retained", True) else "expired"))
    if state not in {"retained", "expired", "oversized", "missing"}:
        state = "expired" if state in {"breached", "breach"} else "retained"
    return {"artifact_id": _text(item.get("artifact_id") or item.get("id") or f"artifact-{index}"), "artifact_type": _text(item.get("artifact_type") or item.get("type") or "unknown"), "run_id": _text(item.get("run_id") or "unknown"), "retention_status": state, "breach_reason": _text(item.get("breach_reason") or item.get("reason") or (state if state != "retained" else ""))}


def _by_type(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["artifact_type"]].append(row)
    output = []
    for artifact_type, items in grouped.items():
        breach_count = sum(1 for item in items if item["retention_status"] != "retained")
        output.append({"artifact_type": artifact_type, "artifact_count": len(items), "retained_count": len(items) - breach_count, "expired_count": sum(1 for item in items if item["retention_status"] == "expired"), "oversized_count": sum(1 for item in items if item["retention_status"] == "oversized"), "missing_count": sum(1 for item in items if item["retention_status"] == "missing"), "breach_count": breach_count, "breach_rate": round(breach_count / len(items), 4) if items else 0.0})
    return sorted(output, key=lambda row: (-row["breach_count"], -row["breach_rate"], row["artifact_type"]))


def _top_reasons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["breach_reason"] or row["retention_status"] for row in rows)
    return [{"reason": reason, "count": count} for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

