"""Deterministic KPI tree artifacts for persisted design briefs."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA_VERSION = "max.design_brief.kpi_tree.v1"

_HIGH_RISK_TERMS = (
    "compliance",
    "credential",
    "hipaa",
    "legal",
    "oauth",
    "pii",
    "privacy",
    "regulated",
    "security",
)


def generate_design_brief_kpi_tree(brief: Mapping[str, Any]) -> dict[str, Any]:
    """Generate a stable KPI tree from a persisted design brief payload."""
    brief_id = _clean(brief.get("id")) or "unknown-design-brief"
    title = _clean(brief.get("title")) or "Untitled Design Brief"
    source_idea_ids = _string_list(brief.get("source_idea_ids"))
    evidence_references = _evidence_references(brief, source_idea_ids)
    outcome_metrics = _outcome_metrics(brief, evidence_references)
    input_metrics = _input_metrics(brief, evidence_references)
    guardrail_metrics = _guardrail_metrics(brief, evidence_references)
    north_star = _north_star_metric(brief, title, outcome_metrics, evidence_references)

    return {
        "schema_version": SCHEMA_VERSION,
        "brief_id": brief_id,
        "title": title,
        "north_star_metric": north_star,
        "outcome_metrics": outcome_metrics,
        "input_metrics": input_metrics,
        "guardrail_metrics": guardrail_metrics,
        "measurement_plan": _measurement_plan(
            brief,
            north_star=north_star,
            outcome_metrics=outcome_metrics,
            input_metrics=input_metrics,
            guardrail_metrics=guardrail_metrics,
            evidence_references=evidence_references,
        ),
    }


def render_design_brief_kpi_tree_markdown(report: Mapping[str, Any]) -> str:
    """Render a KPI tree artifact as stable Markdown."""
    return render_kpi_tree_markdown(report)


def render_kpi_tree_markdown(report: Mapping[str, Any]) -> str:
    """Render a KPI tree artifact as stable Markdown."""
    north_star = _mapping(report.get("north_star_metric") or report.get("north_star"))
    measurement_plan = _mapping(report.get("measurement_plan"))
    title = _clean(report.get("title")) or "Untitled KPI Tree"
    schema_version = _clean(report.get("schema_version")) or SCHEMA_VERSION
    brief_id = _clean(report.get("brief_id")) or _clean(report.get("id")) or "unknown-design-brief"
    outcome_metrics = _metric_list(report.get("outcome_metrics") or report.get("supporting_metrics"))
    input_metrics = _metric_list(report.get("input_metrics") or report.get("leading_indicators"))
    guardrail_metrics = _metric_list(report.get("guardrail_metrics") or report.get("guardrails"))

    lines = [
        f"# KPI Tree: {title}",
        "",
        f"Schema: `{schema_version}`",
        f"Design brief: `{brief_id}`",
        "",
        "## North-Star Metric",
        "",
        f"- **Metric**: {_metric_name(north_star)}",
        f"- **Definition**: {_metric_text(north_star, 'definition')}",
        f"- **Target**: {_metric_text(north_star, 'target')}",
        f"- **Owner**: {_metric_text(north_star, 'owner')}",
        f"- **Cadence**: {_metric_text(north_star, 'cadence')}",
        f"- **Children**: {_inline_children(north_star.get('children'))}",
        f"- **Evidence/source ideas**: {_inline_refs(_string_list(north_star.get('source_reference_ids')))}",
        "",
        "## Metric Hierarchy",
        "",
        "Supporting metrics are listed as outcome metrics; leading indicators are listed as input metrics.",
        "",
        "### Outcome Metrics",
        "",
    ]
    _append_metrics(lines, outcome_metrics)
    lines.extend(["", "### Input Metrics", ""])
    _append_metrics(lines, input_metrics)
    lines.extend(["", "### Guardrail Metrics", ""])
    _append_metrics(lines, guardrail_metrics)

    lines.extend(
        [
            "",
            "## Measurement Plan",
            "",
            f"- Owner: {_metric_text(measurement_plan, 'owner')}",
            f"- Cadence: {_metric_text(measurement_plan, 'cadence')}",
            f"- Review ritual: {_metric_text(measurement_plan, 'review_ritual')}",
            f"- Primary data source: {_metric_text(measurement_plan, 'primary_data_source')}",
            f"- Evidence/source ideas: {_inline_refs(_source_reference_ids(report, measurement_plan))}",
            "",
            "### Instrumentation Events",
            "",
        ]
    )
    _append_instrumentation_events(lines, _metric_list(measurement_plan.get("instrumentation_events")))

    lines.extend(["", "### Instrumentation Gaps", ""])
    instrumentation_gaps = _instrumentation_gaps(report, measurement_plan)
    if instrumentation_gaps:
        lines.extend(f"- {gap}" for gap in instrumentation_gaps)
    else:
        lines.append("- None")

    lines.extend(["", "### Open Measurement Questions", ""])
    open_questions = _string_list(measurement_plan.get("open_questions"))
    if open_questions:
        lines.extend(f"- {question}" for question in open_questions)
    else:
        lines.append("- None")

    lines.extend(["", "### Evidence References", ""])
    evidence_references = _metric_list(report.get("evidence_references") or measurement_plan.get("evidence_references"))
    if evidence_references:
        for reference in evidence_references:
            lines.append(
                f"- **{_metric_text(reference, 'id')}** ({_metric_text(reference, 'type')}): "
                f"{_metric_text(reference, 'summary')}"
            )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def _north_star_metric(
    brief: Mapping[str, Any],
    title: str,
    outcome_metrics: list[dict[str, Any]],
    evidence_references: list[dict[str, str]],
) -> dict[str, Any]:
    user = _clean(brief.get("specific_user")) or "target user"
    workflow = _clean(brief.get("workflow_context")) or "the target workflow"
    readiness = _number(brief.get("readiness_score"))
    target_count = 3 if readiness >= 75 else 2 if readiness >= 50 else 1
    return {
        "id": "NS1",
        "metric": "Qualified workflow success",
        "definition": f"Qualified {user} teams complete {workflow} with {title} and confirm the outcome is worth repeating.",
        "target": f"{target_count}+ qualified teams reach repeatable workflow success within 30 days.",
        "owner": _owner_hint(brief, default="Product lead"),
        "cadence": "Weekly during validation, then monthly after launch",
        "children": [metric["id"] for metric in outcome_metrics],
        "source_fields": ["title", "specific_user", "workflow_context", "readiness_score"],
        "source_reference_ids": _reference_ids(evidence_references),
    }


def _outcome_metrics(
    brief: Mapping[str, Any],
    evidence_references: list[dict[str, str]],
) -> list[dict[str, Any]]:
    buyer = _clean(brief.get("buyer")) or "buyer"
    workflow = _clean(brief.get("workflow_context")) or "the target workflow"
    validation_plan = _clean(brief.get("validation_plan")) or "the first validation plan"
    return [
        _metric(
            "O1",
            "Validated demand",
            f"{buyer} or target users confirm the problem and expected outcome for {workflow}.",
            "5 completed discovery or validation conversations with 3+ strong-fit confirmations.",
            _owner_hint(brief, default="Product lead"),
            "Weekly during validation",
            ["buyer", "specific_user", "workflow_context", "validation_plan"],
            _reference_ids(evidence_references),
        ),
        _metric(
            "O2",
            "First value reached",
            f"Qualified users complete the first MVP value path described by {validation_plan}.",
            "50%+ of qualified pilot users reach first value within one business day of setup.",
            _owner_for_scope(_first(_string_list(brief.get("mvp_scope"))) or ""),
            "Weekly during pilot",
            ["mvp_scope", "validation_plan"],
            _reference_ids(evidence_references),
        ),
        _metric(
            "O3",
            "Repeat workflow intent",
            f"Activated users or {buyer} ask to repeat, continue, or expand {workflow}.",
            "3+ qualified accounts request a second session, pilot extension, or buying-path discussion.",
            "Product operations lead",
            "Biweekly through pilot",
            ["buyer", "workflow_context", "validation_plan"],
            _reference_ids(evidence_references),
        ),
    ]


def _input_metrics(
    brief: Mapping[str, Any],
    evidence_references: list[dict[str, str]],
) -> list[dict[str, Any]]:
    scope = _string_list(brief.get("mvp_scope"))
    milestones = _string_list(brief.get("first_milestones"))
    primary_scope = _first(scope) or "core MVP workflow"
    first_milestone = _first(milestones) or "first testable milestone"
    source_ids = _reference_ids(evidence_references)
    metrics = [
        _metric(
            "I1",
            "Qualified setup starts",
            f"Target users begin setup or first action for {primary_scope}.",
            "10 qualified setup starts or 5 qualified hands-on sessions before broad build expansion.",
            _owner_for_scope(primary_scope),
            "Weekly",
            ["mvp_scope", "specific_user"],
            source_ids,
            parent_id="O2",
        ),
        _metric(
            "I2",
            "Milestone acceptance",
            f"The team completes {first_milestone} with written acceptance criteria.",
            "1 working end-to-end slice accepted by product and engineering owners.",
            _owner_for_scope(primary_scope),
            "Weekly until accepted",
            ["first_milestones", "roadmap_items"],
            source_ids,
            parent_id="O2",
        ),
        _metric(
            "I3",
            "Evidence-backed scope decisions",
            "MVP scope changes retain traceability to source ideas, evidence, or validation findings.",
            "100% of added MVP scope items reference at least one source idea or validation result.",
            "Product operations lead",
            "At each scope review",
            ["source_idea_ids", "evidence_counts", "validation_plan"],
            source_ids,
            parent_id="O1",
        ),
    ]
    if len(scope) > 1:
        metrics.append(
            _metric(
                "I4",
                "Scope progression",
                f"Activated users attempt another scoped workflow step such as {scope[1]}.",
                "40%+ of activated users attempt a second scoped step within seven days.",
                _owner_for_scope(scope[1]),
                "Weekly during pilot",
                ["mvp_scope"],
                source_ids,
                parent_id="O3",
            )
        )
    return metrics


def _guardrail_metrics(
    brief: Mapping[str, Any],
    evidence_references: list[dict[str, str]],
) -> list[dict[str, Any]]:
    risks = _string_list(brief.get("risks"))
    readiness = _number(brief.get("readiness_score"))
    source_ids = _reference_ids(evidence_references)
    guardrails = [
        _metric(
            "G1",
            "Readiness floor",
            f"Design brief readiness remains at {readiness:.1f}/100 or improves as validation evidence is added.",
            "Do not expand implementation while readiness is below 70 without an explicit owner-approved exception.",
            "Product lead",
            "At each handoff review",
            ["readiness_score", "validation_plan"],
            source_ids,
        ),
        _metric(
            "G2",
            "Negative workflow impact",
            "Pilot users do not report a material regression in the target workflow.",
            "0 unresolved high-severity workflow regressions during validation or pilot use.",
            "Product operations lead",
            "Weekly during pilot",
            ["workflow_context", "risks"],
            source_ids,
        ),
    ]
    for index, risk in enumerate(risks[:2], start=3):
        guardrails.append(
            _metric(
                f"G{index}",
                f"Risk controlled: {_short_text(risk)}",
                risk,
                "Risk has a named owner, mitigation path, and stop criterion before pilot expansion.",
                _owner_for_risk(risk),
                "Weekly until mitigated",
                ["risks"],
                source_ids,
            )
        )
    if not risks:
        guardrails.append(
            _metric(
                "G3",
                "Uncaptured risk discovery",
                "New adoption, data, security, or workflow risks discovered during validation are captured.",
                "100% of material new risks are logged with owner and next action within one business day.",
                "Product operations lead",
                "Weekly during validation",
                ["risks"],
                source_ids,
            )
        )
    return guardrails


def _measurement_plan(
    brief: Mapping[str, Any],
    *,
    north_star: dict[str, Any],
    outcome_metrics: list[dict[str, Any]],
    input_metrics: list[dict[str, Any]],
    guardrail_metrics: list[dict[str, Any]],
    evidence_references: list[dict[str, str]],
) -> dict[str, Any]:
    workflow = _clean(brief.get("workflow_context")) or "target workflow"
    source_ids = _reference_ids(evidence_references)
    open_questions = []
    if not _clean(brief.get("specific_user")):
        open_questions.append("Name the specific user segment that qualifies KPI measurements.")
    if not _clean(brief.get("workflow_context")):
        open_questions.append("Define the workflow event that marks KPI tree success.")
    if not _string_list(brief.get("source_idea_ids")):
        open_questions.append("Attach source idea references so metric evidence has lineage.")

    return {
        "owner": _owner_hint(brief, default="Product operations lead"),
        "cadence": "Weekly KPI review during validation and pilot",
        "review_ritual": "Review north-star movement, outcome drivers, input progress, and triggered guardrails before changing MVP scope.",
        "primary_data_source": "Design brief validation log, pilot analytics, and source idea evidence",
        "metric_ids": [
            north_star["id"],
            *(metric["id"] for metric in outcome_metrics),
            *(metric["id"] for metric in input_metrics),
            *(metric["id"] for metric in guardrail_metrics),
        ],
        "instrumentation_events": [
            {
                "id": "E1",
                "event": "kpi_tree_reviewed",
                "description": "KPI tree reviewed against current design brief readiness and validation evidence.",
                "owner": "Product operations lead",
                "cadence": "Weekly",
                "source_reference_ids": source_ids,
            },
            {
                "id": "E2",
                "event": "qualified_workflow_success",
                "description": f"A qualified account completes {workflow} and confirms repeat value.",
                "owner": north_star["owner"],
                "cadence": north_star["cadence"],
                "source_reference_ids": source_ids,
            },
            {
                "id": "E3",
                "event": "guardrail_triggered",
                "description": "A guardrail threshold is hit and routed to the named owner.",
                "owner": "Product operations lead",
                "cadence": "As triggered",
                "source_reference_ids": source_ids,
            },
        ],
        "source_reference_ids": source_ids,
        "evidence_references": evidence_references,
        "open_questions": open_questions,
    }


def _metric(
    item_id: str,
    metric: str,
    definition: str,
    target: str,
    owner: str,
    cadence: str,
    source_fields: list[str],
    source_reference_ids: list[str],
    *,
    parent_id: str = "NS1",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "parent_id": parent_id,
        "metric": metric,
        "definition": definition,
        "target": target,
        "owner": owner,
        "cadence": cadence,
        "source_fields": source_fields,
        "source_reference_ids": source_reference_ids,
    }


def _evidence_references(brief: Mapping[str, Any], source_idea_ids: list[str]) -> list[dict[str, str]]:
    references = [
        {"id": f"idea:{idea_id}", "type": "source_idea", "summary": f"Source idea {idea_id}"}
        for idea_id in source_idea_ids
    ]
    evidence_counts = _evidence_counts(brief)
    if sum(evidence_counts.values()) > 0:
        references.append(
            {
                "id": "brief:evidence_counts",
                "type": "evidence_counts",
                "summary": (
                    f"{evidence_counts['signals']} signal(s), {evidence_counts['insights']} insight(s), "
                    f"{evidence_counts['source_ideas']} source idea reference(s)"
                ),
            }
        )
    validation_plan = _clean(brief.get("validation_plan"))
    if validation_plan:
        references.append({"id": "brief:validation_plan", "type": "validation_plan", "summary": validation_plan})
    if not references:
        references.append(
            {
                "id": "brief:fallback",
                "type": "fallback",
                "summary": "No source ideas or evidence counts were persisted; KPI tree uses brief-level fallback assumptions.",
            }
        )
    return references


def _evidence_counts(brief: Mapping[str, Any]) -> dict[str, int]:
    raw_counts = brief.get("evidence_counts")
    if isinstance(raw_counts, Mapping):
        return {
            "signals": _count(raw_counts.get("signals")),
            "insights": _count(raw_counts.get("insights")),
            "source_ideas": _count(raw_counts.get("source_ideas")),
        }
    return {
        "signals": len(_string_list(brief.get("evidence_signals") or brief.get("signal_ids"))),
        "insights": len(_string_list(brief.get("inspiring_insights") or brief.get("insight_ids"))),
        "source_ideas": len(_string_list(brief.get("source_idea_ids"))),
    }


def _append_metrics(lines: list[str], metrics: list[dict[str, Any]], *, level: int = 0) -> None:
    if not metrics:
        lines.append("- None")
        return

    for item in metrics:
        indent = "  " * level
        lines.extend(
            [
                f"{indent}- **{_metric_label(item)}** (parent: `{_metric_text(item, 'parent_id')}`)",
                f"{indent}  Definition: {_metric_text(item, 'definition')}",
                f"{indent}  Target: {_metric_text(item, 'target')}",
                f"{indent}  Owner: {_metric_text(item, 'owner')}",
                f"{indent}  Cadence: {_metric_text(item, 'cadence')}",
                f"{indent}  Children: {_inline_children(item.get('children'))}",
                f"{indent}  Evidence/source ideas: {_inline_refs(_string_list(item.get('source_reference_ids')))}",
            ]
        )
        children = _metric_list(item.get("children"))
        if children:
            _append_metrics(lines, children, level=level + 1)


def _owner_hint(brief: Mapping[str, Any], *, default: str) -> str:
    buyer = _clean(brief.get("buyer"))
    if buyer:
        return f"Product lead with {buyer}"
    return default


def _owner_for_scope(scope: str) -> str:
    lowered = scope.lower()
    if any(keyword in lowered for keyword in ("api", "cli", "integration", "github", "data")):
        return "Engineering lead"
    if any(keyword in lowered for keyword in ("research", "validation", "interview")):
        return "Research lead"
    return "Product engineer"


def _owner_for_risk(risk: str) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _HIGH_RISK_TERMS):
        return "Security and compliance owner"
    if any(term in lowered for term in ("api", "integration", "platform", "data")):
        return "Engineering lead"
    return "Product lead"


def _reference_ids(references: list[dict[str, str]]) -> list[str]:
    return [reference["id"] for reference in references]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, tuple):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    return [text] if text else []


def _first(items: list[str]) -> str:
    return items[0] if items else ""


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


def _short_text(value: str) -> str:
    cleaned = _clean(value)
    if len(cleaned) <= 72:
        return cleaned
    return cleaned[:69].rstrip() + "..."


def _inline_refs(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "`brief:fallback`"


def _append_instrumentation_events(lines: list[str], events: list[dict[str, Any]]) -> None:
    if not events:
        lines.append("- None")
        return

    for event in events:
        lines.append(
            f"- **{_metric_text(event, 'event') or _metric_text(event, 'id')}** "
            f"({_metric_text(event, 'owner')}, {_metric_text(event, 'cadence')}): "
            f"{_metric_text(event, 'description')}"
        )


def _instrumentation_gaps(report: Mapping[str, Any], measurement_plan: Mapping[str, Any]) -> list[str]:
    gaps = _gap_list(report.get("instrumentation_gaps"))
    if gaps:
        return gaps
    gaps = _gap_list(measurement_plan.get("instrumentation_gaps"))
    if gaps:
        return gaps
    return _string_list(measurement_plan.get("open_questions"))


def _source_reference_ids(report: Mapping[str, Any], measurement_plan: Mapping[str, Any]) -> list[str]:
    source_ids = _string_list(measurement_plan.get("source_reference_ids") or report.get("source_reference_ids"))
    if source_ids:
        return source_ids
    references = _metric_list(report.get("evidence_references") or measurement_plan.get("evidence_references"))
    return [_metric_text(reference, "id") for reference in references if _metric_text(reference, "id")]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _metric_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _gap_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return _string_list(value)

    gaps: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            text = (
                _clean(item.get("description"))
                or _clean(item.get("summary"))
                or _clean(item.get("message"))
                or _clean(item.get("id"))
            )
            if text:
                gaps.append(text)
        else:
            text = _clean(item)
            if text:
                gaps.append(text)
    return gaps


def _metric_label(metric: Mapping[str, Any]) -> str:
    metric_id = _metric_text(metric, "id")
    metric_name = _metric_name(metric)
    return f"{metric_id} {metric_name}".strip()


def _metric_name(metric: Mapping[str, Any]) -> str:
    return _clean(metric.get("metric")) or _clean(metric.get("name")) or "Untitled metric"


def _metric_text(metric: Mapping[str, Any], key: str) -> str:
    return _clean(metric.get(key)) or "Not specified"


def _inline_children(value: Any) -> str:
    if not isinstance(value, list | tuple):
        return "None"

    child_labels: list[str] = []
    for child in value:
        if isinstance(child, Mapping):
            child_id = _clean(child.get("id"))
            child_labels.append(f"`{child_id}`" if child_id else _metric_name(child))
        else:
            child_id = _clean(child)
            if child_id:
                child_labels.append(f"`{child_id}`")
    return ", ".join(child_labels) if child_labels else "None"
