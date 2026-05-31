"""Generate deterministic feedback quality remediation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.feedback_quality_remediation_plan.v1"
KIND = "max.spec.feedback_quality_remediation_plan"


def generate_feedback_quality_remediation_plan(spec_like: Any) -> dict[str, Any]:
    """Return a remediation plan for noisy or incomplete feedback labels."""
    spec, ctx, hints, evidence_ids = base(spec_like, "feedback_quality_remediation")
    label_confusion_pairs = _confusion_pairs(hints.get("label_confusion_pairs") or spec.get("label_confusion_pairs"))
    missing_reason_counts = _missing_reason_counts(hints.get("missing_reason_counts") or spec.get("missing_reason_counts"))
    acceptance_metrics = _metrics(
        hints.get("acceptance_metrics") or hints.get("metrics") or spec.get("acceptance_metrics"),
        evidence_ids,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Feedback Quality Remediation Plan",
        "summary": source_summary(
            ctx,
            label_confusion_pair_count=len(label_confusion_pairs),
            missing_reason_count=len(missing_reason_counts),
            acceptance_metric_count=len(acceptance_metrics),
        ),
        "label_audit": _label_audit(label_confusion_pairs, missing_reason_counts, evidence_ids),
        "taxonomy_cleanup": section(
            hints,
            ("taxonomy_cleanup", "taxonomy_changes", "label_cleanup"),
            "FQT",
            "feedback_owner",
            "Clean up feedback taxonomy",
            evidence_ids,
            ["merge duplicate labels, deprecate ambiguous labels, and document canonical definitions"],
        ),
        "reviewer_calibration": section(
            hints,
            ("reviewer_calibration", "reviewer_alignment", "calibration"),
            "FQC",
            "review_ops",
            "Calibrate feedback reviewers",
            evidence_ids,
            ["run blinded relabeling session and resolve disagreements against the updated taxonomy"],
        ),
        "sampling_plan": section(
            hints,
            ("sampling_plan", "sampling"),
            "FQS",
            "analytics_owner",
            "Sample feedback quality",
            evidence_ids,
            ["stratify by label, reviewer, source, and missing-reason bucket for weekly quality review"],
        ),
        "data_correction_workflow": section(
            hints,
            ("data_correction_workflow", "correction_workflow", "data_corrections"),
            "FQD",
            "data_owner",
            "Correct feedback data",
            evidence_ids,
            ["queue relabeling fixes, backfill corrected records, and preserve before/after audit evidence"],
        ),
        "monitoring_metrics": section(
            hints,
            ("monitoring_metrics", "monitoring"),
            "FQM",
            "analytics_owner",
            "Monitor feedback quality",
            evidence_ids,
            [
                "track label confusion rate, missing reason rate, reviewer agreement, correction backlog age, and score-impact drift"
            ],
        ),
        "acceptance_metrics": acceptance_metrics or _default_acceptance_metrics(evidence_ids),
        "rollout_phases": section(
            hints,
            ("rollout_phases", "phases", "rollout"),
            "FQR",
            "feedback_owner",
            "Roll out remediation",
            evidence_ids,
            ["audit baseline, pilot corrected labels, backfill approved fixes, expand monitoring, and lock stop/go review"],
        ),
        "stop_go_criteria": section(
            hints,
            ("stop_go_criteria", "go_no_go", "exit_criteria"),
            "FQG",
            "feedback_owner",
            "Decide remediation stop/go",
            evidence_ids,
            [
                "go only when acceptance metrics are met, open high-severity label defects are zero, and reviewer calibration is signed off"
            ],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _label_audit(
    label_confusion_pairs: list[dict[str, Any]],
    missing_reason_counts: list[dict[str, Any]],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    for index, pair in enumerate(label_confusion_pairs, start=1):
        audit.append(
            row(
                "FQA",
                index,
                f"{pair['from_label']} -> {pair['to_label']}",
                "feedback_owner",
                f"Audit {pair['count']} records where {pair['from_label']} was confused with {pair['to_label']}.",
                evidence_ids,
                type="label_confusion",
                from_label=pair["from_label"],
                to_label=pair["to_label"],
                count=pair["count"],
            )
        )
    offset = len(audit)
    for index, reason in enumerate(missing_reason_counts, start=1):
        audit.append(
            row(
                "FQA",
                offset + index,
                reason["reason"],
                "feedback_owner",
                f"Audit {reason['count']} records missing a complete feedback reason.",
                evidence_ids,
                type="missing_reason",
                reason=reason["reason"],
                count=reason["count"],
            )
        )
    if audit:
        return audit
    return [
        row(
            "FQA",
            1,
            "baseline feedback label quality audit",
            "feedback_owner",
            "Audit noisy labels, missing reasons, reviewer disagreement, and score-impacting feedback records.",
            evidence_ids,
            type="baseline_audit",
        )
    ]


def _confusion_pairs(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            from_label = compact(item.get("from_label") or item.get("from") or item.get("actual")) or f"source label {index}"
            to_label = compact(item.get("to_label") or item.get("to") or item.get("predicted")) or f"target label {index}"
            count = _count(item.get("count") or item.get("records") or item.get("frequency"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            from_label = compact(item[0]) or f"source label {index}"
            to_label = compact(item[1]) or f"target label {index}"
            count = _count(item[2] if len(item) > 2 else 0)
        else:
            continue
        result.append({"from_label": from_label, "to_label": to_label, "count": count})
    return sorted(result, key=lambda item: (-item["count"], item["from_label"].casefold(), item["to_label"].casefold()))


def _missing_reason_counts(value: Any) -> list[dict[str, Any]]:
    items = value.items() if isinstance(value, dict) else enumerate(value if isinstance(value, list) else [], start=1)
    result: list[dict[str, Any]] = []
    for key, item in items:
        if isinstance(item, dict):
            reason = compact(item.get("reason") or item.get("name") or item.get("label")) or f"missing reason {key}"
            count = _count(item.get("count") or item.get("records") or item.get("frequency"))
        else:
            reason = compact(key)
            count = _count(item)
        if reason:
            result.append({"reason": reason, "count": count})
    return sorted(result, key=lambda item: (-item["count"], item["reason"].casefold()))


def _metrics(value: Any, evidence_ids: list[str]) -> list[dict[str, Any]]:
    metrics = []
    for index, record in enumerate(unique_records(value, []), start=1):
        name = compact(record.get("name")) or f"acceptance metric {index}"
        operator = compact(record.get("operator")) or "<="
        target = compact(record.get("target") or record.get("threshold")) or "agreed target"
        metrics.append(
            row(
                "FQAM",
                index,
                name,
                compact(record.get("owner")) or "analytics_owner",
                f"Accept remediation when {name} {operator} {target}.",
                evidence_ids,
                operator=operator,
                target=target,
            )
        )
    return metrics


def _default_acceptance_metrics(evidence_ids: list[str]) -> list[dict[str, Any]]:
    defaults = [
        ("label confusion rate", "<=", "2%"),
        ("missing feedback reason rate", "<=", "1%"),
        ("reviewer agreement", ">=", "90%"),
    ]
    return [
        row(
            "FQAM",
            index,
            name,
            "analytics_owner",
            f"Accept remediation when {name} {operator} {target}.",
            evidence_ids,
            operator=operator,
            target=target,
        )
        for index, (name, operator, target) in enumerate(defaults, start=1)
    ]


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
