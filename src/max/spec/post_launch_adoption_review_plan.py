"""Generate deterministic post-launch adoption review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, number
from max.spec._review_plan_common import base, records, row, source_summary, values


SCHEMA_VERSION = "max.spec.post_launch_adoption_review_plan.v1"
KIND = "max.spec.post_launch_adoption_review_plan"


def generate_post_launch_adoption_review_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "post_launch_adoption_review")
    metrics_raw = records(hints.get("adoption_metrics") or hints.get("metrics") or spec.get("adoption_metrics"), ["activation rate"])
    metrics = []
    below_target = False
    for index, item in enumerate(metrics_raw, start=1):
        actual = number(item.get("actual") or item.get("value"))
        target = number(item.get("target"))
        at_risk = actual is not None and target is not None and actual < target
        below_target = below_target or at_risk
        metrics.append(row("PLM", index, item["name"], compact(item.get("owner")) or "growth_owner", compact(item.get("description")) or f"Review adoption metric {item['name']}.", evidence_ids, actual=actual, target=target, status="below_target" if at_risk else "on_track"))
    cohorts = values(hints.get("cohort_segments") or hints.get("cohorts") or spec.get("cohort_segments"), [ctx["target_user"]])
    missing_cohort = cohorts == ["primary user"] or any("missing" in item.lower() for item in cohorts)
    risks = records(hints.get("adoption_risks") or hints.get("risks"), [] if not (below_target or missing_cohort) else ["cohort coverage gap"])
    status = "at_risk" if below_target or missing_cohort or risks else "on_track"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, adoption_status=status, metric_count=len(metrics), cohort_count=len(cohorts)),
        "adoption_metrics": metrics,
        "cohort_segments": [row("PLC", index, name, "growth_owner", f"Measure adoption for cohort {name}.", evidence_ids) for index, name in enumerate(cohorts, start=1)],
        "adoption_risks": [row("PLR", index, item["name"], compact(item.get("owner")) or "growth_owner", compact(item.get("description")) or f"Track adoption risk: {item['name']}.", evidence_ids, severity=compact(item.get("severity")) or "medium") for index, item in enumerate(risks, start=1)],
        "intervention_actions": [row("PLI", index, item["name"], compact(item.get("owner")) or "growth_owner", f"Run intervention for {item['name']}.", evidence_ids, timing=compact(item.get("due")) or "next review") for index, item in enumerate(risks or ([{"name": "below-target adoption recovery"}] if status == "at_risk" else []), start=1)],
        "review_checkpoints": [row("PLK", index, name, "growth_owner", f"Review adoption progress at {name}.", evidence_ids) for index, name in enumerate(values(hints.get("review_checkpoints"), ["7 days post launch", "30 days post launch"]), start=1)],
        "adoption_status": status,
        "evidence_references": ctx["evidence_references"],
    }
