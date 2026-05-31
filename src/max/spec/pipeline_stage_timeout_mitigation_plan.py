"""Generate deterministic pipeline stage timeout mitigation plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, summary

SCHEMA_VERSION = "max.spec.pipeline_stage_timeout_mitigation_plan.v1"
KIND = "max.spec.pipeline_stage_timeout_mitigation_plan"


def generate_pipeline_stage_timeout_mitigation_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    stages = _stages(hints.get("stages") or hints.get("timeouts") or spec.get("stages") or spec.get("timeouts"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            affected_stage_count=len(stages),
            highest_severity=stages[0]["severity"] if stages else "low",
            plan_mode="mitigate_timeouts" if stages else "monitoring",
        ),
        "affected_stages": stages,
        "root_cause_hypotheses": _root_cause_hypotheses(stages),
        "immediate_actions": _immediate_actions(stages),
        "validation_checks": _validation_checks(stages),
        "owners": _owners(stages),
        "rollback_triggers": _rollback_triggers(stages),
        "evidence_references": ctx["evidence_references"],
    }


def _stages(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        timed_out = bool(item.get("timed_out") or item.get("timeout") or item.get("exceeded_timeout"))
        timeout_count = int(number(item.get("timeout_count") or item.get("timeouts") or item.get("failure_count")) or 0)
        runtime_seconds = float(number(item.get("runtime_seconds") or item.get("duration_seconds") or item.get("p95_seconds")) or 0.0)
        budget_seconds = float(number(item.get("budget_seconds") or item.get("timeout_seconds") or item.get("sla_seconds")) or 0.0)
        over_budget_ratio = round(runtime_seconds / budget_seconds, 4) if budget_seconds > 0 else 0.0
        if not timed_out and timeout_count <= 0 and (budget_seconds <= 0 or runtime_seconds <= budget_seconds):
            continue
        severity = _severity(timeout_count, over_budget_ratio, timed_out)
        rows.append(
            {
                "id": compact(item.get("id") or item.get("stage_id")) or f"PST{index}",
                "name": compact(item.get("name") or item.get("stage")) or f"stage_{index}",
                "owner": compact(item.get("owner") or item.get("team")) or _owner_hint(severity),
                "severity": severity,
                "timeout_count": timeout_count or (1 if timed_out else 0),
                "runtime_seconds": runtime_seconds,
                "budget_seconds": budget_seconds,
                "over_budget_ratio": over_budget_ratio,
                "symptom": compact(item.get("symptom") or item.get("error") or item.get("reason")) or _symptom(over_budget_ratio),
            }
        )
    return sorted(rows, key=lambda row: (_severity_rank(row["severity"]), row["name"].casefold(), row["id"].casefold()))


def _root_cause_hypotheses(stages: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not stages:
        return [{"id": "PTH1", "stage_id": "none", "hypothesis": "No active timeout pattern is present; continue monitoring for budget drift."}]
    return [
        {
            "id": f"PTH{index}",
            "stage_id": stage["id"],
            "hypothesis": _hypothesis(stage),
        }
        for index, stage in enumerate(stages, start=1)
    ]


def _immediate_actions(stages: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not stages:
        return [{"id": "PTA1", "stage_id": "none", "owner": "on_call", "action": "Keep timeout dashboards watched and confirm the next scheduled run remains within budget."}]
    return [
        {
            "id": f"PTA{index}",
            "stage_id": stage["id"],
            "owner": stage["owner"],
            "action": _action(stage),
        }
        for index, stage in enumerate(stages, start=1)
    ]


def _validation_checks(stages: list[dict[str, Any]]) -> list[dict[str, str]]:
    target = "all affected stages complete within configured timeout budgets for two consecutive runs" if stages else "next pipeline run remains within configured timeout budgets"
    return [
        {"id": "PTV1", "name": "timeout_budget_compliance", "target": target},
        {"id": "PTV2", "name": "downstream_backlog_recovery", "target": "queued work drains without new timeout alerts"},
    ]


def _owners(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owners = sorted({stage["owner"] for stage in stages}, key=str.casefold) or ["on_call"]
    return [{"id": f"PTO{index}", "owner": owner, "stage_ids": [stage["id"] for stage in stages if stage["owner"] == owner], "responsibility": "coordinate timeout mitigation" if stages else "monitor pipeline timeout budget"} for index, owner in enumerate(owners, start=1)]


def _rollback_triggers(stages: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"id": "PTR1", "name": "timeout_rate_worsens", "condition": "timeout count increases after mitigation is applied", "action": "rollback the latest stage configuration change"},
        {"id": "PTR2", "name": "data_freshness_regresses", "condition": "pipeline freshness misses its recovery target", "action": "restore prior concurrency and timeout settings"},
    ] if stages else [{"id": "PTR1", "name": "new_timeout_detected", "condition": "any stage exceeds its timeout budget", "action": "promote from monitoring to active mitigation"}]


def _severity(timeout_count: int, over_budget_ratio: float, timed_out: bool) -> str:
    if timeout_count >= 5 or over_budget_ratio >= 2.0:
        return "critical"
    if timeout_count >= 2 or over_budget_ratio >= 1.25:
        return "high"
    if timed_out or timeout_count >= 1 or over_budget_ratio > 1.0:
        return "medium"
    return "low"


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _owner_hint(severity: str) -> str:
    return "pipeline_lead" if severity in {"critical", "high"} else "stage_owner"


def _symptom(over_budget_ratio: float) -> str:
    return "runtime exceeded timeout budget" if over_budget_ratio > 1.0 else "timeout observed"


def _hypothesis(stage: dict[str, Any]) -> str:
    if stage["over_budget_ratio"] >= 2.0:
        return "stage work volume or dependency latency is far above the configured timeout budget"
    if stage["timeout_count"] >= 2:
        return "repeated timeout failures indicate capacity, concurrency, or downstream dependency pressure"
    return "single timeout may be transient but needs budget and dependency verification"


def _action(stage: dict[str, Any]) -> str:
    if stage["severity"] == "critical":
        return "pause nonessential intake, reduce concurrency pressure, and assign lead review before the next run"
    if stage["severity"] == "high":
        return "raise stage timeout guardrails only with owner approval and remove avoidable downstream waits"
    return "capture run diagnostics and rerun with focused monitoring"


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("pipeline_stage_timeout_mitigation")
    return hints if isinstance(hints, dict) else {}
