"""Deterministic success-metrics reports for persisted design briefs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "max.design_brief.success_metrics.v1"

_HIGH_RISK_TERMS = (
    "compliance",
    "credential",
    "legal",
    "pii",
    "privacy",
    "regulated",
    "security",
)


def build_design_brief_success_metrics(design_brief: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-ready success metrics report from a persisted design brief payload."""
    brief_id = _clean(design_brief.get("id")) or "unknown-design-brief"
    title = _clean(design_brief.get("title")) or "Untitled Design Brief"
    readiness_score = _number(design_brief.get("readiness_score"))
    workflow = _clean(design_brief.get("workflow_context"))
    validation_plan = _clean(design_brief.get("validation_plan"))
    risks = _string_list(design_brief.get("risks"))
    evidence_counts = _evidence_counts(design_brief)
    missing_inputs = _missing_inputs(design_brief, evidence_counts)

    return {
        "schema_version": SCHEMA_VERSION,
        "brief_id": brief_id,
        "title": title,
        "north_star_metric": _north_star_metric(
            design_brief,
            title=title,
            workflow=workflow,
            readiness_score=readiness_score,
        ),
        "activation_metrics": _activation_metrics(design_brief, workflow=workflow),
        "retention_metrics": _retention_metrics(design_brief, workflow=workflow),
        "validation_metrics": _validation_metrics(
            design_brief,
            validation_plan=validation_plan,
            readiness_score=readiness_score,
            evidence_counts=evidence_counts,
        ),
        "risk_guardrails": _risk_guardrails(design_brief, risks=risks),
        "instrumentation_events": _instrumentation_events(design_brief, workflow=workflow),
        "missing_inputs": missing_inputs,
    }


