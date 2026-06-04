"""JSON API renderer for spec template render latency status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.spec_template_render_latency_status.v1"
KIND = "max.api.spec_template_render_latency_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def spec_template_render_latency_status_to_json(
    payload: Any,
    *,
    warning_p95_ms: float = 1000.0,
    critical_p95_ms: float = 3000.0,
    warning_failure_rate: float = 0.01,
    critical_failure_rate: float = 0.05,
) -> str:
    payload_map = mapping(payload)
    templates = _templates(payload, warning_p95_ms, critical_p95_ms, warning_failure_rate, critical_failure_rate)
    status = _overall_status(templates)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "template_count": len(templates),
                "slow_template_count": sum(1 for row in templates if row["p95_ms"] > warning_p95_ms),
                "failing_template_count": sum(1 for row in templates if row["failure_rate"] > warning_failure_rate),
                "max_p95_ms": max((row["p95_ms"] for row in templates), default=0.0),
                "status": status,
            },
            "templates": templates,
            "metadata": source_metadata(payload_map, template_count=len(templates)),
        },
        indent=2,
        sort_keys=True,
    )


def _templates(payload: Any, warning_p95_ms: float, critical_p95_ms: float, warning_failure_rate: float, critical_failure_rate: float) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("templates") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_template(row, index, warning_p95_ms, critical_p95_ms, warning_failure_rate, critical_failure_rate) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["p95_ms"], row["template"]))


def _template(item: Mapping[str, Any], index: int, warning_p95_ms: float, critical_p95_ms: float, warning_failure_rate: float, critical_failure_rate: float) -> dict[str, Any]:
    render_count = max(0, int_or_zero(item.get("render_count")))
    failure_count = max(0, int_or_zero(item.get("failure_count")))
    failure_rate = round(failure_count / render_count, 4) if render_count else (1.0 if failure_count else 0.0)
    p95 = max(0.0, float_or_zero(item.get("p95_ms")))
    if p95 > critical_p95_ms or failure_rate > critical_failure_rate:
        status = "critical"
    elif p95 > warning_p95_ms or failure_rate > warning_failure_rate:
        status = "warning"
    else:
        status = "ok"
    return {
        "template": _text(item.get("template") or item.get("name")) or f"template-{index}",
        "render_count": render_count,
        "p50_ms": max(0.0, float_or_zero(item.get("p50_ms"))),
        "p95_ms": p95,
        "max_ms": max(0.0, float_or_zero(item.get("max_ms"))),
        "failure_count": failure_count,
        "failure_rate": failure_rate,
        "status": status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
