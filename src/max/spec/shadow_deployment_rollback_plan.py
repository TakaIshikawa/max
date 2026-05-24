"""Generate deterministic shadow deployment rollback plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.shadow_deployment_rollback_plan.v1"
KIND = "max.spec.shadow_deployment_rollback_plan"


def generate_shadow_deployment_rollback_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "shadow_deployment_rollback")
    components = unique_records(
        named(
            hints.get("shadowed_components") or hints.get("components") or hints.get("shadow_scope"),
            ("component", "pipeline", "model", "publisher", "name"),
        ),
        [{"name": "shadowed inference component", "component": "shadowed inference component", "owner": "release_owner"}],
    )
    metrics = unique_records(
        named(hints.get("comparison_metrics") or hints.get("metrics"), ("metric", "name")),
        [
            {
                "name": "request parity",
                "metric": "request parity",
                "threshold": "no missing mirrored requests",
                "owner": "release_owner",
            },
            {
                "name": "latency delta",
                "metric": "latency delta",
                "threshold": "p95 delta <= 10%",
                "owner": "sre_owner",
            },
        ],
    )
    rollback_triggers = section(
        hints,
        ("rollback_triggers", "triggers", "rollback_criteria"),
        "SDT",
        "release_owner",
        "Define shadow deployment rollback trigger",
        evidence_ids,
        ["rollback if comparison metric breaches threshold, errors increase, data parity fails, or owner rejects launch"],
        extra_keys=("metric", "threshold"),
    )
    risk_flags = _risk_flags(rollback_triggers, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            shadowed_component_count=len(components),
            comparison_metric_count=len(metrics),
            high_risk_count=sum(1 for flag in risk_flags if flag["severity"] == "high"),
        ),
        "shadow_scope": [
            item(
                "SDS",
                index,
                record,
                "release_owner",
                evidence_ids,
                "Inventory shadowed component",
                name_keys=("name", "component", "pipeline", "model", "publisher"),
                extra_keys=("component", "pipeline", "model", "publisher", "environment", "traffic"),
            )
            for index, record in enumerate(components, start=1)
        ],
        "comparison_metrics": [
            item(
                "SDM",
                index,
                record,
                "sre_owner",
                evidence_ids,
                "Track shadow deployment comparison metric",
                name_keys=("name", "metric"),
                extra_keys=("metric", "threshold", "baseline", "window"),
            )
            for index, record in enumerate(metrics, start=1)
        ],
        "rollback_triggers": rollback_triggers,
        "rollback_risk_flags": risk_flags,
        "decision_owner_actions": section(
            hints,
            ("decision_owner_actions", "owner_actions", "actions"),
            "SDO",
            "release_owner",
            "Assign shadow rollback decision owner action",
            evidence_ids,
            ["release owner reviews trigger breach, declares rollback, pauses promotion, and assigns remediation"],
            extra_keys=("role", "decision_owner", "deadline"),
        ),
        "communication_steps": section(
            hints,
            ("communication_steps", "communications", "comms"),
            "SDC",
            "incident_owner",
            "Coordinate shadow rollback communication",
            evidence_ids,
            ["notify engineering, SRE, support, product, and downstream integration owners of rollback decision"],
        ),
        "validation_checks": section(
            hints,
            ("validation_checks", "validation", "checks"),
            "SDV",
            "sre_owner",
            "Validate shadow rollback",
            evidence_ids,
            ["confirm shadow traffic disabled, primary path healthy, comparison alerts quiet, and replay queue drained"],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _risk_flags(triggers: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    missing = [trigger for trigger in triggers if not compact(trigger.get("threshold"))]
    if not missing:
        return [
            item(
                "SDF",
                1,
                {
                    "name": "rollback trigger thresholds documented",
                    "severity": "low",
                    "description": "Rollback triggers include explicit threshold evidence for decision review.",
                },
                "release_owner",
                evidence_ids,
                "Record shadow rollback risk",
            )
        ]
    return [
        item(
            "SDF",
            index,
            {
                "name": f"missing rollback threshold for {trigger['name']}",
                "severity": "high",
                "description": "Rollback trigger is missing an explicit threshold for the decision owner.",
            },
            "release_owner",
            evidence_ids,
            "Flag shadow rollback threshold gap",
        )
        for index, trigger in enumerate(missing, start=1)
    ]
