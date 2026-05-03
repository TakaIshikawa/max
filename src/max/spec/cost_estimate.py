"""Generate deterministic cost estimates for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


COST_ESTIMATE_SCHEMA_VERSION = "max-cost-estimate/v1"
COST_ESTIMATE_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "source_idea_id",
    "title",
    "category",
    "item",
    "description",
    "estimate_type",
    "low_monthly_cost",
    "base_monthly_cost",
    "high_monthly_cost",
    "one_time_cost",
    "assumptions",
    "confidence",
    "notes",
)

_EXTERNAL_SERVICE_TERMS = {
    "ai": ("openai", "anthropic", "llm", "model", "embedding", "vector", "artificial intelligence"),
    "cloud": ("aws", "gcp", "azure", "s3", "lambda", "cloud", "kubernetes"),
    "crm": ("salesforce", "hubspot"),
    "messaging": ("slack", "teams", "discord"),
    "payments": ("stripe", "billing", "invoice"),
    "search": ("elasticsearch", "opensearch", "algolia"),
    "observability": ("datadog", "sentry", "new relic", "pagerduty"),
}

_OPERATIONAL_TERMS = {
    "on_call": ("on-call", "incident", "pager", "alert", "slo"),
    "data_storage": ("database", "postgres", "warehouse", "retention", "archive", "export"),
    "security_review": ("oauth", "sso", "secret", "token", "pii", "customer data"),
    "integration_support": ("webhook", "api", "sync", "adapter", "integration"),
    "pilot_support": ("pilot", "first 10", "customer", "validation", "feedback"),
}


def generate_cost_estimate(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic effort and cost guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    quality = spec.get("quality") if isinstance(spec.get("quality"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    signals = _complexity_signals(spec, solution, execution, evaluation)
    effort = _effort_estimate(signals, evaluation, quality)
    external_drivers = _external_service_cost_drivers(spec, solution)
    operational_drivers = _operational_cost_drivers(spec, execution, evaluation)
    cost_drivers = external_drivers + operational_drivers
    risks = _cost_risks(signals, cost_drivers, execution, evaluation, quality)
    recommendations = _recommendations(effort, cost_drivers, risks)

    return {
        "schema_version": COST_ESTIMATE_SCHEMA_VERSION,
        "kind": "max.cost_estimate",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "domain": source.get("domain"),
            "category": source.get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec",
            "workflow_context": _workflow(project),
            "target_user": _compact(project.get("specific_user") or project.get("target_users"))
            or "primary user",
            "buyer": _compact(project.get("buyer")) or "launch sponsor",
            "stack": _stack_label(solution.get("suggested_stack")),
            "effort_band": effort["band"],
            "estimated_engineering_days": effort["engineering_days"],
            "cost_driver_count": len(cost_drivers),
            "risk_count": len(risks),
            "recommendation": evaluation.get("recommendation") if evaluation else None,
            "overall_score": evaluation.get("overall_score") if evaluation else None,
        },
        "cost_drivers": cost_drivers,
        "effort_estimate": effort,
        "risks": risks,
        "recommendations": recommendations,
    }


def render_cost_estimate_markdown(estimate: dict[str, Any]) -> str:
    """Render a generated cost estimate as a stable markdown handoff document."""
    summary = estimate.get("summary", {})
    source = estimate.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Cost Estimate",
        "",
        f"- Schema version: {_text(estimate.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Effort band: {_text(summary.get('effort_band'))}",
        f"- Estimated engineering days: {_text(summary.get('estimated_engineering_days'))}",
        "",
    ]

    lines.extend(_render_effort(estimate.get("effort_estimate") or {}))
    _extend_section(lines, "Cost Drivers", estimate.get("cost_drivers") or [], _render_driver)
    _extend_section(lines, "Risks", estimate.get("risks") or [], _render_risk)
    _extend_section(lines, "Recommendations", estimate.get("recommendations") or [], _render_recommendation)
    return "\n".join(lines).rstrip() + "\n"


def render_cost_estimate_csv(estimate: dict[str, Any]) -> str:
    """Render cost estimate line items as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=COST_ESTIMATE_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(estimate or {}):
        writer.writerow(row)
    return output.getvalue()


