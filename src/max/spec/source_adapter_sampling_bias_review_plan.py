"""Generate deterministic source adapter sampling bias review plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from max.spec._planning_common import compact, context, number, string_list, summary

SCHEMA_VERSION = "max.spec.source_adapter_sampling_bias_review_plan.v1"
KIND = "max.spec.source_adapter_sampling_bias_review_plan"

DEFAULT_MAX_SHARE = 0.5
DEFAULT_MIN_VOLUME = 10
DEFAULT_STALE_AFTER_DAYS = 30


def generate_source_adapter_sampling_bias_review_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    config = _config(spec)
    rows = _adapter_rows(spec, config)
    findings = _findings(rows, config)
    actions = _rebalance_actions(findings)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            adapter_count=len(rows),
            finding_count=len(findings),
            blocking_count=sum(1 for item in findings if item["severity"] == "high"),
            max_share=config["max_share"],
            stale_after_days=config["stale_after_days"],
        ),
        "sampling_bias_findings": findings,
        "rebalance_actions": actions,
        "holdout_checks": _holdout_checks(rows, findings),
        "verification_gates": _verification_gates(),
        "evidence_references": ctx["evidence_references"],
    }


def _config(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    bias = metadata.get("source_adapter_sampling_bias") if isinstance(metadata.get("source_adapter_sampling_bias"), dict) else {}
    return {
        "max_share": float(number(bias.get("max_share") or bias.get("share_threshold")) or DEFAULT_MAX_SHARE),
        "min_volume": int(number(bias.get("min_volume") or bias.get("minimum_sample_count")) or DEFAULT_MIN_VOLUME),
        "stale_after_days": int(number(bias.get("stale_after_days")) or DEFAULT_STALE_AFTER_DAYS),
        "target_segments": string_list(bias.get("target_segments")),
        "as_of": _parse_datetime(bias.get("as_of")) or datetime.now(timezone.utc),
    }


def _adapter_rows(spec: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    bias = metadata.get("source_adapter_sampling_bias") if isinstance(metadata.get("source_adapter_sampling_bias"), dict) else {}
    raw_rows = bias.get("adapters") or bias.get("samples") or spec.get("adapters") or spec.get("samples") or []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_rows if isinstance(raw_rows, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        count = int(number(item.get("sample_count") or item.get("count") or item.get("signals")) or 0)
        share = number(item.get("share") or item.get("sample_share"))
        rows.append(
            {
                "id": compact(item.get("adapter_id") or item.get("id")) or f"adapter_{index}",
                "adapter": compact(item.get("adapter") or item.get("name") or item.get("source_adapter")) or f"adapter_{index}",
                "sample_count": count,
                "share": float(share) if share is not None else None,
                "segments": string_list(item.get("segments") or item.get("covered_segments")),
                "target_segments": string_list(item.get("target_segments")) or config["target_segments"],
                "newest_signal_at": compact(item.get("newest_signal_at") or item.get("latest_signal_at")),
                "owner": compact(item.get("owner")) or "source_owner",
            }
        )
    total = sum(row["sample_count"] for row in rows)
    for row in rows:
        if row["share"] is None:
            row["share"] = row["sample_count"] / total if total else 0.0
    return rows


def _findings(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in rows:
        if row["share"] > config["max_share"]:
            findings.append(_finding(row, "overrepresented_source", "high", f"Adapter share {row['share']:.2f} exceeds threshold {config['max_share']:.2f}."))
        missing = [segment for segment in row["target_segments"] if segment not in row["segments"]]
        if missing:
            findings.append(_finding(row, "missing_target_segments", "medium", "Adapter sample is missing target segments.", missing_segments=missing))
        if _is_stale(row["newest_signal_at"], config):
            findings.append(_finding(row, "stale_samples", "medium", f"Newest signal is older than {config['stale_after_days']} days."))
        if row["sample_count"] < config["min_volume"]:
            findings.append(_finding(row, "low_volume_adapter", "low", f"Adapter sample count {row['sample_count']} is below minimum {config['min_volume']}."))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda item: (order[item["severity"]], item["adapter"].casefold(), item["id"].casefold()))


def _finding(row: dict[str, Any], finding_type: str, severity: str, description: str, **extra: Any) -> dict[str, Any]:
    item = {
        "id": f"{row['id']}:{finding_type}",
        "adapter_id": row["id"],
        "adapter": row["adapter"],
        "type": finding_type,
        "severity": severity,
        "owner": row["owner"],
        "sample_count": row["sample_count"],
        "share": row["share"],
        "newest_signal_at": row["newest_signal_at"],
        "description": description,
    }
    item.update(extra)
    return item


def _is_stale(value: str, config: dict[str, Any]) -> bool:
    parsed = _parse_datetime(value)
    if parsed is None:
        return bool(value)
    return (config["as_of"] - parsed).days > config["stale_after_days"]


def _rebalance_actions(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not findings:
        return [{"id": "SBA1", "type": "baseline_monitoring", "action": "Continue monitoring adapter sample mix against configured thresholds."}]
    actions: list[dict[str, str]] = []
    action_text = {
        "overrepresented_source": "Throttle this adapter and shift collection quota to underrepresented sources.",
        "missing_target_segments": "Add targeted collection jobs for missing segments before accepting the sample.",
        "stale_samples": "Refresh adapter ingestion and replace stale rows in the review sample.",
        "low_volume_adapter": "Increase sampling volume or mark the adapter as insufficient for holdout scoring.",
    }
    for finding in findings:
        actions.append({"id": f"SBA{len(actions) + 1}", "finding_id": finding["id"], "adapter": finding["adapter"], "type": finding["type"], "owner": finding["owner"], "action": action_text[finding["type"]]})
    return actions


def _holdout_checks(rows: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": "SBH1", "name": "adapter_mix_holdout", "description": "Recompute adapter share on the holdout sample before release.", "required": True},
        {"id": "SBH2", "name": "segment_coverage_holdout", "description": "Verify every target segment is represented in refreshed holdout rows.", "required": bool(rows or findings)},
    ]


def _verification_gates() -> list[dict[str, str]]:
    return [
        {"id": "SBG1", "name": "share_threshold", "description": "No adapter exceeds the configured maximum sample share."},
        {"id": "SBG2", "name": "freshness_threshold", "description": "No adapter has stale newest_signal_at values in the accepted sample."},
        {"id": "SBG3", "name": "segment_coverage", "description": "All configured target segments are represented before scoring."},
    ]


def _parse_datetime(value: Any) -> datetime | None:
    text = compact(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
