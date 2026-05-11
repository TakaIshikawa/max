"""Shared helpers for deterministic TactSpec planning reports."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any, Callable


CSV_COLUMNS = (
    "section",
    "type",
    "source_id",
    "title",
    "strictness",
    "item_id",
    "name",
    "owner",
    "severity",
    "timing",
    "condition",
    "action",
    "description",
    "references",
    "evidence_refs",
)


def context(tact_spec: dict[str, Any]) -> dict[str, Any]:
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    risks = string_list(execution.get("risks"))
    score = number(evaluation.get("overall_score"))
    recommendation = compact(evaluation.get("recommendation"))
    risk_level = classify_risk(risks, score, recommendation)
    strictness = "strict" if risk_level == "high" else "standard"
    evidence = evidence_references(spec)
    stack = solution.get("suggested_stack") if isinstance(solution.get("suggested_stack"), dict) else {}

    return {
        "source": {
            "system": compact(source.get("system")) or "max",
            "type": compact(source.get("type")) or "tact_spec",
            "idea_id": compact(source.get("idea_id")),
            "status": compact(source.get("status")),
            "domain": compact(source.get("domain")),
            "category": compact(source.get("category")),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(evidence),
        },
        "title": compact(project.get("title")) or compact(source.get("idea_id")) or "Untitled TactSpec",
        "workflow_context": compact(project.get("workflow_context")) or "primary workflow",
        "target_user": compact(project.get("specific_user") or project.get("target_users")) or "primary user",
        "buyer": compact(project.get("buyer")) or "launch sponsor",
        "validation_plan": compact(execution.get("validation_plan")) or "repeatable launch validation",
        "mvp_scope": string_list(execution.get("mvp_scope")),
        "risks": risks,
        "risk_level": risk_level,
        "strictness": strictness,
        "evaluation_score": score,
        "recommendation": recommendation or None,
        "technical_approach": compact(solution.get("technical_approach") or solution.get("approach"))
        or "planned solution",
        "stack_label": stack_label(stack),
        "acceptance_criteria": acceptance_criteria(spec),
        "evidence_references": evidence,
    }


def summary(ctx: dict[str, Any], **extra: Any) -> dict[str, Any]:
    data = {
        "title": ctx["title"],
        "workflow_context": ctx["workflow_context"],
        "target_user": ctx["target_user"],
        "buyer": ctx["buyer"],
        "evaluation_score": ctx["evaluation_score"],
        "recommendation": ctx["recommendation"],
        "risk_level": ctx["risk_level"],
        "strictness": ctx["strictness"],
    }
    data.update(extra)
    return data


def source_id(source: dict[str, Any]) -> str:
    return compact(source.get("idea_id")) or compact(source.get("id")) or "tact_spec"


def markdown_header(report: dict[str, Any], label: str) -> list[str]:
    summary_data = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    title = compact(summary_data.get("title")) or "TactSpec"
    return [
        f"# {title} {label}",
        "",
        f"- Schema version: {text(report.get('schema_version'))}",
        f"- Kind: {text(report.get('kind'))}",
        f"- Source ID: {source_id(source)}",
        f"- TactSpec schema: {text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {text(summary_data.get('workflow_context'))}",
        f"- Target user: {text(summary_data.get('target_user'))}",
        f"- Buyer: {text(summary_data.get('buyer'))}",
        f"- Risk level: {text(summary_data.get('risk_level'))}",
        f"- Strictness: {text(summary_data.get('strictness'))}",
        "",
    ]


def extend_section(
    lines: list[str], title: str, items: list[dict[str, Any]], renderer: Callable[[dict[str, Any]], list[str]]
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def render_item(item: dict[str, Any]) -> list[str]:
    title = f"### {item.get('id')}: {item.get('name')}" if item.get("name") else f"### {item.get('id')}"
    lines = [title, ""]
    for key in ("type", "severity", "owner", "timing", "condition", "action", "description", "expiry", "references"):
        value = item.get(key)
        if value is not None and value != "":
            lines.append(f"- {key.replace('_', ' ').title()}: {join(value) if isinstance(value, list) else text(value)}")
    return lines


def render_evidence(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Type: {item['type']}", f"- Reference: {item['reference']}"]


def csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return "; ".join(csv_text(item) for item in value if csv_text(item))
    if isinstance(value, dict):
        return "; ".join(f"{csv_text(key)}: {csv_text(item)}" for key, item in sorted(value.items()) if csv_text(item))
    return compact(value)


def csv_row(**values: Any) -> dict[str, str]:
    return {column: csv_text(values.get(column)) for column in CSV_COLUMNS}


def render_csv(report: dict[str, Any], section_names: tuple[str, ...]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    summary_data = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    evidence_refs = [item.get("reference") for item in report.get("evidence_references") or [] if isinstance(item, dict)]
    base = {
        "source_id": source_id(source),
        "title": summary_data.get("title"),
        "strictness": summary_data.get("strictness"),
        "evidence_refs": evidence_refs,
    }
    for section in section_names:
        for item in report.get(section) or []:
            writer.writerow(
                csv_row(
                    **base,
                    section=section,
                    type=item.get("type"),
                    item_id=item.get("id"),
                    name=item.get("name"),
                    owner=item.get("owner"),
                    severity=item.get("severity"),
                    timing=item.get("timing") or item.get("expiry"),
                    condition=item.get("condition"),
                    action=item.get("action"),
                    description=item.get("description"),
                    references=item.get("references"),
                )
            )
    return output.getvalue()


def evidence_references(spec: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    refs: list[tuple[str, str]] = []
    refs.extend(("insight", item) for item in string_list(evidence.get("insight_ids")))
    refs.extend(("signal", item) for item in string_list(evidence.get("signal_ids")))
    refs.extend(("source_idea", item) for item in string_list(evidence.get("source_idea_ids")))
    rationale = compact(evidence.get("rationale"))
    if rationale:
        refs.append(("rationale", rationale))
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for ref_type, value in refs:
        key = (ref_type, value)
        if key in seen:
            continue
        seen.add(key)
        reference = value if ref_type == "rationale" else f"{ref_type}:{value}"
        result.append({"id": f"EV{len(result) + 1}", "type": ref_type, "reference": reference})
    return result


def acceptance_criteria(spec: dict[str, Any]) -> list[str]:
    criteria = spec.get("acceptance_criteria")
    values = criteria.get("criteria") if isinstance(criteria, dict) else criteria
    result: list[str] = []
    for item in values if isinstance(values, list) else []:
        result.append(compact(item.get("criterion") or item.get("description") or item.get("name")) if isinstance(item, dict) else compact(item))
    compact_value = compact(values)
    return [item for item in result if item] or ([compact_value] if compact_value and not isinstance(values, list) else [])


def classify_risk(risks: list[str], score: float | None, recommendation: str) -> str:
    text_value = " ".join(risks).lower()
    high_terms = ("security", "privacy", "compliance", "data loss", "outage", "migration", "dependency", "protocol churn", "downtime")
    if score is not None and score < 55:
        return "high"
    if recommendation in {"no", "strong_no"}:
        return "high"
    if len(risks) >= 3 or any(term in text_value for term in high_terms):
        return "high"
    if risks:
        return "medium"
    return "low"


def stack_label(stack: dict[str, Any]) -> str:
    return ", ".join(f"{compact(key)}={compact(value)}" for key, value in sorted(stack.items()) if compact(value))


def number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [compact(item) for item in value if compact(item)]
    compact_value = compact(value)
    return [compact_value] if compact_value else []


def join(values: Any) -> str:
    items = string_list(values)
    return ", ".join(items) if items else "none"


def compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