def _complexity_signals(
    spec: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    stack_components = _stack_components(solution.get("suggested_stack"))
    scope_items = [_compact(item) for item in _list(execution.get("mvp_scope")) if _compact(item)]
    risks = [_compact(item) for item in _list(execution.get("risks")) if _compact(item)]
    weaknesses = [_compact(item) for item in _list(evaluation.get("weaknesses")) if _compact(item)]
    text = _haystack(spec)
    external_categories = _detected_categories(text, _EXTERNAL_SERVICE_TERMS)
    operational_categories = _detected_categories(text, _OPERATIONAL_TERMS)

    return {
        "stack_component_count": len(stack_components),
        "scope_item_count": len(scope_items),
        "risk_count": len(risks),
        "weakness_count": len(weaknesses),
        "external_category_count": len(external_categories),
        "operational_category_count": len(operational_categories),
        "mentions_auth_or_pii": _contains_any(
            text, ("oauth", "sso", "auth", "pii", "customer data", "personal data")
        ),
        "mentions_realtime_or_scale": _contains_any(
            text, ("real-time", "realtime", "stream", "queue", "scale", "high volume")
        ),
        "external_categories": external_categories,
        "operational_categories": operational_categories,
    }


def _effort_estimate(
    signals: dict[str, Any],
    evaluation: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    score = 1
    score += min(signals["stack_component_count"], 5)
    score += min(signals["scope_item_count"], 5)
    score += signals["external_category_count"] * 2
    score += signals["operational_category_count"]
    score += min(signals["risk_count"], 4)
    score += min(signals["weakness_count"], 3)
    if signals["mentions_auth_or_pii"]:
        score += 2
    if signals["mentions_realtime_or_scale"]:
        score += 2

    dimensions = evaluation.get("dimensions") if isinstance(evaluation.get("dimensions"), dict) else {}
    build_effort = dimensions.get("build_effort") if isinstance(dimensions.get("build_effort"), dict) else {}
    if isinstance(build_effort.get("value"), int | float):
        score += max(0, int(round(float(build_effort["value"]) - 5)))
    quality_score = quality.get("quality_score")
    if isinstance(quality_score, int | float) and quality_score < 0.5:
        score += 1

    if score <= 6:
        band, days, confidence = "low", "2-5", "medium"
    elif score <= 21:
        band, days, confidence = "medium", "6-15", "medium"
    else:
        band, days, confidence = "high", "16-30", "low"

    return {
        "band": band,
        "complexity_score": score,
        "engineering_days": days,
        "confidence": confidence,
        "basis": [
            f"{signals['scope_item_count']} MVP scope item(s)",
            f"{signals['stack_component_count']} stack component(s)",
            f"{signals['external_category_count']} external service cost category/categories",
            f"{signals['risk_count']} execution risk(s)",
            f"{signals['weakness_count']} evaluation weakness(es)",
        ],
    }


def _external_service_cost_drivers(
    spec: dict[str, Any], solution: dict[str, Any]
) -> list[dict[str, Any]]:
    text = _haystack(spec)
    drivers: list[dict[str, Any]] = []
    for index, category in enumerate(_detected_categories(text, _EXTERNAL_SERVICE_TERMS), start=1):
        drivers.append(
            _driver(
                f"EXT{index}",
                "external_service",
                category,
                _impact(category, "external"),
                f"Usage-based or subscription spend may increase for {category.replace('_', ' ')} services.",
                ["solution.suggested_stack", "solution.technical_approach"],
            )
        )
    if not drivers and _stack_components(solution.get("suggested_stack")):
        drivers.append(
            _driver(
                "EXT1",
                "external_service",
                "runtime_dependencies",
                "low",
                "Stack dependencies appear implementation-owned; confirm whether any managed services are required.",
                ["solution.suggested_stack"],
            )
        )
    return drivers


def _operational_cost_drivers(
    spec: dict[str, Any],
    execution: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    text = _haystack(spec)
    drivers: list[dict[str, Any]] = []
    for index, category in enumerate(_detected_categories(text, _OPERATIONAL_TERMS), start=1):
        drivers.append(
            _driver(
                f"OPS{index}",
                "operational",
                category,
                _impact(category, "operational"),
                f"Run, support, or governance work is likely for {category.replace('_', ' ')}.",
                ["execution.validation_plan", "execution.risks", "evaluation.weaknesses"],
            )
        )
    if _list(execution.get("first_10_customers")):
        drivers.append(
            _driver(
                f"OPS{len(drivers) + 1}",
                "operational",
                "pilot_coordination",
                "medium",
                "First customer rollout adds coordination, support, and feedback triage time.",
                ["execution.first_10_customers"],
            )
        )
    if evaluation.get("recommendation") in {"no", "maybe"}:
        drivers.append(
            _driver(
                f"OPS{len(drivers) + 1}",
                "operational",
                "validation_rework",
                "medium",
                "Evaluation recommendation suggests additional validation or scope trimming before build.",
                ["evaluation.recommendation", "evaluation.weaknesses"],
            )
        )
    return drivers


def _cost_risks(
    signals: dict[str, Any],
    cost_drivers: list[dict[str, Any]],
    execution: dict[str, Any],
    evaluation: dict[str, Any],
    quality: dict[str, Any],
) -> list[dict[str, Any]]:
    risks = [
        _risk(
            "CR1",
            "scope_growth",
            "medium" if signals["scope_item_count"] > 2 else "low",
            "MVP scope can expand during implementation if acceptance boundaries are not explicit.",
            ["execution.mvp_scope"],
            "Freeze pilot acceptance criteria before adding integrations or workflow variants.",
        )
    ]
    if any(driver["impact"] == "high" for driver in cost_drivers):
        risks.append(
            _risk(
                "CR2",
                "usage_based_spend",
                "high",
                "High-impact service drivers can create variable spend once real users or data volumes arrive.",
                ["solution.suggested_stack", "solution.technical_approach"],
                "Set budgets, rate limits, and fixture-based load assumptions before pilot launch.",
            )
        )
    if signals["mentions_auth_or_pii"]:
        risks.append(
            _risk(
                "CR3",
                "security_and_privacy_review",
                "high",
                "Authentication, secrets, or customer data can add review and remediation effort.",
                ["project", "solution", "execution.risks"],
                "Keep sensitive data out of the first milestone or use sandbox fixtures until controls are reviewed.",
            )
        )
    if evaluation.get("weaknesses") or quality.get("rejection_tags"):
        risks.append(
            _risk(
                "CR4",
                "validation_rework",
                "medium",
                "Weaknesses or quality concerns can turn into rework after the build starts.",
                ["evaluation.weaknesses", "quality.rejection_tags"],
                "Convert each weakness into a test, non-goal, or explicit follow-up before implementation.",
            )
        )
    return risks


def _recommendations(
    effort: dict[str, Any],
    cost_drivers: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "id": "REC1",
            "priority": "high",
            "recommendation": "Build the first milestone with fixture data and one primary workflow path.",
            "expected_savings": "Reduces integration and support cost while proving the value path.",
        },
        {
            "id": "REC2",
            "priority": "medium",
            "recommendation": "Add budget counters or usage logging for every external service driver.",
            "expected_savings": "Makes variable spend visible before pilot usage expands.",
        },
    ]
    if effort.get("band") == "high":
        recommendations.insert(
            1,
            {
                "id": "REC3",
                "priority": "high",
                "recommendation": "Split implementation into a low-cost discovery spike and a separately approved build.",
                "expected_savings": "Avoids committing full build effort before cost assumptions are tested.",
            },
        )
    if any(risk["severity"] == "high" for risk in risks):
        recommendations.append(
            {
                "id": "REC4",
                "priority": "high",
                "recommendation": "Gate launch on resolving high-severity cost risks or accepting them with an owner.",
                "expected_savings": "Prevents avoidable review, incident, or usage-spend surprises.",
            }
        )
    if not cost_drivers:
        recommendations.append(
            {
                "id": "REC5",
                "priority": "low",
                "recommendation": "Keep dependencies local until a concrete managed-service need appears.",
                "expected_savings": "Preserves the low-cost profile of the current spec.",
            }
        )
    return recommendations


def _driver(
    driver_id: str,
    category: str,
    name: str,
    impact: str,
    description: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": driver_id,
        "category": category,
        "name": name,
        "impact": impact,
        "description": _compact(description),
        "derived_from": derived_from,
    }


def _risk(
    risk_id: str,
    name: str,
    severity: str,
    description: str,
    derived_from: list[str],
    mitigation: str,
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "name": name,
        "severity": severity,
        "description": _compact(description),
        "derived_from": derived_from,
        "mitigation": _compact(mitigation),
    }


def _impact(category: str, driver_type: str) -> str:
    if category in {"ai", "cloud", "payments", "on_call", "security_review"}:
        return "high"
    if driver_type == "external" or category in {"data_storage", "integration_support", "pilot_support"}:
        return "medium"
    return "low"


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_effort(effort: dict[str, Any]) -> list[str]:
    return [
        "## Effort Estimate",
        "",
        f"- Band: {_text(effort.get('band'))}",
        f"- Complexity score: {_text(effort.get('complexity_score'))}",
        f"- Engineering days: {_text(effort.get('engineering_days'))}",
        f"- Confidence: {_text(effort.get('confidence'))}",
        "- Basis:",
        *_bullets(effort.get("basis")),
        "",
    ]


def _render_driver(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Impact: {_text(item.get('impact'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_risk(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Mitigation: {_text(item.get('mitigation'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_recommendation(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('priority'))}",
        f"- Recommendation: {_text(item.get('recommendation'))}",
        f"- Expected savings: {_text(item.get('expected_savings'))}",
    ]


def _csv_rows(estimate: dict[str, Any]) -> list[dict[str, str]]:
    line_items = _cost_line_items(estimate)
    return [_csv_row(estimate, item) for item in line_items]


def _cost_line_items(estimate: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("cost_line_items", "line_items", "cost_items"):
        items = estimate.get(key)
        if isinstance(items, list):
            return [item if isinstance(item, dict) else {"item": item} for item in items]

    drivers = estimate.get("cost_drivers")
    if isinstance(drivers, list):
        return [driver for driver in drivers if isinstance(driver, dict)]
    return []


def _csv_row(estimate: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    summary = estimate.get("summary") if isinstance(estimate.get("summary"), dict) else {}
    source = estimate.get("source") if isinstance(estimate.get("source"), dict) else {}
    monthly = _dict(item.get("monthly_cost") or item.get("monthly_estimate"))
    effort = estimate.get("effort_estimate") if isinstance(estimate.get("effort_estimate"), dict) else {}
    return {
        "schema_version": _csv_text(estimate.get("schema_version")),
        "kind": _csv_text(estimate.get("kind")),
        "source_idea_id": _csv_text(source.get("idea_id")),
        "title": _csv_text(summary.get("title")),
        "category": _csv_text(item.get("category")),
        "item": _csv_text(
            item.get("item")
            or item.get("name")
            or item.get("title")
            or item.get("id")
        ),
        "description": _csv_text(item.get("description")),
        "estimate_type": _csv_text(
            item.get("estimate_type")
            or item.get("cost_type")
            or item.get("type")
            or ("driver" if item.get("impact") else "")
        ),
        "low_monthly_cost": _csv_text(
            _first_present(
                item,
                "low_monthly_cost",
                "monthly_cost_low",
                "low_monthly",
                "monthly_low",
                fallback=monthly.get("low"),
            )
        ),
        "base_monthly_cost": _csv_text(
            _first_present(
                item,
                "base_monthly_cost",
                "monthly_cost_base",
                "base_monthly",
                "monthly_base",
                fallback=_first_non_none(
                    monthly.get("base"),
                    _monthly_scalar(item.get("monthly_cost")),
                ),
            )
        ),
        "high_monthly_cost": _csv_text(
            _first_present(
                item,
                "high_monthly_cost",
                "monthly_cost_high",
                "high_monthly",
                "monthly_high",
                fallback=monthly.get("high"),
            )
        ),
        "one_time_cost": _csv_text(
            _first_present(
                item,
                "one_time_cost",
                "one_time",
                "one_time_estimate",
                "setup_cost",
            )
        ),
        "assumptions": _csv_join(item.get("assumptions")),
        "confidence": _csv_text(item.get("confidence") or effort.get("confidence")),
        "notes": _csv_join(
            item.get("notes")
            or item.get("note")
            or item.get("derived_from")
            or item.get("source_references")
        ),
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_present(mapping: dict[str, Any], *keys: str, fallback: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return fallback


def _monthly_scalar(value: Any) -> Any:
    return None if isinstance(value, dict) else value


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _detected_categories(text: str, categories: dict[str, tuple[str, ...]]) -> list[str]:
    detected = [category for category, terms in sorted(categories.items()) if _contains_any(text, terms)]
    return list(dict.fromkeys(detected))


def _haystack(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_haystack(value[key]) for key in sorted(value)).lower()
    if isinstance(value, list | tuple):
        return " ".join(_haystack(item) for item in value).lower()
    return _compact(value).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _workflow(project: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        values = [f"{key}={stack[key]}" for key in sorted(stack) if _compact(stack[key])]
        if values:
            return ", ".join(values)
    return "unspecified"


def _stack_components(stack: Any) -> list[str]:
    if not isinstance(stack, dict):
        return []
    return [_compact(value) for key, value in sorted(stack.items()) if key and _compact(value)]


def _bullets(values: Any) -> list[str]:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    return [f"  - {item}" for item in items] if items else ["  - None."]


def _join_code(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return _compact(value)


def _csv_join(values: Any) -> str:
    if isinstance(values, list | tuple):
        return " | ".join(_csv_text(value) for value in values if _csv_text(value))
    return _csv_text(values)
