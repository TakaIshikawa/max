"""JSON API renderer for prompt template version drift status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.prompt_template_version_drift_status.v1"
KIND = "max.api.prompt_template_version_drift_status"
STATUS_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def prompt_template_version_drift_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    templates = _templates(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(templates), "templates": templates, "status_totals": _status_totals(templates), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, template_count=len(templates))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _templates(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("templates") if isinstance(payload.get("templates"), list) else payload.get("prompt_templates")
    rows = [_template(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["drift_days"], row["template_id"]))


def _template(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    deployed = _text(item.get("deployed_version"))
    approved = _text(item.get("approved_version"))
    drift_days = max(0, int_or_zero(item.get("drift_days", item.get("age_days"))))
    status = _status(item.get("status"), deployed, approved, drift_days)
    return {"template_id": _text(item.get("template_id") or item.get("id")) or f"template-{index}", "profile": _bucket(item.get("profile"), "default"), "deployed_version": deployed or "unknown", "approved_version": approved or None, "drift_days": drift_days, "owner": _text(item.get("owner")) or "unassigned", "status": status}


def _status(value: Any, deployed: str, approved: str, drift_days: int) -> str:
    explicit = _bucket(value, "")
    if explicit in STATUS_RANK:
        return explicit
    if not approved:
        return "critical" if drift_days >= 14 else "high"
    if deployed != approved:
        return "critical" if drift_days >= 30 else ("high" if drift_days >= 14 else "medium")
    return "low"


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"status": "critical" if counts["critical"] else ("high" if counts["high"] else ("medium" if counts["medium"] else "low")), "template_count": len(rows), "drifted_count": sum(1 for row in rows if row["status"] != "low"), "critical_count": counts["critical"]}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "template_count": counts[status]} for status in ("critical", "high", "medium", "low")]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
