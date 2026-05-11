"""Deterministic change impact memos for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.change_impact.v1"
KIND = "max.design_brief.change_impact"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "name",
    "owner",
    "impact",
    "risk",
    "recommendation",
    "evidence_refs",
    "source_idea_ids",
)


def build_design_brief_change_impact_memo(
    store: Store, brief_id: str, proposed_change: str = ""
) -> dict[str, Any] | None:
    """Build a deterministic impact memo for a proposed design brief change."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    context = _context(design_brief, source_ideas, proposed_change)
    stakeholders = _stakeholders(context, source_idea_ids)
    dependencies = _dependencies(context, source_idea_ids)
    metric_risks = _metric_risks(context, source_idea_ids)
    sequencing = _sequencing(context, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
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
        "impact_summary": {
            "proposed_change": context["proposed_change"],
            "buyer": context["buyer"],
            "target_user": context["target_user"],
            "workflow_context": context["workflow_context"],
            "impact_level": context["impact_level"],
            "primary_risk": context["primary_risk"],
            "recommendation": context["recommendation"],
        },
        "affected_stakeholders": stakeholders,
        "impacted_dependencies": dependencies,
        "metric_risks": metric_risks,
        "sequencing_changes": sequencing,
        "evidence_references": _evidence_references(design_brief, source_ideas),
    }


def render_design_brief_change_impact_memo(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_change_impact_memo_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported change impact memo format: {fmt}")

    brief = report["design_brief"]
    summary = report["impact_summary"]
    lines = [
        f"# Change Impact Memo: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Proposed change: {summary['proposed_change']}",
        f"Impact level: {summary['impact_level']}",
        f"Recommendation: {summary['recommendation']}",
        "",
    ]
    for section, title in (
        ("affected_stakeholders", "Affected Stakeholders"),
        ("impacted_dependencies", "Impacted Dependencies"),
        ("metric_risks", "Metric Risks"),
        ("sequencing_changes", "Sequencing Changes"),
    ):
        lines.extend([f"## {title}", ""])
        for item in report.get(section) or []:
            lines.append(f"- **{item['name']}** ({item['owner']}): {item['impact']} Recommendation: {item['recommendation']}")
        lines.append("")
    lines.extend(["## Evidence References", ""])
    refs = report.get("evidence_references") or []
    lines.extend(f"- {item['reference']}" for item in refs) if refs else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_change_impact_memo_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    brief = report.get("design_brief") or {}
    for section in ("affected_stakeholders", "impacted_dependencies", "metric_risks", "sequencing_changes"):
        for item in report.get(section) or []:
            writer.writerow(
                {
                    "design_brief_id": brief.get("id", ""),
                    "design_brief_title": brief.get("title", ""),
                    "section": section,
                    "item_id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "owner": item.get("owner", ""),
                    "impact": item.get("impact", ""),
                    "risk": item.get("risk", ""),
                    "recommendation": item.get("recommendation", ""),
                    "evidence_refs": json.dumps(item.get("evidence_refs") or [], sort_keys=True),
                    "source_idea_ids": json.dumps(item.get("source_idea_ids") or [], sort_keys=True),
                }
            )
    return output.getvalue()


def _context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]], proposed_change: str) -> dict[str, Any]:
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    change = _compact(proposed_change) or "Clarify scope or positioning before the next design review."
    readiness = float(design_brief.get("readiness_score") or 0.0)
    impact_level = "high" if readiness < 60 or risks else "moderate"
    return {
        "proposed_change": change,
        "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer")) or "economic sponsor",
        "target_user": _first_text(design_brief.get("specific_user"), _field_values(source_ideas, "specific_user")) or "primary user",
        "workflow_context": _first_text(design_brief.get("workflow_context"), _field_values(source_ideas, "workflow_context")) or "target workflow",
        "validation_plan": _first_text(design_brief.get("validation_plan"), _field_values(source_ideas, "validation_plan")) or "validation plan not captured",
        "mvp_scope": _string_list(design_brief.get("mvp_scope")) or ["approved brief scope"],
        "milestones": _string_list(design_brief.get("first_milestones")) or ["confirm change disposition"],
        "risks": risks,
        "primary_risk": risks[0] if risks else "No explicit risk captured.",
        "impact_level": impact_level,
        "recommendation": "Run a change review before implementation continues." if impact_level == "high" else "Accept after owner review and metric update.",
    }


