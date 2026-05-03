"""Deterministic one-page summary exports for persisted design briefs."""

from __future__ import annotations

import csv
from io import StringIO
import json
from typing import Any

from max.analysis.design_brief_evidence_matrix import build_design_brief_evidence_matrix
from max.analysis.design_brief_prd import build_design_brief_prd
from max.analysis.design_brief_risk_register import build_design_brief_risk_register
from max.analysis.design_brief_roadmap import build_design_brief_roadmap
from max.analysis.design_validation import build_validation_plan
from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.one_pager.v1"

CSV_COLUMNS = (
    "design_brief_id",
    "design_brief_title",
    "row_type",
    "field",
    "value",
    "risk_id",
    "severity",
    "likelihood",
    "priority",
    "mitigation",
    "validation_action",
    "source_idea_ids",
)

DECISION_CSV_FIELDS = (
    ("target_customer", "Target customer"),
    ("problem", "Problem"),
    ("solution", "Solution"),
    ("validation_next_step", "Validation next step"),
    ("first_milestone", "First milestone"),
    ("source_idea_ids", "Source idea IDs"),
)


def build_design_brief_one_pager(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a compact decision artifact from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    prd = build_design_brief_prd(store, brief_id)
    evidence_matrix = build_design_brief_evidence_matrix(store, design_brief)
    risk_register = build_design_brief_risk_register(store, brief_id)
    validation_plan = build_validation_plan(
        store,
        design_brief,
        generated_at=design_brief.get("updated_at") or design_brief.get("created_at"),
    )
    roadmap = build_design_brief_roadmap(store, brief_id)
    source_idea_ids = _source_idea_ids(design_brief, prd)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "title": design_brief["title"],
        "domain": design_brief.get("domain", ""),
        "target_customer": _target_customer(design_brief, prd),
        "problem": _problem(design_brief, prd),
        "solution": _solution(design_brief, prd),
        "evidence_count": _evidence_count(evidence_matrix),
        "readiness_score": float(design_brief.get("readiness_score") or 0.0),
        "top_risks": _top_risks(risk_register),
        "validation_next_step": _validation_next_step(design_brief, validation_plan, risk_register),
        "first_milestone": _first_milestone(design_brief, roadmap),
        "source_idea_ids": source_idea_ids,
    }


def render_design_brief_one_pager(one_pager: dict[str, Any], fmt: str = "json") -> str:
    """Render the one-page design brief summary as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(one_pager, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_one_pager_csv(one_pager)
    if fmt != "markdown":
        raise ValueError(f"Unsupported one-pager format: {fmt}")

    brief = one_pager["design_brief"]
    lines = [
        f"# One-Pager: {one_pager['title']}",
        "",
        f"Schema: `{one_pager['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {one_pager['domain'] or 'general'}",
        f"Readiness: {one_pager['readiness_score']:.1f}/100",
        f"Evidence count: {one_pager['evidence_count']}",
        "",
        "## Decision Fields",
        "",
        f"- **Target customer**: {one_pager['target_customer']}",
        f"- **Problem**: {one_pager['problem']}",
        f"- **Solution**: {one_pager['solution']}",
        f"- **Validation next step**: {one_pager['validation_next_step']}",
        f"- **First milestone**: {one_pager['first_milestone']}",
        f"- **Source idea IDs**: {_join_or_fallback(one_pager['source_idea_ids'], 'design brief')}",
        "",
        "## Top Risks",
        "",
    ]
    risks = one_pager["top_risks"]
    if risks:
        lines.extend(
            f"- **{risk['severity']} / {risk['likelihood']}**: {risk['title']} - {risk['mitigation']}"
            for risk in risks
        )
    else:
        lines.append("- No explicit top risks are captured yet.")
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_one_pager_csv(one_pager: dict[str, Any]) -> str:
    """Render the one-page design brief summary as deterministic CSV rows."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(one_pager):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(one_pager: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    source_idea_ids = _csv_list(one_pager.get("source_idea_ids", []))
    for key, label in DECISION_CSV_FIELDS:
        value = one_pager.get(key)
        rows.append(
            _csv_row(
                one_pager,
                row_type="decision_field",
                field=label,
                value=_csv_list(value) if key == "source_idea_ids" else value,
                source_idea_ids=source_idea_ids,
            )
        )

    for risk in one_pager.get("top_risks", []):
        rows.append(
            _csv_row(
                one_pager,
                row_type="top_risk",
                field=risk.get("title"),
                value=risk.get("title"),
                risk_id=risk.get("id"),
                severity=risk.get("severity"),
                likelihood=risk.get("likelihood"),
                priority=risk.get("priority"),
                mitigation=risk.get("mitigation"),
                validation_action=risk.get("validation_action"),
                source_idea_ids=_csv_list(risk.get("source_idea_ids")) or source_idea_ids,
            )
        )
    return rows


