"""Inference prompt redaction gap export report."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = "max.inference_prompt_redaction_gap_report.v1"
KIND = "max.inference_prompt_redaction_gap_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"

SENSITIVE_FIELD_WEIGHTS = {
    "private_key": 10,
    "jwt": 9,
    "api_key": 8,
    "token": 8,
    "password": 7,
    "secret": 7,
    "ssn": 6,
    "credit_card": 6,
    "email": 3,
    "phone": 3,
    "pii": 3,
}


def build_inference_prompt_redaction_gap_report(
    records: Iterable[Mapping[str, Any]],
    *,
    metadata: Mapping[str, Any] | None = None,
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    """Summarize prompt redaction gaps by provider, model, and profile."""

    prompts = [_prompt_row(raw, index) for index, raw in enumerate(records, start=1)]
    prompts.sort(
        key=lambda row: (
            row["provider"].casefold(),
            row["model"].casefold(),
            row["profile"].casefold(),
            row["id"].casefold(),
        )
    )
    risk_rows = _risk_rows(prompts)
    gap_prompts = [row for row in prompts if row["gap_count"] > 0]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "metadata": _jsonable(metadata or {}),
        "summary": {
            "prompt_count": len(prompts),
            "redacted_prompt_count": sum(1 for row in prompts if row["redaction_status"] == "redacted"),
            "partial_redaction_prompt_count": sum(1 for row in prompts if row["redaction_status"] == "partial"),
            "unredacted_prompt_count": sum(1 for row in prompts if row["redaction_status"] == "unredacted"),
            "unredacted_sensitive_field_gap_count": sum(row["gap_count"] for row in prompts),
            "risk_group_count": len(risk_rows),
            "highest_risk_score": max([row["risk_score"] for row in risk_rows] or [0]),
        },
        "prompts": prompts,
        "risk_rows": risk_rows,
        "redaction_gaps": gap_prompts,
    }


def render_inference_prompt_redaction_gap_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _prompt_row(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    unredacted = _strings(
        raw.get("unredacted_sensitive_fields")
        or raw.get("sensitive_fields_unredacted")
        or raw.get("gaps")
    )
    redacted = _strings(raw.get("redacted_sensitive_fields") or raw.get("sensitive_fields_redacted"))
    detected = _strings(raw.get("sensitive_fields") or raw.get("detected_sensitive_fields"))
    if not unredacted and _bool(raw.get("contains_unredacted_sensitive_data")):
        unredacted = detected or ["sensitive_data"]
    redaction_status = _status(raw, unredacted, redacted, detected)
    return {
        "id": _text(raw.get("id") or raw.get("prompt_id") or raw.get("request_id")) or f"prompt-{index}",
        "provider": _text(raw.get("provider")) or "unknown",
        "model": _text(raw.get("model") or raw.get("model_id")) or "unknown",
        "profile": _text(raw.get("profile") or raw.get("profile_id")) or "default",
        "redaction_status": redaction_status,
        "sensitive_fields": detected,
        "redacted_sensitive_fields": redacted,
        "unredacted_sensitive_fields": unredacted,
        "gap_count": len(unredacted),
        "risk_score": sum(_field_weight(field) for field in unredacted),
    }


def _risk_rows(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in prompts:
        if row["gap_count"] <= 0:
            continue
        key = (row["provider"], row["model"], row["profile"])
        item = grouped.setdefault(
            key,
            {
                "provider": row["provider"],
                "model": row["model"],
                "profile": row["profile"],
                "prompt_count": 0,
                "gap_count": 0,
                "risk_score": 0,
                "prompt_ids": [],
                "unredacted_sensitive_fields": [],
            },
        )
        item["prompt_count"] += 1
        item["gap_count"] += row["gap_count"]
        item["risk_score"] += row["risk_score"]
        item["prompt_ids"].append(row["id"])
        item["unredacted_sensitive_fields"].extend(row["unredacted_sensitive_fields"])

    rows = []
    for item in grouped.values():
        item["prompt_ids"] = sorted(set(item["prompt_ids"]), key=str.casefold)
        item["unredacted_sensitive_fields"] = sorted(set(item["unredacted_sensitive_fields"]), key=str.casefold)
        rows.append(item)
    return sorted(
        rows,
        key=lambda row: (
            -row["risk_score"],
            -row["gap_count"],
            row["provider"].casefold(),
            row["model"].casefold(),
            row["profile"].casefold(),
        ),
    )


def _status(raw: Mapping[str, Any], unredacted: list[str], redacted: list[str], detected: list[str]) -> str:
    explicit = _text(raw.get("redaction_status") or raw.get("status")).casefold()
    if explicit in {"redacted", "partial", "unredacted"}:
        return explicit
    if unredacted and redacted:
        return "partial"
    if unredacted:
        return "unredacted"
    if redacted or detected or _bool(raw.get("redacted")):
        return "redacted"
    return "unknown"


def _field_weight(field: str) -> int:
    normalized = field.casefold().replace("-", "_").replace(" ", "_")
    return next((weight for name, weight in SENSITIVE_FIELD_WEIGHTS.items() if name in normalized), 1)


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable):
        values = list(value)
    else:
        values = [value]
    return sorted({_text(item) for item in values if _text(item)}, key=str.casefold)


def _bool(value: Any) -> bool:
    return value is True or _text(value).casefold() in {"1", "true", "yes", "y"}


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