def _stakeholders(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return [
        _item("STK1", context["buyer"], "Product lead", f"May need to re-approve priority and business outcome for {context['proposed_change']}.", "Sponsor alignment can drift.", context["recommendation"], ["design_brief.buyer"], ids),
        _item("STK2", context["target_user"], "Design lead", f"Workflow expectations may change for {context['workflow_context']}.", "Adoption evidence can become stale.", "Validate the revised workflow with at least one target user.", ["design_brief.specific_user", "design_brief.workflow_context"], ids),
        _item("STK3", "Implementation team", "Engineering lead", "Scope, sequencing, and technical assumptions may need replanning.", context["primary_risk"], "Re-estimate MVP scope and first milestones.", ["design_brief.mvp_scope", "design_brief.first_milestones"], ids),
    ]


def _dependencies(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return [
        _item("DEP1", "MVP scope", "Product lead", f"Change must be reconciled against: {'; '.join(context['mvp_scope'][:3])}.", "Unbounded scope can dilute pilot learning.", "Mark each scope item as keep, change, or defer.", ["design_brief.mvp_scope"], ids),
        _item("DEP2", "Validation plan", "Research owner", context["validation_plan"], "Existing validation may no longer prove the changed claim.", "Update success criteria before running more evidence collection.", ["design_brief.validation_plan"], ids),
        _item("DEP3", "Risk controls", "Risk owner", context["primary_risk"], "Known risks may increase if the change touches data, users, or launch timing.", "Attach an owner and disposition to the top risk.", ["design_brief.risks"], ids),
    ]


def _metric_risks(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return [
        _item("MET1", "Activation", "Product analytics", f"Activation definition for {context['workflow_context']} may need revision.", "Baseline and post-change data may not compare cleanly.", "Freeze the old metric and add a changed-scope annotation.", ["design_brief.workflow_context"], ids),
        _item("MET2", "Pilot success", "Product lead", "Pilot success criteria may need a new threshold.", "A change can make the pilot look successful for the wrong reason.", "Update the pilot scorecard before the next milestone.", ["design_brief.validation_plan"], ids),
    ]


def _sequencing(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return [
        _item("SEQ1", "Change review", "Product lead", "Review buyer, user, dependency, metric, and risk impact before delivery resumes.", "Skipping review can create silent acceptance drift.", "Hold a brief change review as the next step.", ["design_brief.synthesis_rationale"], ids),
        _item("SEQ2", "Milestone update", "Delivery owner", f"Reconcile changed scope with milestone: {context['milestones'][0]}.", "Old milestones may certify the wrong outcome.", "Publish revised milestone language and owner.", ["design_brief.first_milestones"], ids),
    ]


def _item(id: str, name: str, owner: str, impact: str, risk: str, recommendation: str, refs: list[str], ids: list[str]) -> dict[str, Any]:
    return {"id": id, "name": name, "owner": owner, "impact": impact, "risk": risk, "recommendation": recommendation, "evidence_refs": refs, "source_idea_ids": ids}


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas = []
    for rank, idea_id in enumerate(_string_list(design_brief.get("source_idea_ids"))):
        unit = store.get_buildable_unit(idea_id)
        data = unit.model_dump(mode="json") if unit is not None else {"id": idea_id, "missing": True}
        data["rank"] = rank
        ideas.append(data)
    return ideas


def _evidence_references(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs = [{"type": "design_brief", "reference": f"design_brief.{field}"} for field in ("buyer", "specific_user", "workflow_context", "validation_plan", "mvp_scope", "first_milestones", "risks") if _string_list(design_brief.get(field))]
    refs.extend({"type": "source_idea", "reference": f"idea:{idea['id']}"} for idea in source_ideas if idea.get("id") and not idea.get("missing"))
    return refs


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        value = item.get(field)
        values.extend(_string_list(value))
    return [value for value in values if value]


def _first_text(*values: Any) -> str:
    for value in values:
        for text in _string_list(value):
            if text:
                return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    text = _compact(value)
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _compact(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