def _csv_row(one_pager: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = one_pager["design_brief"]
    row = {
        "design_brief_id": _csv_cell(brief.get("id")),
        "design_brief_title": _csv_cell(brief.get("title") or one_pager.get("title")),
        "row_type": "",
        "field": "",
        "value": "",
        "risk_id": "",
        "severity": "",
        "likelihood": "",
        "priority": "",
        "mitigation": "",
        "validation_action": "",
        "source_idea_ids": "",
    }
    for key, value in values.items():
        row[key] = _csv_cell(value)
    return row


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return _csv_list(value)
    return str(value).strip()


def _csv_list(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values.strip()
    return "; ".join(text for value in values if (text := _csv_cell(value)))


def _target_customer(design_brief: dict[str, Any], prd: dict[str, Any] | None) -> str:
    section = (prd or {}).get("sections", {}).get("user_buyer", {})
    return _first_text(
        section.get("content"),
        _combine_customer(design_brief.get("specific_user"), design_brief.get("buyer")),
        "TBD customer",
    )


def _problem(design_brief: dict[str, Any], prd: dict[str, Any] | None) -> str:
    section = (prd or {}).get("sections", {}).get("problem", {})
    return _first_text(
        section.get("content"),
        design_brief.get("why_this_now"),
        design_brief.get("synthesis_rationale"),
        "TBD problem",
    )


def _solution(design_brief: dict[str, Any], prd: dict[str, Any] | None) -> str:
    section = (prd or {}).get("sections", {}).get("proposed_workflow", {})
    return _first_text(
        design_brief.get("merged_product_concept"),
        section.get("content"),
        "TBD solution",
    )


def _evidence_count(evidence_matrix: dict[str, Any]) -> int:
    signal_ids: list[str] = []
    insight_ids: list[str] = []
    source_idea_ids: list[str] = []
    for row in evidence_matrix.get("rows", []):
        signal_ids.extend(str(item) for item in row.get("supporting_signal_ids", []))
        insight_ids.extend(str(item) for item in row.get("supporting_insight_ids", []))
        source_idea_ids.extend(str(item) for item in row.get("supporting_source_idea_ids", []))
    return len(set(signal_ids) | set(insight_ids) | set(source_idea_ids))


def _top_risks(risk_register: dict[str, Any] | None) -> list[dict[str, Any]]:
    risks = (risk_register or {}).get("risks", [])
    return [
        {
            "id": risk["id"],
            "title": risk["title"],
            "severity": risk["severity"],
            "likelihood": risk["likelihood"],
            "priority": risk["priority"],
            "mitigation": risk["mitigation"],
            "validation_action": risk["validation_action"],
            "source_idea_ids": list(risk.get("source_idea_ids", [])),
        }
        for risk in risks[:3]
    ]


def _validation_next_step(
    design_brief: dict[str, Any],
    validation_plan: dict[str, Any],
    risk_register: dict[str, Any] | None,
) -> str:
    risks = (risk_register or {}).get("risks", [])
    if risks:
        return _first_text(risks[0].get("validation_action"), design_brief.get("validation_plan"))

    timeline = validation_plan.get("two_week_timeline", [])
    if timeline:
        step = timeline[0]
        return _first_text(step.get("activity"), step.get("task"), design_brief.get("validation_plan"))

    return _first_text(design_brief.get("validation_plan"), "Run three target-user discovery interviews.")


def _first_milestone(design_brief: dict[str, Any], roadmap: dict[str, Any] | None) -> str:
    milestones = _string_list(design_brief.get("first_milestones"))
    if milestones:
        return milestones[0]
    for item in (roadmap or {}).get("items", []):
        if item.get("phase") in {"prototype", "validation", "beta", "launch"}:
            return _first_text(item.get("title"))
    return "Define the first implementation milestone."


def _source_idea_ids(design_brief: dict[str, Any], prd: dict[str, Any] | None) -> list[str]:
    ids = list((prd or {}).get("design_brief", {}).get("source_idea_ids") or [])
    if not ids:
        ids = list(design_brief.get("source_idea_ids") or [])
    return [str(item) for item in dict.fromkeys(ids)]


def _combine_customer(user: Any, buyer: Any) -> str:
    user_text = _first_text(user)
    buyer_text = _first_text(buyer)
    if user_text and buyer_text:
        return f"Primary user: {user_text}. Buyer or sponsor: {buyer_text}."
    return user_text or buyer_text


def _join_or_fallback(values: list[str], fallback: str) -> str:
    return ", ".join(values) if values else fallback


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
