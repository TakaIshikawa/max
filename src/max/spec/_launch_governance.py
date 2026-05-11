"""Shared helpers for deterministic launch governance TactSpec reports."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any, Iterable, Mapping


CSV_COLUMNS = (
    "section",
    "type",
    "source_idea_id",
    "title",
    "risk_level",
    "item_id",
    "name",
    "severity",
    "stakeholder",
    "owner",
    "timing",
    "description",
    "action",
    "evidence_references",
)

RISK_TERMS = (
    "critical",
    "outage",
    "downtime",
    "security",
    "privacy",
    "compliance",
    "migration",
    "payment",
    "data loss",
    "rollback",
)


def base_context(tact_spec: Mapping[str, Any] | None) -> dict[str, Any]:
    spec = tact_spec if isinstance(tact_spec, Mapping) else {}
    source = _dict(spec.get("source"))
    project = _dict(spec.get("project"))
    solution = _dict(spec.get("solution"))
    execution = _dict(spec.get("execution"))
    evaluation = _dict(spec.get("evaluation"))

    title = _text(project.get("title")) or _text(source.get("idea_id")) or "Untitled TactSpec"
    risks = _string_list(execution.get("risks"))
    score = _number(evaluation.get("overall_score"))
    risk_text = " ".join([*risks, _text(evaluation.get("recommendation"))]).lower()
    risk_level = (
        "high"
        if any(term in risk_text for term in RISK_TERMS) or (score is not None and score < 60)
        else "medium"
        if risks or (score is not None and score < 75)
        else "low"
    )
    evidence = evidence_references(spec)
    return {
        "spec": spec,
        "source": {
            "system": _text(source.get("system")) or "max",
            "type": _text(source.get("type")) or "tact_spec_preview",
            "idea_id": _text(source.get("idea_id")) or None,
            "status": _text(source.get("status")) or None,
            "domain": _text(source.get("domain")) or None,
            "category": _text(source.get("category")) or None,
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(evidence),
        },
        "title": title,
        "summary_text": _text(project.get("summary")) or _text(solution.get("approach")) or "Launch governance plan.",
        "workflow": _text(project.get("workflow_context")) or "primary workflow",
        "target_user": _text(project.get("specific_user") or project.get("target_users")) or "primary user",
        "buyer": _text(project.get("buyer")) or "launch sponsor",
        "support_context": _text(project.get("support_context") or execution.get("support_context"))
        or "support intake and customer escalation",
        "technical_approach": _text(solution.get("technical_approach")) or "planned implementation",
        "stack": stack_label(solution.get("suggested_stack")),
        "validation_plan": _text(execution.get("validation_plan")) or "repeatable launch validation",
        "mvp_scope": _string_list(execution.get("mvp_scope")) or ["approved launch scope"],
        "risks": risks,
        "risk_level": risk_level,
        "strictness": "strict" if risk_level == "high" else "standard",
        "evaluation_score": score,
        "evidence_references": evidence,
        "evidence_ids": [item["id"] for item in evidence],
    }


def summary(context: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    payload = {
        "title": context["title"],
        "workflow_context": context["workflow"],
        "target_user": context["target_user"],
        "buyer": context["buyer"],
        "support_context": context["support_context"],
        "risk_level": context["risk_level"],
        "strictness": context["strictness"],
        "suggested_stack": context["stack"],
    }
    payload.update(extra)
    return payload


def item(
    item_id: str,
    name: str,
    description: str,
    owner: str,
    *,
    type_: str = "",
    severity: str = "",
    stakeholder: str = "",
    timing: str = "",
    action: str = "",
    evidence: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "type": type_ or name,
        "severity": severity,
        "stakeholder": stakeholder,
        "owner": owner,
        "timing": timing,
        "description": description,
        "action": action,
        "evidence_references": list(evidence),
    }


def render_markdown(report: Mapping[str, Any], title_suffix: str, section_order: Iterable[str]) -> str:
    summary_data = _dict(report.get("summary"))
    source = _dict(report.get("source"))
    title = _text(summary_data.get("title")) or "TactSpec"
    lines = [
        f"# {title} {title_suffix}",
        "",
        f"- Schema version: {_text(report.get('schema_version'))}",
        f"- Kind: {_text(report.get('kind'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Workflow context: {_text(summary_data.get('workflow_context'))}",
        f"- Target user: {_text(summary_data.get('target_user'))}",
        f"- Buyer: {_text(summary_data.get('buyer'))}",
        f"- Support context: {_text(summary_data.get('support_context'))}",
        f"- Risk level: {_text(summary_data.get('risk_level'))}",
        f"- Strictness: {_text(summary_data.get('strictness'))}",
        "",
    ]
    for section in section_order:
        lines.extend([f"## {section.replace('_', ' ').title()}", ""])
        rows = report.get(section) if isinstance(report.get(section), list) else []
        if rows:
            for row in rows:
                lines.append(_markdown_row(_dict(row)))
        else:
            lines.append("- No generated items.")
        lines.append("")
    lines.extend(["## Evidence References", ""])
    evidence = report.get("evidence_references") if isinstance(report.get("evidence_references"), list) else []
    if evidence:
        for ref in evidence:
            if isinstance(ref, Mapping):
                lines.append(f"- {ref.get('id')}: {ref.get('reference')}")
            else:
                lines.append(f"- {_text(ref)}")
    else:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def render_incident_markdown(report: Mapping[str, Any]) -> str:
    lines = render_markdown(
        report,
        "Incident Communications Matrix",
        ("stakeholder_channels",),
    ).rstrip().splitlines()
    lines.extend(["", "## Severity Notifications", ""])
    notifications = report.get("severity_notifications") if isinstance(report.get("severity_notifications"), list) else []
    for severity in ("sev1", "sev2", "sev3"):
        lines.extend([f"### {severity.upper()}", ""])
        rows = [row for row in notifications if _dict(row).get("severity") == severity]
        if rows:
            lines.extend(_markdown_row(_dict(row)) for row in rows)
        else:
            lines.append("- No generated notifications.")
        lines.append("")
    lines.extend(["## Stakeholder Channels", ""])
    channels = report.get("stakeholder_channels") if isinstance(report.get("stakeholder_channels"), list) else []
    for channel in channels:
        row = _dict(channel)
        lines.append(f"### {row.get('stakeholder') or row.get('name')}")
        lines.append(_markdown_row(row))
        lines.append("")
    for section in ("message_templates", "escalation_handoffs", "status_promises"):
        lines.extend([f"## {section.replace('_', ' ').title()}", ""])
        rows = report.get(section) if isinstance(report.get(section), list) else []
        lines.extend(_markdown_row(_dict(row)) for row in rows)
        if not rows:
            lines.append("- No generated items.")
        lines.append("")
    lines.extend(["## Evidence References", ""])
    evidence = report.get("evidence_references") if isinstance(report.get("evidence_references"), list) else []
    lines.extend(f"- {_dict(ref).get('id')}: {_dict(ref).get('reference')}" for ref in evidence)
    if not evidence:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def render_csv(report: Mapping[str, Any], section_order: Iterable[str]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    source = _dict(report.get("source"))
    summary_data = _dict(report.get("summary"))
    for section in section_order:
        for row in report.get(section) or []:
            row = _dict(row)
            writer.writerow(
                {
                    "section": section,
                    "type": _text(row.get("type")),
                    "source_idea_id": _text(source.get("idea_id")),
                    "title": _text(summary_data.get("title")),
                    "risk_level": _text(summary_data.get("risk_level")),
                    "item_id": _text(row.get("id")),
                    "name": _text(row.get("name")),
                    "severity": _text(row.get("severity")),
                    "stakeholder": _text(row.get("stakeholder")),
                    "owner": _text(row.get("owner")),
                    "timing": _text(row.get("timing")),
                    "description": _text(row.get("description")),
                    "action": _text(row.get("action")),
                    "evidence_references": "; ".join(_string_list(row.get("evidence_references"))),
                }
            )
    return output.getvalue()


def evidence_references(spec: Mapping[str, Any]) -> list[dict[str, str]]:
    evidence = _dict(spec.get("evidence"))
    refs: list[str] = []
    for key in ("insight_ids", "signal_ids", "source_idea_ids"):
        refs.extend(_string_list(evidence.get(key)))
    refs.extend(_string_list(evidence.get("references")))
    rationale = _text(evidence.get("rationale"))
    if rationale:
        refs.append(rationale)
    return [{"id": f"EV{index}", "reference": ref} for index, ref in enumerate(_dedupe(refs), start=1)]


def stack_label(value: Any) -> str:
    if isinstance(value, Mapping):
        parts = [f"{key}={value[key]}" for key in sorted(value) if _text(value[key])]
        return ", ".join(parts) if parts else "unspecified"
    if isinstance(value, (list, tuple, set)):
        parts = [_text(item) for item in value if _text(item)]
        return ", ".join(parts) if parts else "unspecified"
    return _text(value) or "unspecified"


def _markdown_row(row: Mapping[str, Any]) -> str:
    pieces = [f"**{row.get('id', '')} {row.get('name', '')}**".strip()]
    details = []
    for key in ("severity", "stakeholder", "owner", "timing"):
        if _text(row.get(key)):
            details.append(f"{key}: {_text(row.get(key))}")
    if details:
        pieces.append(f"({'; '.join(details)})")
    if _text(row.get("description")):
        pieces.append(f": {_text(row.get('description'))}")
    if _text(row.get("action")):
        pieces.append(f" Action: {_text(row.get('action'))}")
    return "- " + " ".join(pieces)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, Mapping):
        return [f"{key}: {value[key]}" for key in sorted(value) if _text(value[key])]
    if isinstance(value, Iterable):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
