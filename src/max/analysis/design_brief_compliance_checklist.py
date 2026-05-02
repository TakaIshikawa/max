"""Deterministic compliance checklist export for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.compliance_checklist.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "design_brief_id",
    "design_brief_title",
    "section_id",
    "section",
    "item_id",
    "obligation_control",
    "applicability",
    "required_evidence",
    "owner",
    "verification",
    "status_or_priority",
    "evidence_references",
    "source_idea_ids",
    "source_fields",
    "rationale",
)


SECTION_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "security",
        "title": "Security",
        "owner_role": "Security owner",
        "description": "Confirm the MVP can be built without exposing credentials, systems, or users.",
        "exit_criteria": "Threat model, access boundaries, and vulnerability review are accepted.",
        "keywords": ("security", "credential", "oauth", "vulnerability", "threat", "risk"),
    },
    {
        "id": "privacy",
        "title": "Privacy",
        "owner_role": "Privacy owner",
        "description": "Confirm personal data collection, consent, and disclosure requirements.",
        "exit_criteria": "Personal data use, user notice, and consent assumptions are documented.",
        "keywords": ("privacy", "pii", "personal", "consent", "user", "customer"),
    },
    {
        "id": "accessibility",
        "title": "Accessibility",
        "owner_role": "Design owner",
        "description": "Confirm the user-facing workflow can meet baseline accessibility expectations.",
        "exit_criteria": "Keyboard, screen reader, contrast, and error-state coverage are planned.",
        "keywords": ("accessibility", "a11y", "screen reader", "keyboard", "contrast", "user"),
    },
    {
        "id": "data_retention",
        "title": "Data Retention",
        "owner_role": "Data owner",
        "description": "Confirm persisted records have retention, deletion, and audit handling.",
        "exit_criteria": "Data classes, retention periods, deletion paths, and audit needs are recorded.",
        "keywords": ("data", "retention", "delete", "audit", "telemetry", "metrics", "events"),
    },
    {
        "id": "launch_governance",
        "title": "Launch Governance",
        "owner_role": "Product owner",
        "description": "Confirm compliance gates are resolved before implementation or publication.",
        "exit_criteria": "Required approvals, launch blockers, and post-launch review owners are recorded.",
        "keywords": ("launch", "governance", "approval", "compliance", "legal", "risk"),
    },
)


def build_design_brief_compliance_checklist(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a compliance checklist from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    evidence = _collect_evidence(store, source_ideas)
    sections = _sections(design_brief, source_ideas, source_idea_ids, evidence)
    checklist_items = _flatten_items(sections)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.compliance_checklist",
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
        "summary": {
            "gate": _compliance_gate(design_brief),
            "section_count": len(sections),
            "item_count": len(checklist_items),
            "evidence_reference_count": len(_all_evidence_references(sections)),
            "source_idea_count": len(source_idea_ids),
        },
        "sections": sections,
        "checklist_items": checklist_items,
        "evidence_references": _all_evidence_references(sections),
        "recommended_next_actions": _recommended_next_actions(design_brief, sections),
        "source_ideas": source_ideas,
    }


def render_design_brief_compliance_checklist(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a compliance checklist as Markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported compliance checklist format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Compliance Checklist: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Compliance gate: {summary['gate']}",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
    ]

    for section in report["sections"]:
        lines.extend([f"## {section['title']}", "", section["description"], ""])
        lines.extend(
            [
                f"- Owner role: {section['owner_role']}",
                f"- Gate status: {section['gate_status']}",
                f"- Exit criteria: {section['exit_criteria']}",
                f"- Evidence references: {_inline_ids([ref['id'] for ref in section['evidence_references']])}",
                "",
            ]
        )
        for item in section["items"]:
            lines.extend(
                [
                    f"### {item['id']}: {item['task']}",
                    "",
                    f"- Status: {item['status']}",
                    f"- Owner: {item['owner']}",
                    f"- Required: {item['required']}",
                    f"- Rationale: {item['rationale']}",
                    f"- Exit criteria: {item['exit_criteria']}",
                    f"- Source ideas: {_inline_ids(item['source_idea_ids'])}",
                    f"- Evidence references: {_inline_ids([ref['id'] for ref in item['evidence_references']])}",
                    "",
                ]
            )

    lines.extend(["## Recommended Next Actions", ""])
    lines.extend(f"- {action}" for action in report["recommended_next_actions"])
    return "\n".join(lines).rstrip() + "\n"


def compliance_checklist_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-compliance-checklist.{extension}"
    )


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for item in _csv_items(report):
        writer.writerow(_csv_row(report, item))
    return output.getvalue()


def _csv_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    items = report.get("checklist_items")
    if isinstance(items, list):
        return items

    rows: list[dict[str, Any]] = []
    for section in report.get("sections", []) or []:
        for item in section.get("items", []) or []:
            rows.append(
                {
                    **item,
                    "section_id": section.get("id", ""),
                    "section_title": section.get("title", ""),
                    "section_owner_role": section.get("owner_role", ""),
                }
            )
    return rows


def _csv_row(report: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    evidence_references = [
        ref.get("id")
        for ref in item.get("evidence_references", []) or []
        if isinstance(ref, dict) and ref.get("id")
    ]
    required = item.get("required")
    applicability = "required" if required is True else "optional" if required is False else ""
    row = {
        "schema_version": _csv_text(report.get("schema_version")),
        "kind": _csv_text(report.get("kind")),
        "design_brief_id": _csv_text(brief.get("id")),
        "design_brief_title": _csv_text(brief.get("title")),
        "section_id": _csv_text(item.get("section_id")),
        "section": _csv_text(item.get("section_title")),
        "item_id": _csv_text(item.get("id")),
        "obligation_control": _csv_text(item.get("task")),
        "applicability": applicability,
        "required_evidence": _csv_text(item.get("exit_criteria")),
        "owner": _csv_text(item.get("owner")),
        "verification": "owner_review",
        "status_or_priority": _csv_text(item.get("status") or item.get("priority")),
        "evidence_references": _csv_list(evidence_references),
        "source_idea_ids": _csv_list(item.get("source_idea_ids")),
        "source_fields": _csv_list(item.get("source_fields")),
        "rationale": _csv_text(item.get("rationale")),
    }
    return {column: row[column] for column in CSV_COLUMNS}


def _sections(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    item_number = 1
    sections: list[dict[str, Any]] = []
    for config in SECTION_CONFIGS:
        evidence_refs = _evidence_references_for_keywords(evidence, config["keywords"], source_idea_ids)
        raw_items = _section_items(config["id"], design_brief, source_ideas, source_idea_ids, evidence_refs)
        items = []
        for raw in raw_items:
            items.append({"id": f"DBCC{item_number}", "status": "pending", **raw})
            item_number += 1
        sections.append(
            {
                "id": config["id"],
                "title": config["title"],
                "description": config["description"],
                "owner_role": config["owner_role"],
                "exit_criteria": config["exit_criteria"],
                "gate_status": "requires_review",
                "evidence_references": evidence_refs,
                "items": items,
            }
        )
    return sections


def _section_items(
    section_id: str,
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    evidence_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs = evidence_refs
    if section_id == "security":
        return [
            _item(
                task="Review authentication, authorization, and credential handling for the MVP workflow.",
                rationale=_first_text(_joined_fields(source_ideas, ("tech_approach",)), design_brief.get("merged_product_concept"), "Security boundaries are not yet explicit."),
                owner="security_owner",
                exit_criteria="Access boundaries, secrets handling, and privileged actions are documented.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("tech_approach", "suggested_stack"), source_idea_ids),
                source_fields=["tech_approach", "suggested_stack"],
                evidence_references=refs,
            ),
            _item(
                task="Record threat scenarios and launch-blocking security risks.",
                rationale="; ".join(_risk_texts(design_brief, source_ideas)) or "No security risks are captured yet.",
                owner="security_owner",
                exit_criteria="Top security risks have mitigation, owner, and accept or block decision.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("domain_risks", "evidence_rationale"), source_idea_ids),
                source_fields=["risks", "domain_risks", "evidence_rationale"],
                evidence_references=refs,
            ),
        ]
    if section_id == "privacy":
        return [
            _item(
                task="Identify personal or customer data needed by the target workflow.",
                rationale=_first_text(design_brief.get("workflow_context"), _joined_fields(source_ideas, ("workflow_context",)), "Data use is not yet explicit."),
                owner="privacy_owner",
                exit_criteria="Personal data categories and collection purpose are listed.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("workflow_context", "specific_user", "buyer"), source_idea_ids),
                source_fields=["workflow_context", "specific_user", "buyer"],
                evidence_references=refs,
            ),
            _item(
                task="Confirm user notice, consent, and data sharing assumptions before implementation.",
                rationale=_first_text(design_brief.get("specific_user"), _joined_fields(source_ideas, ("specific_user", "buyer")), "Privacy review needs user and buyer context."),
                owner="privacy_owner",
                exit_criteria="Notice, consent, processor, and sharing assumptions are accepted or marked not applicable.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("specific_user", "buyer"), source_idea_ids),
                source_fields=["specific_user", "buyer", "first_10_customers"],
                evidence_references=refs,
            ),
        ]
    if section_id == "accessibility":
        return [
            _item(
                task="Define baseline accessibility checks for the primary user journey.",
                rationale=_first_text(design_brief.get("specific_user"), _joined_fields(source_ideas, ("specific_user", "target_users")), "Primary users are not fully specified."),
                owner="design_owner",
                exit_criteria="Keyboard navigation, focus order, semantic labels, contrast, and error states are in scope.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("specific_user", "target_users"), source_idea_ids),
                source_fields=["specific_user", "target_users", "workflow_context"],
                evidence_references=refs,
            ),
            _item(
                task="Add accessibility acceptance criteria to the first implementation milestones.",
                rationale="; ".join(_string_list(design_brief.get("first_milestones"))) or "No first milestones are captured yet.",
                owner="design_owner",
                exit_criteria="Each user-facing milestone includes an accessibility acceptance check.",
                source_idea_ids=source_idea_ids,
                source_fields=["first_milestones", "mvp_scope"],
                evidence_references=refs,
            ),
        ]
    if section_id == "data_retention":
        return [
            _item(
                task="Classify records, telemetry, feedback, and operational data created by the MVP.",
                rationale=_first_text(design_brief.get("merged_product_concept"), _joined_fields(source_ideas, ("solution",)), "Data created by the MVP is not yet classified."),
                owner="data_owner",
                exit_criteria="Data classes include owner, purpose, storage location, and sensitivity.",
                source_idea_ids=_source_ids_for_fields(source_ideas, ("solution", "tech_approach"), source_idea_ids),
                source_fields=["merged_product_concept", "solution", "tech_approach"],
                evidence_references=refs,
            ),
            _item(
                task="Define retention, deletion, and audit requirements before publishing specs.",
                rationale="Compliance gates should prevent unbounded data retention by default.",
                owner="data_owner",
                exit_criteria="Retention periods, deletion triggers, and audit log requirements are documented.",
                source_idea_ids=source_idea_ids,
                source_fields=["mvp_scope", "validation_plan", "source_idea_ids"],
                evidence_references=refs,
            ),
        ]
    return [
        _item(
            task="Assign compliance gate owners before specs are built or published.",
            rationale=_first_text(design_brief.get("why_this_now"), "Compliance needs accountable approval owners."),
            owner="product_owner",
            exit_criteria="Security, privacy, accessibility, data, and launch gate owners are named.",
            source_idea_ids=source_idea_ids,
            source_fields=["why_this_now", "design_status", "source_idea_ids"],
            evidence_references=refs,
        ),
        _item(
            task="Convert unresolved compliance findings into launch blockers or dated follow-up work.",
            rationale="; ".join(_risk_texts(design_brief, source_ideas)) or "No compliance risks are captured yet.",
            owner="product_owner",
            exit_criteria="Every unresolved finding has a block, accept, defer, or not-applicable decision.",
            source_idea_ids=source_idea_ids,
            source_fields=["risks", "domain_risks", "validation_plan"],
            evidence_references=refs,
        ),
    ]


def _item(
    *,
    task: str,
    rationale: str,
    owner: str,
    exit_criteria: str,
    source_idea_ids: list[str],
    source_fields: list[str],
    evidence_references: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "task": task,
        "rationale": _compact(rationale),
        "owner": owner,
        "required": True,
        "exit_criteria": exit_criteria,
        "source_idea_ids": list(dict.fromkeys(source_idea_ids)),
        "source_fields": source_fields,
        "evidence_references": evidence_references,
    }


def _flatten_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "section_id": section["id"],
            "section_title": section["title"],
            "section_owner_role": section["owner_role"],
        }
        for section in sections
        for item in section["items"]
    ]


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = list(design_brief.get("sources", []))
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(design_brief.get("source_idea_ids", []), start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

    for source in sources:
        idea_id = str(source["idea_id"])
        if idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append(
                {
                    "id": idea_id,
                    "role": source.get("role", "source"),
                    "rank": source.get("rank", 0),
                    "missing": True,
                }
            )
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _collect_evidence(store: Store, source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    signal_source_ideas: dict[str, list[str]] = {}
    insight_source_ideas: dict[str, list[str]] = {}
    insight_signal_ids: dict[str, list[str]] = {}

    for idea in source_ideas:
        if idea.get("missing"):
            continue
        idea_id = idea["id"]
        for signal_id in _string_list(idea.get("evidence_signals")):
            signal_source_ideas.setdefault(signal_id, []).append(idea_id)
        for insight_id in _string_list(idea.get("inspiring_insights")):
            insight_source_ideas.setdefault(insight_id, []).append(idea_id)

    insights: dict[str, Any] = {}
    for insight_id in sorted(insight_source_ideas):
        insight = store.get_insight(insight_id)
        if not insight:
            continue
        insights[insight_id] = insight
        signal_ids = _string_list(insight.evidence)
        insight_signal_ids[insight_id] = signal_ids
        for signal_id in signal_ids:
            signal_source_ideas.setdefault(signal_id, []).extend(insight_source_ideas[insight_id])

    signals: dict[str, Any] = {}
    for signal_id in sorted(signal_source_ideas):
        signal = store.get_signal(signal_id)
        if signal:
            signals[signal_id] = signal

    return {
        "signals": signals,
        "insights": insights,
        "signal_source_ideas": {
            signal_id: list(dict.fromkeys(ids)) for signal_id, ids in signal_source_ideas.items()
        },
        "insight_source_ideas": {
            insight_id: list(dict.fromkeys(ids)) for insight_id, ids in insight_source_ideas.items()
        },
        "insight_signal_ids": insight_signal_ids,
    }


def _evidence_references_for_keywords(
    evidence: dict[str, Any],
    keywords: tuple[str, ...],
    fallback_source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for signal_id, signal in sorted(evidence["signals"].items()):
        if _matches_keywords(
            " ".join(
                [
                    signal.title,
                    signal.content,
                    signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type),
                    signal.signal_role,
                    " ".join(signal.tags),
                ]
            ),
            keywords,
        ):
            refs.append(
                {
                    "kind": "signal",
                    "id": signal_id,
                    "title": signal.title,
                    "source_adapter": signal.source_adapter,
                    "source_type": signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type),
                    "url": signal.url,
                    "source_idea_ids": evidence["signal_source_ideas"].get(signal_id, fallback_source_idea_ids),
                }
            )

    for insight_id, insight in sorted(evidence["insights"].items()):
        category = insight.category.value if hasattr(insight.category, "value") else str(insight.category)
        if _matches_keywords(" ".join([insight.title, insight.summary, category]), keywords):
            refs.append(
                {
                    "kind": "insight",
                    "id": insight_id,
                    "title": insight.title,
                    "source_adapter": None,
                    "source_type": category,
                    "url": None,
                    "source_idea_ids": evidence["insight_source_ideas"].get(insight_id, fallback_source_idea_ids),
                }
            )

    if not refs:
        return []
    return sorted(refs, key=lambda ref: (ref["kind"], ref["id"]))


def _all_evidence_references(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for section in sections:
        for ref in section["evidence_references"]:
            refs_by_key[(ref["kind"], ref["id"])] = ref
    return [refs_by_key[key] for key in sorted(refs_by_key)]


def _recommended_next_actions(design_brief: dict[str, Any], sections: list[dict[str, Any]]) -> list[str]:
    actions = [
        "Review each compliance section before generating or publishing implementation specs.",
        "Record owner, decision, and evidence link for every required checklist item.",
        "Treat unresolved required items as launch blockers unless explicitly accepted by the accountable owner.",
    ]
    if _compliance_gate(design_brief) != "ready_for_compliance_review":
        actions.insert(0, "Approve the design brief or raise readiness before using this checklist as a launch gate.")
    if not _all_evidence_references(sections):
        actions.append("Attach persisted evidence signals or insights to source ideas for audit traceability.")
    return actions


def _compliance_gate(design_brief: dict[str, Any]) -> str:
    status = design_brief.get("design_status")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_compliance_review"
    if status in {"approved", "published"}:
        return "approved_needs_readiness_review"
    return "needs_design_approval"


def _source_ids_for_fields(
    source_ideas: list[dict[str, Any]],
    fields: tuple[str, ...],
    fallback: list[str],
) -> list[str]:
    ids = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing") and any(_has_value(idea.get(field)) for field in fields)
    ]
    return list(dict.fromkeys(ids)) or fallback


def _risk_texts(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    risks = _string_list(design_brief.get("risks"))
    for idea in source_ideas:
        risks.extend(_string_list(idea.get("domain_risks")))
    return list(dict.fromkeys(_compact(risk) for risk in risks if _compact(risk)))


def _joined_fields(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for idea in source_ideas:
        for field in fields:
            values.extend(_string_list(idea.get(field)))
    return "; ".join(list(dict.fromkeys(values)))


def _matches_keywords(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, dict):
        return [_compact(key) for key in value.keys() if _compact(key)]
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _csv_list(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values
    return ";".join(_csv_text(value) for value in values if _csv_text(value))


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
