"""JSON API renderer for LLM prompt version adoption status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.llm_prompt_version_adoption_status.v1"
KIND = "max.api.llm_prompt_version_adoption_status"


def llm_prompt_version_adoption_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_legacy_share"), 0.1)
    critical = _float(payload.get("critical_legacy_share"), 0.25)
    prompts = [_prompt(row, warning, critical) for row in _items(payload)]
    prompts.sort(key=lambda row: (_rank(row["status"]), row["prompt_name"]))
    summary = _summary(prompts)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "prompts": prompts, "metadata": source_metadata(payload, prompt_count=len(prompts))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("prompts")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _prompt(row: Mapping[str, Any], warning: float, critical: float) -> dict[str, Any]:
    latest = str(row.get("latest_version") or row.get("current_version") or "")
    versions = {str(version): max(0, int_or_zero(count)) for version, count in mapping(row.get("observed_versions")).items()}
    request_count = max(0, int_or_zero(row.get("request_count"))) or sum(versions.values())
    legacy = sum(count for version, count in versions.items() if version != latest)
    share = round(legacy / request_count, 4) if request_count else 0.0
    status = "critical" if share >= critical else "warning" if share >= warning else "ok"
    return {"prompt_name": _bucket(row.get("prompt_name") or row.get("name"), "unknown_prompt"), "current_version": row.get("current_version"), "latest_version": latest, "observed_versions": dict(sorted(versions.items())), "request_count": request_count, "legacy_request_count": legacy, "legacy_request_share": share, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    total = sum(row["request_count"] for row in rows)
    legacy = sum(row["legacy_request_count"] for row in rows)
    return {"status": "critical" if critical else "warning" if warning else "ok", "prompt_count": len(rows), "lagging_prompt_count": critical + warning, "legacy_request_count": legacy, "total_request_count": total, "adoption_percentage": round(((total - legacy) / total) * 100, 2) if total else 100.0}


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
