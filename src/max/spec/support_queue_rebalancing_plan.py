"""Generate deterministic support queue rebalancing plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, rank, source_summary, unique_records


SCHEMA_VERSION = "max.spec.support_queue_rebalancing_plan.v1"
KIND = "max.spec.support_queue_rebalancing_plan"


def generate_support_queue_rebalancing_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "support_queue_rebalancing")
    queues = sorted(
        unique_records(
            named(hints.get("queues") or hints.get("queue_metrics"), ("queue", "team", "region")),
            [{"name": "support queue", "owner": "support_owner", "severity": "medium"}],
        ),
        key=_queue_sort_key,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, queue_count=len(queues)),
        "queue_baseline": [
            item("SQR", index, record, "support_owner", evidence_ids, "Review support queue baseline", name_keys=("name", "queue", "team", "region"), extra_keys=("queue", "team", "region", "backlog", "sla_risk"))
            for index, record in enumerate(queues, start=1)
        ],
        "routing_changes": section(hints, ("routing", "routing_changes"), "SQC", "support_ops_owner", "Apply routing change", evidence_ids, ["temporary routing rules by queue, tier, region, or vendor"]),
        "staffing_assumptions": section(hints, ("staffing", "staffing_assumptions"), "SQS", "support_manager", "Confirm staffing assumption", evidence_ids, ["coverage, language, tier, and vendor staffing assumption"]),
        "sla_customer_impact": section(hints, ("sla_impact", "customer_impact", "sla_customer_impact"), "SQI", "support_manager", "Assess SLA and customer impact", evidence_ids, ["SLA risk and customer escalation impact"]),
        "escalation_paths": section(hints, ("escalations", "escalation_paths"), "SQE", "support_owner", "Confirm escalation path", evidence_ids, ["tier, incident, and account escalation path"]),
        "communications": section(hints, ("communications",), "SQN", "support_ops_owner", "Communicate queue rebalance", evidence_ids, ["agent, vendor, account team, and leadership communication"]),
        "monitoring": section(hints, ("monitoring", "monitors"), "SQM", "support_ops_owner", "Monitor queue rebalance", evidence_ids, ["backlog, first response, breach, and reassignment monitor"]),
        "rollback": section(hints, ("rollback", "rollback_steps"), "SQX", "support_ops_owner", "Rollback queue rebalance", evidence_ids, ["restore previous routing and staffing allocation"]),
        "evidence_references": ctx["evidence_references"],
    }


def _queue_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    backlog = _number(record.get("backlog") or record.get("backlog_count"))
    sla_risk = compact(record.get("sla_risk") or record.get("sla")).lower()
    sla_rank = 0 if any(term in sla_risk for term in ("breach", "high", "critical", "at risk")) else 1
    return (sla_rank, -backlog, rank(record.get("severity")), compact(record.get("name")).casefold())


def _number(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0
