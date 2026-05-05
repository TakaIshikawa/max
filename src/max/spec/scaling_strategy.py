"""Generate deterministic scaling strategies for implementation-ready specs."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


SCALING_STRATEGY_SCHEMA_VERSION = "max-scaling-strategy/v1"

SCALING_STRATEGY_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "idea_id",
    "title",
    "section",
    "row_type",
    "item_id",
    "metric_name",
    "threshold_type",
    "threshold_value",
    "threshold_unit",
    "scaling_dimension",
    "scaling_type",
    "scaling_action",
    "target_capacity",
    "min_instances",
    "max_instances",
    "cpu_threshold_percent",
    "memory_threshold_percent",
    "response_time_ms",
    "cost_per_unit_usd",
    "projected_monthly_cost_usd",
    "trigger_condition",
    "cooldown_period_seconds",
    "notes",
    "source_fields",
)


def generate_scaling_strategy(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an idea, evaluation, and optional tact spec into scaling guidance."""
    spec = tact_spec or generate_spec_preview(unit, evaluation)

    return {
        "schema_version": SCALING_STRATEGY_SCHEMA_VERSION,
        "kind": "max.scaling_strategy",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": unit.category,
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evaluation_available": evaluation is not None,
        },
        "summary": {
            "title": unit.title,
            "target_user": unit.specific_user or unit.target_users,
            "workflow_context": unit.workflow_context,
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
            "scaling_approach": _scaling_approach(unit, spec),
        },
        "capacity_thresholds": _capacity_thresholds(unit, evaluation, spec),
        "auto_scaling_rules": _auto_scaling_rules(unit, evaluation, spec),
        "horizontal_scaling": _horizontal_scaling(unit, spec),
        "vertical_scaling": _vertical_scaling(unit, spec),
        "cost_projections": _cost_projections(unit, evaluation, spec),
    }


