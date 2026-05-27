"""Spec generation token waste export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_generation_token_waste_report.v1"
KIND = "max.spec_generation_token_waste_report"


def build_spec_generation_token_waste_report(records: Iterable[dict[str, Any]], *, title: str = "Spec Generation Token Waste Report") -> dict[str, Any]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(_empty_group)
    attempt_count = 0
    for raw in records:
        attempt_count += 1
        key = (
            _text(raw.get("profile") or raw.get("profile_id")) or "unknown-profile",
            _text(raw.get("spec_type") or raw.get("type")) or "unknown-spec-type",
            _text(raw.get("model") or raw.get("model_name")) or "unknown-model",
        )
        group = groups[key]
        tokens = _tokens(raw)
        status = _text(raw.get("status") or raw.get("outcome")).lower()
        retried = _bool(raw.get("retried") or raw.get("is_retry")) or _int(raw.get("retry_count")) > 0
        accepted = status in {"accepted", "success", "succeeded", "published"}
        failed = status in {"failed", "error", "rejected", "timeout"} or bool(_text(raw.get("failure_reason") or raw.get("error")))

        group["attempt_count"] += 1
        group["total_tokens"] += tokens
        if accepted and not retried and not failed:
            group["accepted_tokens"] += tokens
        else:
            group["wasted_tokens"] += tokens
        if failed:
            group["failed_tokens"] += tokens
            reason = _text(raw.get("failure_reason") or raw.get("error") or raw.get("error_class")) or "unknown_failure"
            group["failure_reasons"][reason] += 1
        if retried:
            group["retried_tokens"] += tokens

    rows = [_row(profile, spec_type, model, group) for (profile, spec_type, model), group in groups.items()]
    rows.sort(key=lambda row: (_severity_rank(row["severity"]), -row["wasted_tokens"], row["profile"].lower(), row["spec_type"].lower(), row["model"].lower()))
    total_tokens = sum(row["total_tokens"] for row in rows)
    wasted_tokens = sum(row["wasted_tokens"] for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Spec Generation Token Waste Report",
        "summary": {
            "attempt_count": attempt_count,
            "group_count": len(rows),
            "total_tokens": total_tokens,
            "accepted_tokens": sum(row["accepted_tokens"] for row in rows),
            "failed_tokens": sum(row["failed_tokens"] for row in rows),
            "retried_tokens": sum(row["retried_tokens"] for row in rows),
            "wasted_tokens": wasted_tokens,
            "waste_ratio": _ratio(wasted_tokens, total_tokens),
        },
        "rows": rows,
    }


def render_spec_generation_token_waste_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_generation_token_waste_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Spec Generation Token Waste Report'}",
        "",
        "## Summary",
        "",
        f"- Attempts: {summary.get('attempt_count', 0)}",
        f"- Total tokens: {summary.get('total_tokens', 0)}",
        f"- Wasted tokens: {summary.get('wasted_tokens', 0)}",
        f"- Waste ratio: {summary.get('waste_ratio', 0.0)}",
        "",
        "## Waste Rows",
        "",
    ]
    rows = report.get("rows") or []
    if not rows:
        lines.append("- No spec generation token usage recorded.")
    else:
        for row in rows:
            lines.append(f"- {row['profile']} / {row['spec_type']} / {row['model']}: {row['wasted_tokens']} wasted tokens ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _empty_group() -> dict[str, Any]:
    return {"attempt_count": 0, "total_tokens": 0, "accepted_tokens": 0, "failed_tokens": 0, "retried_tokens": 0, "wasted_tokens": 0, "failure_reasons": defaultdict(int)}


def _row(profile: str, spec_type: str, model: str, group: dict[str, Any]) -> dict[str, Any]:
    waste_ratio = _ratio(group["wasted_tokens"], group["total_tokens"])
    return {
        "profile": profile,
        "spec_type": spec_type,
        "model": model,
        "attempt_count": group["attempt_count"],
        "total_tokens": group["total_tokens"],
        "accepted_tokens": group["accepted_tokens"],
        "failed_tokens": group["failed_tokens"],
        "retried_tokens": group["retried_tokens"],
        "wasted_tokens": group["wasted_tokens"],
        "waste_ratio": waste_ratio,
        "failure_reasons": [{"reason": reason, "count": count} for reason, count in sorted(group["failure_reasons"].items())],
        "severity": _severity(waste_ratio),
        "recommended_action": "Reduce failed or retried spec generation attempts before scaling this profile.",
    }


def _severity(waste_ratio: float) -> str:
    if waste_ratio >= 0.75:
        return "critical"
    if waste_ratio >= 0.5:
        return "high"
    if waste_ratio >= 0.25:
        return "medium"
    return "low"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _tokens(raw: dict[str, Any]) -> int:
    if raw.get("total_tokens") is not None:
        return _int(raw.get("total_tokens"))
    return _int(raw.get("prompt_tokens")) + _int(raw.get("completion_tokens"))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
