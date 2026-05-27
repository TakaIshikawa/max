"""Model context window pressure export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.model_context_window_pressure_report.v1"
KIND = "max.model_context_window_pressure_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_model_context_window_pressure_report(records: Iterable[dict[str, Any]], *, title: str = "Model Context Window Pressure Report", generated_at: str = DEFAULT_GENERATED_AT, utilization_threshold: float = 0.8) -> dict[str, Any]:
    threshold = min(max(float(utilization_threshold), 0.0), 1.0)
    rows = []
    total_records = 0
    for raw in records:
        total_records += 1
        prompt = _int(raw.get("prompt_tokens"))
        completion = _int(raw.get("completion_tokens"))
        total = _int(raw.get("total_tokens")) or prompt + completion
        window = _int(raw.get("context_window") or raw.get("context_window_tokens"))
        utilization = round(total / window, 4) if window else 0.0
        overflow = bool(window and total > window)
        near = not overflow and utilization >= threshold
        if not overflow and not near:
            continue
        rows.append({"run_id": _text(raw.get("run_id")) or "unknown-run", "model": _text(raw.get("model")) or "unknown-model", "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total, "context_window": window, "utilization_percent": round(utilization * 100, 2), "near_limit": near, "overflow": overflow, "recommended_mitigation": "Shorten retrieved context or summarize prior turns." if overflow else "Monitor prompt growth and trim low-value context."})
    rows.sort(key=lambda row: (not row["overflow"], -row["utilization_percent"], row["run_id"].lower(), row["model"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Model Context Window Pressure Report", "summary": {"record_count": total_records, "pressure_row_count": len(rows), "near_limit_count": sum(1 for row in rows if row["near_limit"]), "overflow_count": sum(1 for row in rows if row["overflow"])}, "pressure_rows": rows}


def render_model_context_window_pressure_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_model_context_window_pressure_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Model Context Window Pressure Report'}", "", "## Summary", "", f"- Pressure rows: {summary.get('pressure_row_count', 0)}", f"- Near limit: {summary.get('near_limit_count', 0)}", f"- Overflow: {summary.get('overflow_count', 0)}"]).rstrip() + "\n"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
