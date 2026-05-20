"""Deterministic operational metrics review plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, row_id, section, sorted_rows, text

KIND = "max.design_brief.operational_metrics_review_plan"
SCHEMA_VERSION = "max.design_brief.operational_metrics_review_plan.v1"


def generate_design_brief_operational_metrics_review_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "operational_metrics_review_plan")
    metrics = _metrics(data)
    gaps = _gaps(metrics)
    missing_thresholds = sum(1 for row in metrics if not row["target_threshold"])
    status = "blocked" if not metrics or missing_thresholds == len(metrics) else ("needs_attention" if gaps else "ready")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"readiness_status": status, "metric_count": len(metrics), "review_gap_count": len(gaps)},
        "metric_reviews": metrics,
        "review_gaps": gaps,
    }


def _metrics(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    cadence = text(data.get("review_cadence") or data.get("cadence"))
    for index, item in enumerate(list_of_dicts(data.get("kpis") or data.get("metrics")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("OM", index)),
                "metric": first_text(item.get("metric"), item.get("kpi"), item.get("name"), default=f"metric {index}"),
                "baseline": text(item.get("baseline")),
                "target_threshold": text(item.get("target_threshold") or item.get("threshold") or item.get("target")),
                "review_cadence": text(item.get("review_cadence") or item.get("cadence"), cadence),
                "alert_owner": text(item.get("alert_owner") or item.get("owner")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "metric")


def _gaps(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not metrics:
        return [gap("missing_operational_metrics", "No operational metrics were provided.")]
    gaps = []
    for row in metrics:
        key = row["metric"].lower().replace(" ", "_")
        if not row["alert_owner"]:
            gaps.append(gap(f"{key}_missing_alert_owner", f"{row['metric']} is missing an alert owner."))
        if not row["target_threshold"]:
            gaps.append(gap(f"{key}_missing_target_threshold", f"{row['metric']} is missing a target threshold.", "medium"))
        if not row["review_cadence"]:
            gaps.append(gap(f"{key}_missing_review_cadence", f"{row['metric']} is missing a review cadence.", "medium"))
    return gaps
