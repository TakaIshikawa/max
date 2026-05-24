"""JSON API renderer for prompt redaction coverage status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.prompt_redaction_coverage_status.v1"
KIND = "max.api.prompt_redaction_coverage_status"
STATUS_RANK = {"exposed": 0, "partial": 1, "covered": 2}


def prompt_redaction_coverage_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    templates = _templates(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(templates), "templates": templates, "uncovered_fields": _uncovered(templates), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, template_count=len(templates))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _templates(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("templates") if isinstance(payload.get("templates"), list) else payload.get("prompts")
    rows = [_template(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["template_id"]))


def _template(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    sensitive = _strings(item.get("sensitive_fields"))
    rules = _strings(item.get("redaction_rules", item.get("covered_fields")))
    explicit_uncovered = _strings(item.get("uncovered_fields"))
    uncovered = explicit_uncovered or sorted(set(sensitive) - set(rules))
    coverage = _ratio(item.get("coverage_ratio"))
    if item.get("coverage_ratio") is None:
        coverage = round((len(sensitive) - len(uncovered)) / len(sensitive), 4) if sensitive else 1.0
    status = "covered" if not uncovered and coverage >= 1.0 else ("exposed" if sensitive and coverage <= 0.0 else "partial")
    return {"template_id": _text(item.get("template_id") or item.get("id")) or f"template-{index}", "sensitive_fields": sensitive, "redaction_rules": rules, "uncovered_fields": uncovered, "coverage_ratio": _clamp(coverage), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    total_fields = sum(len(row["sensitive_fields"]) for row in rows)
    uncovered = sum(len(row["uncovered_fields"]) for row in rows)
    return {"template_count": len(rows), "covered_count": counts["covered"], "partial_count": counts["partial"], "exposed_count": counts["exposed"], "uncovered_field_count": uncovered, "coverage_ratio": round((total_fields - uncovered) / total_fields, 4) if total_fields else 1.0}


def _uncovered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"template_id": row["template_id"], "fields": row["uncovered_fields"]} for row in rows if row["uncovered_fields"]]


def _ratio(value: Any) -> float:
    return _clamp(float_or_zero(value))


def _clamp(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 4)


def _strings(value: Any) -> list[str]:
    return sorted({_text(item) for item in as_list(value) if _text(item)})


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

