"""Generate deterministic model bias evaluation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_bias_evaluation_plan.v1"
KIND = "max.spec.model_bias_evaluation_plan"
DEFAULT_MIN_SAMPLE_SIZE = 100
STRICT_MIN_SAMPLE_SIZE = 250


def generate_model_bias_evaluation_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable evaluation plan for fairness-sensitive model changes."""
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_bias_evaluation")
    protected_segments = unique_records(
        named(
            hints.get("protected_segments")
            or hints.get("segments")
            or hints.get("sensitive_slices"),
            ("segment", "attribute", "name"),
        ),
        [],
    )
    metrics = unique_records(
        named(hints.get("slice_metrics") or hints.get("metrics"), ("metric", "name")),
        [{"name": "false positive rate parity", "metric": "false_positive_rate_parity"}],
    )
    strict = _strict_thresholds(hints)
    min_sample_size = _int(
        hints.get("minimum_sample_size") or hints.get("min_sample_size"),
        STRICT_MIN_SAMPLE_SIZE if strict else DEFAULT_MIN_SAMPLE_SIZE,
    )
    thresholds = _thresholds(hints, strict)
    segment_rows = [
        _segment_row(index, record, min_sample_size, evidence_ids)
        for index, record in enumerate(protected_segments, start=1)
    ]
    blockers = _blockers(protected_segments, hints, evidence_ids)
    warnings = _warnings(segment_rows, hints, min_sample_size, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Model Bias Evaluation Plan",
        "summary": source_summary(
            ctx,
            protected_segment_count=len(segment_rows),
            metric_count=len(metrics),
            blocker_count=len(blockers),
            warning_count=len(warnings),
            threshold_mode="strict" if strict else "standard",
        ),
        "model": compact(hints.get("model") or hints.get("model_name") or hints.get("target_model"))
        or "target model",
        "threshold_mode": "strict" if strict else "standard",
        "minimum_sample_size": min_sample_size,
        "protected_segments": segment_rows,
        "slice_metrics": [
            item(
                "MBM",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Measure model bias slice metric",
                name_keys=("name", "metric"),
                extra_keys=("metric", "baseline", "current", "threshold", "slice"),
            )
            for index, record in enumerate(metrics, start=1)
        ],
        "thresholds": thresholds,
        "remediation_actions": section(
            hints,
            ("remediation_actions", "remediations", "actions"),
            "MBR",
            "model_owner",
            "Remediate model bias finding",
            evidence_ids,
            ["rebalance evaluation data, tune decision threshold, retrain model, or add human review"],
            extra_keys=("owner_role", "segment", "metric", "deadline"),
        ),
        "approval_gates": section(
            hints,
            ("approval_gates", "approvals", "signoff"),
            "MBA",
            "governance_owner",
            "Approve model bias evaluation",
            evidence_ids,
            ["evaluation owner, model owner, product owner, and governance approver signoff before release"],
            extra_keys=("approver", "decision", "deadline"),
        ),
        "blockers": blockers,
        "warnings": warnings,
        "evidence_references": ctx["evidence_references"],
    }


def _segment_row(
    index: int, record: dict[str, Any], min_sample_size: int, evidence_ids: list[str]
) -> dict[str, Any]:
    data = item(
        "MBS",
        index,
        record,
        "evaluation_owner",
        evidence_ids,
        "Evaluate protected model segment",
        name_keys=("name", "segment", "attribute"),
        extra_keys=("segment", "attribute", "sample_size", "owner_role"),
    )
    data["minimum_sample_size"] = min_sample_size
    return data


def _thresholds(hints: dict[str, Any], strict: bool) -> list[dict[str, Any]]:
    default_threshold = "0.02 max adverse slice delta" if strict else "0.05 max adverse slice delta"
    fallback = [
        {
            "name": "adverse impact parity",
            "metric": "adverse_impact_ratio",
            "threshold": ">= 0.90" if strict else ">= 0.80",
        },
        {"name": "slice performance delta", "metric": "max_slice_delta", "threshold": default_threshold},
    ]
    return unique_records(
        named(hints.get("thresholds") or hints.get("evaluation_thresholds") or hints.get("gates"), ("metric", "name")),
        fallback,
    )


def _blockers(
    protected_segments: list[dict[str, Any]], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not protected_segments:
        blockers.append(
            row(
                "MBK",
                len(blockers) + 1,
                "missing protected segments",
                "governance_owner",
                "Model bias evaluation must define protected segments before approval.",
                evidence_ids,
                severity="critical",
                status="blocked",
            )
        )
    if not _has_remediation_owner(hints):
        blockers.append(
            row(
                "MBK",
                len(blockers) + 1,
                "missing remediation owner",
                "model_owner",
                "Model bias findings must have an accountable remediation owner before release.",
                evidence_ids,
                severity="high",
                status="blocked",
            )
        )
    return blockers


def _warnings(
    segment_rows: list[dict[str, Any]],
    hints: dict[str, Any],
    min_sample_size: int,
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for segment in segment_rows:
        sample_size = _int(segment.get("sample_size"), min_sample_size)
        if sample_size < min_sample_size:
            warnings.append(
                row(
                    "MBW",
                    len(warnings) + 1,
                    f"small sample size for {segment['name']}",
                    "evaluation_owner",
                    "Protected segment sample size is below the minimum required for bias evaluation.",
                    evidence_ids,
                    severity="medium",
                    segment=segment["name"],
                    sample_size=sample_size,
                    minimum_sample_size=min_sample_size,
                )
            )
    if _is_stale(hints.get("evaluation_evidence") or hints.get("evidence") or hints.get("evaluation_run")):
        warnings.append(
            row(
                "MBW",
                len(warnings) + 1,
                "stale evaluation evidence",
                "evaluation_owner",
                "Bias evaluation evidence should be refreshed before approval.",
                evidence_ids,
                severity="medium",
            )
        )
    return warnings


def _strict_thresholds(hints: dict[str, Any]) -> bool:
    for key in ("regulated", "user_facing"):
        if compact(hints.get(key)).lower() in {"1", "true", "yes", "y", "required"}:
            return True
    text = " ".join(
        compact(hints.get(key)).lower()
        for key in (
            "model_type",
            "risk_level",
            "domain",
            "deployment",
            "audience",
            "regulated",
            "user_facing",
        )
        if compact(hints.get(key))
    )
    return any(
        term in text
        for term in (
            "regulated",
            "user-facing",
            "user facing",
            "customer-facing",
            "customer facing",
            "high",
            "employment",
            "credit",
            "health",
            "insurance",
        )
    )


def _has_remediation_owner(hints: dict[str, Any]) -> bool:
    for key in ("remediation_owner", "owner", "model_owner"):
        if compact(hints.get(key)):
            return True
    actions = hints.get("remediation_actions") or hints.get("remediations") or hints.get("actions")
    if isinstance(actions, list):
        return any(
            isinstance(action, dict)
            and (compact(action.get("owner")) or compact(action.get("owner_role")))
            for action in actions
        )
    if isinstance(actions, dict):
        return bool(compact(actions.get("owner")) or compact(actions.get("owner_role")))
    return False


def _is_stale(value: Any) -> bool:
    if isinstance(value, dict):
        text = " ".join(compact(item).lower() for item in value.values())
    elif isinstance(value, list):
        text = " ".join(compact(item).lower() for item in value)
    else:
        text = compact(value).lower()
    return any(term in text for term in ("stale", "expired", "outdated", "older than"))


def _int(value: Any, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