def render_design_brief_success_metrics(report: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Render a success metrics report as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported success metrics format: {fmt}")

    north_star = report["north_star_metric"]
    lines = [
        f"# Success Metrics: {report['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{report['brief_id']}`",
        "",
        "## North Star Metric",
        "",
        f"- **Metric**: {north_star['metric']}",
        f"- **Definition**: {north_star['definition']}",
        f"- **Target**: {north_star['target']}",
        f"- **Confidence**: `{north_star['confidence']}`",
        "",
        north_star["rationale"],
        "",
        "## Activation Metrics",
        "",
    ]
    _append_metric_list(lines, report["activation_metrics"])

    lines.extend(["", "## Retention Metrics", ""])
    _append_metric_list(lines, report["retention_metrics"])

    lines.extend(["", "## Validation Metrics", ""])
    _append_metric_list(lines, report["validation_metrics"])

    lines.extend(["", "## Risk Guardrails", ""])
    for item in report["risk_guardrails"]:
        lines.extend(
            [
                f"- **{item['metric']}** (`{item['severity']}`): {item['threshold']}",
                f"  Action: {item['action']}",
            ]
        )

    lines.extend(["", "## Instrumentation Events", ""])
    for item in report["instrumentation_events"]:
        lines.extend(
            [
                f"- **{item['event']}**: {item['description']}",
                f"  Properties: {_inline(item['properties'])}",
            ]
        )

    lines.extend(["", "## Missing Inputs", ""])
    if report["missing_inputs"]:
        lines.extend(f"- **{item['field']}**: {item['reason']}" for item in report["missing_inputs"])
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def write_design_brief_success_metrics(
    path: Path,
    report: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_design_brief_success_metrics(report, fmt=fmt), encoding="utf-8")


def success_metrics_filename(design_brief: dict[str, Any], *, fmt: str) -> str:
    extension = "json" if fmt == "json" else "md"
    return f"{_filename_part(_clean(design_brief.get('id')) or 'design-brief')}-success-metrics.{extension}"


def _north_star_metric(
    design_brief: dict[str, Any],
    *,
    title: str,
    workflow: str,
    readiness_score: float,
) -> dict[str, Any]:
    user = _clean(design_brief.get("specific_user")) or "target user"
    concept = _clean(design_brief.get("merged_product_concept")) or title
    workflow_text = workflow or "the target workflow"
    target_count = 3 if readiness_score >= 75 else 2 if readiness_score >= 50 else 1

    return {
        "metric": "Qualified workflow success",
        "definition": (
            f"Number of qualified {user} teams that complete {workflow_text} with {title} "
            "and confirm the outcome is worth repeating."
        ),
        "target": f"{target_count}+ qualified teams complete the workflow and confirm repeat value within 30 days.",
        "rationale": f"The concept centers on {concept}, so success should measure completed workflow value instead of usage alone.",
        "confidence": "high" if workflow and readiness_score >= 75 else "medium" if workflow else "low",
        "source_fields": ["title", "specific_user", "workflow_context", "merged_product_concept", "readiness_score"],
    }


def _activation_metrics(design_brief: dict[str, Any], *, workflow: str) -> list[dict[str, Any]]:
    scope = _string_list(design_brief.get("mvp_scope"))
    first_scope = scope[0] if scope else "the primary MVP action"
    workflow_text = workflow or "the target workflow"
    metrics = [
        _metric(
            "A1",
            "Qualified setup completion",
            f"Target users complete setup for {workflow_text}.",
            "60%+ of qualified users who start setup reach a configured state during the first session.",
            "Confirms the product can get users to a usable state without hands-on implementation help.",
            ["workflow_context", "specific_user"],
        ),
        _metric(
            "A2",
            "First value reached",
            f"Target users complete {first_scope} and see a useful output.",
            "50%+ of qualified users who finish setup reach first value within one business day.",
            "Connects activation to the first MVP promise captured in the persisted scope.",
            ["mvp_scope"],
        ),
    ]
    if len(scope) > 1:
        metrics.append(
            _metric(
                "A3",
                "MVP scope progression",
                "Activated users attempt a second MVP scope item.",
                "40%+ of activated users attempt another scoped workflow step within seven days.",
                "Separates shallow setup from progression across the planned MVP surface.",
                ["mvp_scope"],
            )
        )
    return metrics


def _retention_metrics(design_brief: dict[str, Any], *, workflow: str) -> list[dict[str, Any]]:
    buyer = _clean(design_brief.get("buyer")) or "buyer"
    workflow_text = workflow or "the target workflow"
    return [
        _metric(
            "R1",
            "Repeat workflow usage",
            f"Activated users return to run {workflow_text} again.",
            "35%+ of activated accounts repeat the core workflow within 14 days.",
            "Repeat use is the clearest early signal that the workflow is recurring rather than a one-time curiosity.",
            ["workflow_context"],
        ),
        _metric(
            "R2",
            "Pilot continuation intent",
            f"{buyer} or the primary user asks to continue, expand, or review a pilot.",
            "3+ qualified accounts request a second session, pilot extension, or buying-path discussion.",
            "Early retention should include human pull from the buyer path when long-term usage data is not available.",
            ["buyer", "validation_plan"],
        ),
    ]


def _validation_metrics(
    design_brief: dict[str, Any],
    *,
    validation_plan: str,
    readiness_score: float,
    evidence_counts: dict[str, int],
) -> list[dict[str, Any]]:
    total_evidence = sum(evidence_counts.values())
    source_count = len(_string_list(design_brief.get("source_idea_ids")))
    return [
        _metric(
            "V1",
            "Validation plan completion",
            validation_plan or "A validation plan is defined and executed before build scale-up.",
            "Complete the first validation step with a written pass/fail decision before expanding implementation.",
            "Keeps implementation tied to a measurable validation gate.",
            ["validation_plan"],
        ),
        _metric(
            "V2",
            "Evidence coverage",
            f"Persisted evidence includes {total_evidence} linked evidence item(s) across {source_count} source idea(s).",
            "Maintain at least one source idea and one supporting evidence signal, insight, or evidence count.",
            "Autonomous implementers need traceable evidence before trusting the brief direction.",
            ["source_idea_ids", "evidence_counts"],
        ),
        _metric(
            "V3",
            "Readiness threshold",
            f"Current readiness score is {readiness_score:.1f}/100.",
            "Keep readiness at or above 70 before assigning broad implementation work.",
            "Readiness gives a deterministic guard against building from a weak brief.",
            ["readiness_score"],
        ),
    ]


def _risk_guardrails(design_brief: dict[str, Any], *, risks: list[str]) -> list[dict[str, Any]]:
    guardrails: list[dict[str, Any]] = [
        {
            "id": "G1",
            "metric": "Negative workflow impact",
            "threshold": "No pilot account reports a material regression in the target workflow.",
            "severity": "high",
            "action": "Pause rollout, capture the failing workflow step, and revise the MVP boundary.",
            "source_fields": ["workflow_context", "risks"],
        }
    ]
    for index, risk in enumerate(risks[:3], start=2):
        severity = "high" if _contains_high_risk_term(risk) else "medium"
        guardrails.append(
            {
                "id": f"G{index}",
                "metric": f"Risk controlled: {risk}",
                "threshold": "Risk is observed in no more than one qualified pilot account before mitigation.",
                "severity": severity,
                "action": "Convert the risk into an owner, mitigation, and explicit stop criterion before continuing.",
                "source_fields": ["risks"],
            }
        )
    if not risks:
        guardrails.append(
            {
                "id": "G2",
                "metric": "Uncaptured risk discovery",
                "threshold": "Any severe adoption, data, security, or workflow risk discovered during validation is logged before build expansion.",
                "severity": "medium",
                "action": "Add the discovered risk to the design brief and rerun the success metrics export.",
                "source_fields": ["risks"],
            }
        )
    return guardrails


def _instrumentation_events(design_brief: dict[str, Any], *, workflow: str) -> list[dict[str, Any]]:
    scope = _string_list(design_brief.get("mvp_scope"))
    workflow_text = workflow or "target workflow"
    events = [
        {
            "id": "E1",
            "event": "success_metrics_report_generated",
            "description": "Success metrics were exported for a persisted design brief.",
            "properties": ["brief_id", "schema_version", "readiness_score", "source_idea_count"],
        },
        {
            "id": "E2",
            "event": "activation_started",
            "description": f"A qualified user starts setup or first action for {workflow_text}.",
            "properties": ["brief_id", "account_id", "user_role", "workflow_context", "started_at"],
        },
        {
            "id": "E3",
            "event": "first_value_reached",
            "description": "A qualified user reaches the first useful MVP output.",
            "properties": ["brief_id", "account_id", "mvp_scope_item", "time_to_value_minutes"],
        },
        {
            "id": "E4",
            "event": "workflow_repeated",
            "description": "An activated account repeats the core workflow after first value.",
            "properties": ["brief_id", "account_id", "days_since_activation", "workflow_run_count"],
        },
        {
            "id": "E5",
            "event": "guardrail_triggered",
            "description": "A risk guardrail threshold is hit during validation or pilot use.",
            "properties": ["brief_id", "account_id", "guardrail_id", "severity", "mitigation_owner"],
        },
    ]
    if len(scope) > 1:
        events.append(
            {
                "id": "E6",
                "event": "mvp_scope_item_attempted",
                "description": "A user attempts an additional MVP scope item after first value.",
                "properties": ["brief_id", "account_id", "mvp_scope_item", "attempt_number"],
            }
        )
    return events


def _missing_inputs(design_brief: dict[str, Any], evidence_counts: dict[str, int]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    required_fields = (
        ("id", "Design brief id is needed for stable attribution."),
        ("title", "Title is needed to label the report and north star metric."),
        ("specific_user", "Specific user is needed to qualify activation and retention metrics."),
        ("workflow_context", "Workflow context is needed to define the core success event."),
        ("merged_product_concept", "Product concept is needed to connect metrics to delivered value."),
        ("validation_plan", "Validation plan is needed for pass/fail validation metrics."),
    )
    for field, reason in required_fields:
        if not _clean(design_brief.get(field)):
            missing.append({"field": field, "reason": reason})
    if not _string_list(design_brief.get("mvp_scope")):
        missing.append({"field": "mvp_scope", "reason": "MVP scope is needed to define first-value and progression metrics."})
    if not _string_list(design_brief.get("risks")):
        missing.append({"field": "risks", "reason": "Risks are needed to create specific guardrail thresholds."})
    if not _string_list(design_brief.get("source_idea_ids")):
        missing.append({"field": "source_idea_ids", "reason": "Source idea lineage is needed to judge evidence coverage."})
    if sum(evidence_counts.values()) == 0:
        missing.append({"field": "evidence_counts", "reason": "Evidence counts are missing, so validation metrics rely on source idea lineage only."})
    return missing


def _evidence_counts(design_brief: dict[str, Any]) -> dict[str, int]:
    raw_counts = design_brief.get("evidence_counts")
    if isinstance(raw_counts, dict):
        return {
            "signals": _count(raw_counts.get("signals")),
            "insights": _count(raw_counts.get("insights")),
            "source_ideas": _count(raw_counts.get("source_ideas")),
        }
    return {
        "signals": len(_string_list(design_brief.get("evidence_signals") or design_brief.get("signal_ids"))),
        "insights": len(_string_list(design_brief.get("inspiring_insights") or design_brief.get("insight_ids"))),
        "source_ideas": len(_string_list(design_brief.get("source_idea_ids"))),
    }


def _metric(
    item_id: str,
    metric: str,
    definition: str,
    target: str,
    rationale: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "metric": metric,
        "definition": definition,
        "target": target,
        "rationale": rationale,
        "source_fields": source_fields,
    }


def _append_metric_list(lines: list[str], metrics: list[dict[str, Any]]) -> None:
    for item in metrics:
        lines.extend(
            [
                f"- **{item['metric']}**: {item['definition']}",
                f"  Target: {item['target']}",
                f"  Rationale: {item['rationale']}",
            ]
        )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, tuple):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    return [text] if text else []


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _contains_high_risk_term(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _HIGH_RISK_TERMS)


def _inline(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