def render_scaling_strategy_markdown(strategy: dict[str, Any]) -> str:
    """Render a scaling strategy as a deterministic markdown handoff document."""
    summary = strategy.get("summary", {})
    source = strategy.get("source", {})

    lines = [
        f"# {_text(summary.get('title')) or _text(strategy.get('idea_id')) or 'Idea'} Scaling Strategy",
        "",
        f"- Schema version: {_text(strategy.get('schema_version'))}",
        f"- Idea ID: {_text(strategy.get('idea_id'))}",
        f"- Source status: {_text(source.get('status'))}",
        f"- Category: {_text(source.get('category'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Scaling approach: {_text(summary.get('scaling_approach'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    lines.extend(_section("Capacity Thresholds", _threshold_lines(strategy.get("capacity_thresholds") or [])))
    lines.extend(_section("Auto-Scaling Rules", _rule_lines(strategy.get("auto_scaling_rules") or [])))
    lines.extend(_section("Horizontal Scaling", _horizontal_lines(strategy.get("horizontal_scaling") or [])))
    lines.extend(_section("Vertical Scaling", _vertical_lines(strategy.get("vertical_scaling") or [])))
    lines.extend(_section("Cost Projections", _cost_lines(strategy.get("cost_projections") or [])))

    return "\n".join(lines).rstrip() + "\n"


def render_scaling_strategy_csv(strategy: dict[str, Any]) -> str:
    """Render a scaling strategy as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=SCALING_STRATEGY_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(strategy):
        writer.writerow(row)
    return output.getvalue()


def _scaling_approach(unit: BuildableUnit, spec: dict[str, Any]) -> str:
    stack = unit.suggested_stack or _spec_dict(spec, ("solution", "suggested_stack"))
    approach = _compact(unit.tech_approach) or _spec_text(spec, ("solution", "technical_approach"))

    if any(term in approach.lower() for term in ["serverless", "lambda", "function"]):
        return "serverless_auto_scaling"
    if any(term in approach.lower() for term in ["kubernetes", "k8s", "container"]):
        return "container_orchestration"
    if stack and any(key in ["database", "db", "cache"] for key in stack):
        return "hybrid_horizontal_vertical"
    return "on_demand_horizontal"


def _capacity_thresholds(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    thresholds = [
        _threshold(
            "threshold_cpu",
            "cpu_utilization",
            "percentage",
            70,
            "%",
            "Scale up when CPU exceeds this threshold.",
            ["solution.technical_approach", "execution.mvp_scope"],
        ),
        _threshold(
            "threshold_memory",
            "memory_utilization",
            "percentage",
            80,
            "%",
            "Scale up when memory exceeds this threshold.",
            ["solution.technical_approach"],
        ),
        _threshold(
            "threshold_response_time",
            "response_time",
            "latency",
            500,
            "ms",
            "Scale up when p95 response time exceeds this threshold.",
            ["execution.validation_plan"],
        ),
    ]

    if evaluation and evaluation.addressable_scale and evaluation.addressable_scale.value >= 7:
        thresholds.append(
            _threshold(
                "threshold_request_rate",
                "request_rate",
                "throughput",
                1000,
                "req/sec",
                "High addressable scale indicates need for request rate monitoring.",
                ["evaluation.addressable_scale"],
            )
        )

    return thresholds


def _auto_scaling_rules(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    rules = [
        _rule(
            "rule_scale_up_cpu",
            "scale_up",
            "cpu_utilization > 70%",
            300,
            "Increase instance count when CPU threshold is breached.",
            ["capacity_thresholds.threshold_cpu"],
        ),
        _rule(
            "rule_scale_down_cpu",
            "scale_down",
            "cpu_utilization < 30% for 10 minutes",
            600,
            "Decrease instance count when CPU is underutilized.",
            ["capacity_thresholds.threshold_cpu"],
        ),
    ]

    if evaluation and evaluation.addressable_scale and evaluation.addressable_scale.value >= 7:
        rules.append(
            _rule(
                "rule_burst_capacity",
                "burst_scale_up",
                "request_rate > 1000 req/sec",
                60,
                "Rapid scale-up for traffic bursts in high-scale scenarios.",
                ["evaluation.addressable_scale", "capacity_thresholds.threshold_request_rate"],
            )
        )

    return rules


def _horizontal_scaling(unit: BuildableUnit, spec: dict[str, Any]) -> list[dict[str, Any]]:
    scaling_approach = _scaling_approach(unit, spec)

    if scaling_approach == "serverless_auto_scaling":
        return [
            _horizontal(
                "horizontal_serverless",
                "serverless_functions",
                1,
                100,
                "Cloud provider manages instance count automatically.",
                ["solution.technical_approach", "solution.suggested_stack"],
            )
        ]

    return [
        _horizontal(
            "horizontal_web",
            "web_tier",
            2,
            10,
            "Web/API tier scales horizontally behind load balancer.",
            ["solution.technical_approach"],
        ),
        _horizontal(
            "horizontal_worker",
            "worker_tier",
            1,
            5,
            "Background worker tier for async processing.",
            ["solution.composability_notes"],
        ),
    ]


def _vertical_scaling(unit: BuildableUnit, spec: dict[str, Any]) -> list[dict[str, Any]]:
    scaling_approach = _scaling_approach(unit, spec)

    # Serverless approaches typically don't need vertical scaling configuration
    if scaling_approach == "serverless_auto_scaling":
        return []

    stack = unit.suggested_stack or _spec_dict(spec, ("solution", "suggested_stack"))

    if not stack or not any(key in ["database", "db", "cache", "data"] for key in stack):
        return []

    vertical_items = []

    # Only add database vertical scaling if database is in stack
    if any(key in ["database", "db"] for key in stack):
        vertical_items.append(
            _vertical(
                "vertical_database",
                "database_tier",
                "Scale database instance size for growing data volume.",
                ["solution.suggested_stack.database"],
            )
        )

    # Only add cache vertical scaling if cache is in stack
    if "cache" in stack:
        vertical_items.append(
            _vertical(
                "vertical_cache",
                "cache_tier",
                "Scale cache memory for increased working set size.",
                ["solution.suggested_stack.cache"],
            )
        )

    return vertical_items


def _cost_projections(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_monthly = 100.0

    if evaluation and evaluation.build_effort:
        effort_multiplier = max(1.0, evaluation.build_effort.value / 5.0)
        baseline_monthly *= effort_multiplier

    projections = [
        _projection(
            "cost_baseline",
            "Baseline monthly cost at minimum viable scale.",
            baseline_monthly,
            ["execution.mvp_scope"],
        ),
        _projection(
            "cost_moderate_scale",
            "Monthly cost at 10x baseline traffic.",
            baseline_monthly * 5.0,
            ["evaluation.addressable_scale"],
        ),
    ]

    if evaluation and evaluation.addressable_scale and evaluation.addressable_scale.value >= 7:
        projections.append(
            _projection(
                "cost_high_scale",
                "Monthly cost at 100x baseline traffic with high addressable scale.",
                baseline_monthly * 25.0,
                ["evaluation.addressable_scale"],
            )
        )

    return projections


def _threshold(
    threshold_id: str,
    metric_name: str,
    threshold_type: str,
    value: int | float,
    unit: str,
    notes: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": threshold_id,
        "metric_name": metric_name,
        "threshold_type": threshold_type,
        "value": value,
        "unit": unit,
        "notes": _compact(notes),
        "source_fields": source_fields,
    }


def _rule(
    rule_id: str,
    scaling_action: str,
    trigger_condition: str,
    cooldown_seconds: int,
    notes: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "scaling_action": scaling_action,
        "trigger_condition": _compact(trigger_condition),
        "cooldown_seconds": cooldown_seconds,
        "notes": _compact(notes),
        "source_fields": source_fields,
    }


def _horizontal(
    scaling_id: str,
    dimension: str,
    min_instances: int,
    max_instances: int,
    notes: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": scaling_id,
        "dimension": dimension,
        "min_instances": min_instances,
        "max_instances": max_instances,
        "notes": _compact(notes),
        "source_fields": source_fields,
    }


def _vertical(
    scaling_id: str,
    dimension: str,
    notes: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": scaling_id,
        "dimension": dimension,
        "notes": _compact(notes),
        "source_fields": source_fields,
    }


def _projection(
    projection_id: str,
    description: str,
    monthly_cost_usd: float,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": projection_id,
        "description": _compact(description),
        "monthly_cost_usd": monthly_cost_usd,
        "source_fields": source_fields,
    }


def _section(title: str, lines: list[str]) -> list[str]:
    result = [f"## {title}", ""]
    if not lines:
        result.extend(["None.", ""])
    else:
        result.extend(lines)
        result.append("")
    return result


def _threshold_lines(thresholds: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in thresholds:
        lines.extend([
            f"### {item.get('id')}: {_text(item.get('metric_name'))}",
            f"- Type: {_text(item.get('threshold_type'))}",
            f"- Value: {_text(item.get('value'))} {_text(item.get('unit'))}",
            f"- Notes: {_text(item.get('notes'))}",
            f"- Source fields: {_join_code(item.get('source_fields') or [])}",
            "",
        ])
    return lines


def _rule_lines(rules: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in rules:
        lines.extend([
            f"### {item.get('id')}: {_text(item.get('scaling_action'))}",
            f"- Trigger: {_text(item.get('trigger_condition'))}",
            f"- Cooldown: {_text(item.get('cooldown_seconds'))}s",
            f"- Notes: {_text(item.get('notes'))}",
            f"- Source fields: {_join_code(item.get('source_fields') or [])}",
            "",
        ])
    return lines


def _horizontal_lines(items: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in items:
        lines.extend([
            f"### {item.get('id')}: {_text(item.get('dimension'))}",
            f"- Min instances: {_text(item.get('min_instances'))}",
            f"- Max instances: {_text(item.get('max_instances'))}",
            f"- Notes: {_text(item.get('notes'))}",
            f"- Source fields: {_join_code(item.get('source_fields') or [])}",
            "",
        ])
    return lines


def _vertical_lines(items: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in items:
        lines.extend([
            f"### {item.get('id')}: {_text(item.get('dimension'))}",
            f"- Notes: {_text(item.get('notes'))}",
            f"- Source fields: {_join_code(item.get('source_fields') or [])}",
            "",
        ])
    return lines


def _cost_lines(projections: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in projections:
        lines.extend([
            f"### {item.get('id')}: ${_text(item.get('monthly_cost_usd'))}/month",
            f"- Description: {_text(item.get('description'))}",
            f"- Source fields: {_join_code(item.get('source_fields') or [])}",
            "",
        ])
    return lines


def _csv_rows(strategy: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    schema_version = strategy.get("schema_version")
    kind = strategy.get("kind")
    idea_id = strategy.get("idea_id")
    summary = strategy.get("summary", {})
    title = summary.get("title")

    for item in strategy.get("capacity_thresholds") or []:
        rows.append(
            _csv_row(
                schema_version=schema_version,
                kind=kind,
                idea_id=idea_id,
                title=title,
                section="capacity_thresholds",
                row_type="threshold",
                item_id=item.get("id"),
                metric_name=item.get("metric_name"),
                threshold_type=item.get("threshold_type"),
                threshold_value=item.get("value"),
                threshold_unit=item.get("unit"),
                notes=item.get("notes"),
                source_fields=item.get("source_fields"),
            )
        )

    for item in strategy.get("auto_scaling_rules") or []:
        rows.append(
            _csv_row(
                schema_version=schema_version,
                kind=kind,
                idea_id=idea_id,
                title=title,
                section="auto_scaling_rules",
                row_type="scaling_rule",
                item_id=item.get("id"),
                scaling_action=item.get("scaling_action"),
                trigger_condition=item.get("trigger_condition"),
                cooldown_period_seconds=item.get("cooldown_seconds"),
                notes=item.get("notes"),
                source_fields=item.get("source_fields"),
            )
        )

    for item in strategy.get("horizontal_scaling") or []:
        rows.append(
            _csv_row(
                schema_version=schema_version,
                kind=kind,
                idea_id=idea_id,
                title=title,
                section="horizontal_scaling",
                row_type="horizontal_config",
                item_id=item.get("id"),
                scaling_dimension=item.get("dimension"),
                scaling_type="horizontal",
                min_instances=item.get("min_instances"),
                max_instances=item.get("max_instances"),
                notes=item.get("notes"),
                source_fields=item.get("source_fields"),
            )
        )

    for item in strategy.get("vertical_scaling") or []:
        rows.append(
            _csv_row(
                schema_version=schema_version,
                kind=kind,
                idea_id=idea_id,
                title=title,
                section="vertical_scaling",
                row_type="vertical_config",
                item_id=item.get("id"),
                scaling_dimension=item.get("dimension"),
                scaling_type="vertical",
                notes=item.get("notes"),
                source_fields=item.get("source_fields"),
            )
        )

    for item in strategy.get("cost_projections") or []:
        rows.append(
            _csv_row(
                schema_version=schema_version,
                kind=kind,
                idea_id=idea_id,
                title=title,
                section="cost_projections",
                row_type="cost_projection",
                item_id=item.get("id"),
                projected_monthly_cost_usd=item.get("monthly_cost_usd"),
                notes=item.get("description"),
                source_fields=item.get("source_fields"),
            )
        )

    return rows


def _csv_row(
    *,
    schema_version: Any = None,
    kind: Any = None,
    idea_id: Any = None,
    title: Any = None,
    section: Any = None,
    row_type: Any = None,
    item_id: Any = None,
    metric_name: Any = None,
    threshold_type: Any = None,
    threshold_value: Any = None,
    threshold_unit: Any = None,
    scaling_dimension: Any = None,
    scaling_type: Any = None,
    scaling_action: Any = None,
    target_capacity: Any = None,
    min_instances: Any = None,
    max_instances: Any = None,
    cpu_threshold_percent: Any = None,
    memory_threshold_percent: Any = None,
    response_time_ms: Any = None,
    cost_per_unit_usd: Any = None,
    projected_monthly_cost_usd: Any = None,
    trigger_condition: Any = None,
    cooldown_period_seconds: Any = None,
    notes: Any = None,
    source_fields: Any = None,
) -> dict[str, str]:
    values = {
        "schema_version": schema_version,
        "kind": kind,
        "idea_id": idea_id,
        "title": title,
        "section": section,
        "row_type": row_type,
        "item_id": item_id,
        "metric_name": metric_name,
        "threshold_type": threshold_type,
        "threshold_value": threshold_value,
        "threshold_unit": threshold_unit,
        "scaling_dimension": scaling_dimension,
        "scaling_type": scaling_type,
        "scaling_action": scaling_action,
        "target_capacity": target_capacity,
        "min_instances": min_instances,
        "max_instances": max_instances,
        "cpu_threshold_percent": cpu_threshold_percent,
        "memory_threshold_percent": memory_threshold_percent,
        "response_time_ms": response_time_ms,
        "cost_per_unit_usd": cost_per_unit_usd,
        "projected_monthly_cost_usd": projected_monthly_cost_usd,
        "trigger_condition": trigger_condition,
        "cooldown_period_seconds": cooldown_period_seconds,
        "notes": notes,
        "source_fields": source_fields,
    }
    return {column: _csv_cell(values.get(column)) for column in SCALING_STRATEGY_CSV_COLUMNS}


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list | tuple | set):
        items = sorted(value, key=_csv_cell) if isinstance(value, set) else value
        return " | ".join(item for item in (_csv_cell(item) for item in items) if item)
    return str(value).strip()


def _spec_dict(spec: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    value = _spec_get(spec, path)
    return value if isinstance(value, dict) else {}


def _spec_text(spec: dict[str, Any], path: tuple[str, ...]) -> str:
    return _compact(_spec_get(spec, path))


def _spec_get(spec: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = spec
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _join_code(values: list[str]) -> str:
    items = [_compact(item) for item in values if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
