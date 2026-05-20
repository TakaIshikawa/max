"""Generate deterministic operational metrics review plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.operational_metrics_review_plan.v1"
KIND = "max.spec.operational_metrics_review_plan"


def generate_operational_metrics_review_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    metrics = _metrics(hints.get("metrics"))
    evidence_ids = _evidence_ids(ctx)
    cadence = compact(hints.get("review_cadence") or hints.get("cadence")) or _first_metric_value(metrics, "cadence") or "weekly during rollout"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, metric_count=len(metrics), review_cadence=cadence, escalation_trigger_count=len(ctx["risks"])),
        "metric_inventory": [_metric_record(index, metric, evidence_ids) for index, metric in enumerate(metrics, start=1)],
        "baseline_expectations": [{"id": f"BE{index}", "metric": metric["name"], "target": metric["target"], "owner": metric["owner"], "evidence_reference_ids": evidence_ids} for index, metric in enumerate(metrics, start=1)],
        "alert_thresholds": [{"id": f"AT{index}", "metric": metric["name"], "threshold": metric["threshold"], "owner": metric["owner"], "evidence_reference_ids": evidence_ids} for index, metric in enumerate(metrics, start=1)],
        "review_cadence": {"cadence": cadence, "owner": compact(hints.get("review_owner")) or "operations_owner", "forum": compact(hints.get("forum")) or "operational review"},
        "escalation_triggers": _escalations(hints, ctx, evidence_ids),
        "owner_roles": _owner_roles(metrics),
        "evidence_references": ctx["evidence_references"],
    }


def _metric_record(index: int, metric: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"MI{index}", "name": metric["name"], "owner": metric["owner"], "target": metric["target"], "threshold": metric["threshold"], "review_cadence": metric["cadence"], "evidence_reference_ids": evidence_ids}


def _metrics(value: Any) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
    rows: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        name = compact(item.get("name") or item.get("metric")) or f"metric {index}"
        rows.append(
            {
                "name": name,
                "owner": compact(item.get("owner")) or "operations_owner",
                "target": compact(item.get("target") or item.get("baseline")) or "baseline established",
                "threshold": compact(item.get("threshold") or item.get("alert_threshold")) or "threshold defined",
                "cadence": compact(item.get("review_cadence") or item.get("cadence")) or "weekly",
            }
        )
    if not rows:
        rows = [
            {"name": "activation rate", "owner": "product_owner", "target": "meets launch baseline", "threshold": "drops below launch baseline", "cadence": "weekly"},
            {"name": "reliability", "owner": "operations_owner", "target": "meets service objective", "threshold": "error budget burn exceeds threshold", "cadence": "daily during rollout"},
            {"name": "support volume", "owner": "support_owner", "target": "within forecast", "threshold": "tickets exceed forecast", "cadence": "weekly"},
        ]
    return sorted(rows, key=lambda row: row["name"].casefold())


def _escalations(hints: dict[str, Any], ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    triggers = _records(hints.get("escalation_triggers")) or [{"name": risk, "owner": "operations_owner"} for risk in ctx["risks"]]
    if not triggers:
        triggers = [{"name": "metric threshold breach", "owner": "operations_owner"}]
    return [{"id": f"ET{index}", "trigger": row["name"], "owner": row["owner"] or "operations_owner", "action": f"Escalate when {row['name']}.", "evidence_reference_ids": evidence_ids} for index, row in enumerate(triggers, start=1)]


def _owner_roles(metrics: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    for metric in metrics:
        seen.setdefault(metric["owner"], f"Review and respond to {metric['name']} metric movement.")
    return [{"role": owner, "responsibility": responsibility} for owner, responsibility in sorted(seen.items())]


def _records(value: Any) -> list[dict[str, str]]:
    raw = [value] if isinstance(value, dict) else value if isinstance(value, list) else string_list(value)
    rows = []
    for item in raw:
        if isinstance(item, dict):
            rows.append({"name": compact(item.get("name") or item.get("trigger")), "owner": compact(item.get("owner"))})
        elif compact(item):
            rows.append({"name": compact(item), "owner": ""})
    return [row for row in rows if row["name"]]


def _first_metric_value(metrics: list[dict[str, str]], key: str) -> str:
    return metrics[0][key] if metrics else ""


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("operational_metrics_review")
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
