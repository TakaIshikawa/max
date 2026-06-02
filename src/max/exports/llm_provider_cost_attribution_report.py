"""LLM provider cost attribution export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Mapping

SCHEMA_VERSION = "max.llm_provider_cost_attribution_report.v1"
KIND = "max.llm_provider_cost_attribution_report"


def build_llm_provider_cost_attribution_report_export(records: list[Mapping[str, Any]], *, generated_at: str = "2026-06-01T00:00:00+00:00", source: str = "llm_usage") -> dict[str, Any]:
    provider_groups: dict[str, dict[str, Any]] = defaultdict(_bucket)
    model_groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(_bucket)
    unit_rows = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        provider = _text(record.get("provider")) or "unknown-provider"
        model = _text(record.get("model")) or "unknown-model"
        stage = _text(record.get("stage") or record.get("pipeline_stage")) or "unknown-stage"
        domain = _text(record.get("domain")) or "unknown-domain"
        input_tokens = _int(record.get("input_tokens"))
        output_tokens = _int(record.get("output_tokens"))
        total_tokens = _int(record.get("total_tokens")) or input_tokens + output_tokens
        cost = round(float(record.get("estimated_cost_usd") or 0), 6)
        budget = float(record.get("budget_usd") or record.get("budget_limit_usd") or 0)
        row = {"unit_id": _text(record.get("unit_id") or record.get("id")) or "unknown-unit", "provider": provider, "model": model, "stage": stage, "domain": domain, "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens, "estimated_cost_usd": cost, "budget_id": _text(record.get("budget_id")) or None, "over_budget": bool(budget and cost > budget)}
        unit_rows.append(row)
        _add(provider_groups[provider], row)
        _add(model_groups[(provider, model)], row)
    provider_rows = [_row({"provider": provider}, bucket) for provider, bucket in provider_groups.items()]
    model_rows = [_row({"provider": provider, "model": model}, bucket) for (provider, model), bucket in model_groups.items()]
    provider_rows.sort(key=_cost_sort)
    model_rows.sort(key=_cost_sort)
    unit_rows.sort(key=_cost_sort)
    highest = model_rows[0] if model_rows else None
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "source": source, "summary": {"unit_count": len(unit_rows), "total_tokens": sum(row["total_tokens"] for row in unit_rows), "estimated_cost_usd": round(sum(row["estimated_cost_usd"] for row in unit_rows), 6), "highest_cost_model": highest, "over_budget_count": sum(1 for row in unit_rows if row["over_budget"])}, "provider_rows": provider_rows, "model_rows": model_rows, "unit_rows": unit_rows}


def render_llm_provider_cost_attribution_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_llm_provider_cost_attribution_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# LLM Provider Cost Attribution Report", "", "## Provider Costs", ""]
    lines.extend([f"- {row['provider']}: ${row['estimated_cost_usd']:.6f} ({row['total_tokens']} tokens)" for row in report.get("provider_rows") or []] or ["- No LLM usage records supplied."])
    lines.extend(["", "## Model Costs", ""])
    lines.extend([f"- {row['provider']} / {row['model']}: ${row['estimated_cost_usd']:.6f}" for row in report.get("model_rows") or []] or ["- No model costs."])
    return "\n".join(lines).rstrip() + "\n"


def _bucket() -> dict[str, Any]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0, "unit_count": 0}


def _add(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        bucket[key] += row[key]
    bucket["estimated_cost_usd"] = round(bucket["estimated_cost_usd"] + row["estimated_cost_usd"], 6)
    bucket["unit_count"] += 1


def _row(labels: dict[str, Any], bucket: dict[str, Any]) -> dict[str, Any]:
    return {**labels, **bucket}


def _cost_sort(row: dict[str, Any]) -> tuple[Any, ...]:
    return (-row["estimated_cost_usd"], row.get("provider", "").lower(), row.get("model", "").lower(), row.get("unit_id", "").lower())


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
