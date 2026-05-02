"""Deterministic release notes for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.release_notes"
SCHEMA_VERSION = "max.design_brief.release_notes.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "design_brief_id",
    "design_brief_title",
    "design_status",
    "readiness_score",
    "audience",
    "category",
    "item_id",
    "title",
    "summary",
    "impact",
    "rollout_or_version",
    "action_required",
    "owner",
    "evidence_refs",
    "source_idea_ids",
    "source_fields",
)


def build_design_brief_release_notes(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build customer-facing and internal release notes from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    context = _release_context(design_brief, source_ideas, lead_idea)
    capabilities = _shipped_capabilities(design_brief, context, source_idea_ids)
    limitations = _known_limitations(design_brief, context, source_ideas, source_idea_ids)
    evidence = _validation_evidence(store, design_brief, source_ideas)
    rollout = _rollout_notes(design_brief, context, source_idea_ids)
    support = _support_handoff(context, limitations, source_idea_ids)
    milestones = _follow_up_milestones(design_brief, context, source_idea_ids)

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
        "summary": {
            "headline": context["headline"],
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "release_stage": _release_stage(design_brief),
            "fallbacks_used": context["fallbacks_used"],
            "capability_count": len(capabilities),
            "known_limitation_count": len(limitations),
            "evidence_count": len(evidence),
            "follow_up_milestone_count": len(milestones),
        },
        "customer_facing": {
            "headline": context["headline"],
            "overview": context["customer_overview"],
            "shipped_capabilities": capabilities,
            "target_users": _target_users(context, source_idea_ids),
            "rollout_notes": rollout,
            "known_limitations": limitations,
            "follow_up_milestones": milestones,
        },
        "internal": {
            "release_summary": context["internal_summary"],
            "validation_evidence": evidence,
            "support_handoff": support,
            "source_idea_ids": source_idea_ids,
            "source_fields": [
                "merged_product_concept",
                "mvp_scope",
                "first_milestones",
                "validation_plan",
                "risks",
            ],
        },
        "source_ideas": source_ideas,
    }


def render_design_brief_release_notes(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render release notes as Markdown, CSV, or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported release notes format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    customer = report["customer_facing"]
    internal = report["internal"]
    lines = [
        f"# Release Notes: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Customer-Facing Notes",
        "",
        f"### {customer['headline']}",
        "",
        customer["overview"],
        "",
        "### Shipped Capabilities",
        "",
    ]
    for item in customer["shipped_capabilities"]:
        lines.extend(
            [
                f"- **{item['title']}**: {item['description']}",
                f"  Source ideas: {', '.join(item['source_idea_ids']) or 'design brief'}",
            ]
        )

    lines.extend(["", "### Target Users", ""])
    for item in customer["target_users"]:
        lines.extend(
            [
                f"- **{item['name']}**: {item['reason']}",
                f"  Source ideas: {', '.join(item['source_idea_ids']) or 'design brief'}",
            ]
        )

    lines.extend(["", "### Rollout Notes", ""])
    for note in customer["rollout_notes"]:
        lines.extend(
            [
                f"- **{note['stage']}**: {note['note']}",
                f"  Owner: {note['owner']}; source ideas: {', '.join(note['source_idea_ids']) or 'design brief'}",
            ]
        )

    lines.extend(["", "### Known Limitations", ""])
    for item in customer["known_limitations"]:
        lines.extend(
            [
                f"- **{item['title']}**: {item['description']}",
                f"  Mitigation: {item['mitigation']}",
            ]
        )

    lines.extend(["", "### Follow-Up Milestones", ""])
    for milestone in customer["follow_up_milestones"]:
        lines.extend(
            [
                f"- **{milestone['name']}**: {milestone['success_signal']}",
                f"  Owner: {milestone['owner']}; source ideas: {', '.join(milestone['source_idea_ids']) or 'design brief'}",
            ]
        )

    lines.extend(
        [
            "",
            "## Internal Notes",
            "",
            f"- Release stage: {summary['release_stage']}",
            f"- Internal summary: {internal['release_summary']}",
            f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
            "",
            "### Validation Evidence",
            "",
        ]
    )
    if internal["validation_evidence"]:
        for item in internal["validation_evidence"]:
            lines.extend(
                [
                    f"- **{item['id']}** ({item['kind']}): {item['summary']}",
                    f"  Source ideas: {', '.join(item['source_idea_ids']) or 'design brief'}",
                ]
            )
    else:
        lines.append("- None available yet.")

    lines.extend(["", "### Support Handoff", ""])
    for item in internal["support_handoff"]:
        lines.extend(
            [
                f"- **{item['topic']}**: {item['detail']}",
                f"  Owner: {item['owner']}; source ideas: {', '.join(item['source_idea_ids']) or 'design brief'}",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def release_notes_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for release notes exports."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    title = _filename_part(str(design_brief.get("title") or "release-notes"))
    return f"{brief_id}-{title}-release-notes.{extension}"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    customer = report.get("customer_facing") or {}
    internal = report.get("internal") or {}
    release_stage = (report.get("summary") or {}).get("release_stage")

    for item in customer.get("shipped_capabilities") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _csv_row(
                report,
                item,
                audience="customer",
                category="shipped_capabilities",
                item_id=item.get("id"),
                title=item.get("title"),
                summary=item.get("description"),
                impact=item.get("customer_value"),
                rollout_or_version=release_stage,
            )
        )

    for item in customer.get("target_users") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _csv_row(
                report,
                item,
                audience="customer",
                category="target_users",
                item_id=item.get("id"),
                title=item.get("name"),
                summary=item.get("reason"),
                impact="Included in release targeting.",
                rollout_or_version=release_stage,
            )
        )

    for item in customer.get("rollout_notes") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _csv_row(
                report,
                item,
                audience="customer",
                category="rollout_notes",
                item_id=item.get("id"),
                title=item.get("stage"),
                summary=item.get("note"),
                rollout_or_version=item.get("stage"),
                action_required=item.get("note"),
                owner=item.get("owner"),
            )
        )

    for item in customer.get("known_limitations") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _csv_row(
                report,
                item,
                audience="customer",
                category="known_limitations",
                item_id=item.get("id"),
                title=item.get("title"),
                summary=item.get("description"),
                impact=item.get("description"),
                rollout_or_version=release_stage,
                action_required=item.get("mitigation"),
            )
        )

    for item in customer.get("follow_up_milestones") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _csv_row(
                report,
                item,
                audience="customer",
                category="follow_up_milestones",
                item_id=item.get("id"),
                title=item.get("name"),
                summary=item.get("success_signal"),
                impact=item.get("success_signal"),
                rollout_or_version=release_stage,
                action_required=item.get("name"),
                owner=item.get("owner"),
            )
        )

    for item in internal.get("validation_evidence") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _csv_row(
                report,
                item,
                audience="internal",
                category="validation_evidence",
                item_id=item.get("id"),
                title=item.get("id"),
                summary=item.get("summary"),
                impact=item.get("kind"),
                rollout_or_version=release_stage,
                evidence_refs=[item.get("id")],
            )
        )

    for item in internal.get("support_handoff") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _csv_row(
                report,
                item,
                audience="internal",
                category="support_handoff",
                item_id=item.get("id"),
                title=item.get("topic"),
                summary=item.get("detail"),
                impact=item.get("detail"),
                rollout_or_version=release_stage,
                action_required=item.get("detail"),
                owner=item.get("owner"),
            )
        )

    return rows


def _csv_row(
    report: dict[str, Any],
    item: dict[str, Any],
    **values: Any,
) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    row = {
        "schema_version": report.get("schema_version"),
        "kind": report.get("kind"),
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "design_status": brief.get("design_status"),
        "readiness_score": brief.get("readiness_score"),
        "source_idea_ids": item.get("source_idea_ids"),
        "source_fields": item.get("source_fields"),
        **values,
    }
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ";".join(_csv_text(item) for item in value if _csv_text(item))
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _release_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("release sponsor", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("value_proposition"),
        lead_idea and lead_idea.get("solution"),
        f"{title} helps {target_user} complete {workflow}.",
    )
    validation = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        "Validate first-use outcomes with the initial release cohort.",
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    primary_scope = scope[0] if scope else f"first usable {title} workflow"
    if not scope:
        fallbacks.append("mvp_scope")
    headline = f"{title} is ready for {target_user}"
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "value_proposition": concept,
        "validation_plan": validation,
        "primary_scope": primary_scope,
        "headline": headline,
        "customer_overview": (
            f"{title} introduces {concept} The first release focuses on "
            f"{primary_scope} for teams working through {workflow}."
        ),
        "internal_summary": (
            f"Release {title} to {target_user} with {buyer} visibility, validate via: {validation}"
        ),
        "fallbacks_used": fallbacks,
    }


def _shipped_capabilities(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    scopes = _string_list(design_brief.get("mvp_scope"))
    if not scopes:
        scopes = [context["primary_scope"]]
    return [
        {
            "id": f"CAP{index}",
            "title": _sentence_title(scope),
            "description": f"Shipped support for {scope} in {context['workflow_context']}.",
            "customer_value": f"Helps {context['target_user']} make progress without the prior workaround.",
            "source_fields": ["mvp_scope", "workflow_context", "specific_user"],
            "source_idea_ids": source_ids,
        }
        for index, scope in enumerate(scopes[:5], start=1)
    ]


def _target_users(context: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "primary_user",
            "name": context["target_user"],
            "reason": f"Owns or directly performs {context['workflow_context']}.",
            "source_fields": ["specific_user", "workflow_context"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "release_sponsor",
            "name": context["buyer"],
            "reason": "Needs rollout visibility, adoption signals, and escalation context.",
            "source_fields": ["buyer", "readiness_score", "design_status"],
            "source_idea_ids": source_ids,
        },
    ]


def _rollout_notes(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    status = str(design_brief.get("design_status") or "unknown")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    return [
        {
            "id": "RN1",
            "stage": "Availability",
            "note": f"Release through a controlled rollout for {context['target_user']} first.",
            "owner": "Product lead",
            "source_fields": ["specific_user", "design_status"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "RN2",
            "stage": "Launch gate",
            "note": f"Current gate is `{_release_stage(design_brief)}` from status `{status}` and readiness {readiness:.1f}/100.",
            "owner": "Release owner",
            "source_fields": ["design_status", "readiness_score"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "RN3",
            "stage": "Validation",
            "note": context["validation_plan"],
            "owner": "Research lead",
            "source_fields": ["validation_plan"],
            "source_idea_ids": source_ids,
        },
    ]


def _known_limitations(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )
    if not risks:
        risks = ["No explicit launch limitation was captured in the design brief."]
    return [
        {
            "id": f"KL{index}",
            "title": "Launch limitation" if index == 1 else f"Launch limitation {index}",
            "description": risk,
            "mitigation": (
                f"Keep access focused on {context['primary_scope']} and route unresolved feedback to the release owner."
            ),
            "source_fields": ["risks", "mvp_scope"],
            "source_idea_ids": source_ids,
        }
        for index, risk in enumerate(risks[:5], start=1)
    ]


def _validation_evidence(
    store: Store, design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field in ("why_this_now", "synthesis_rationale", "validation_plan"):
        text = _first_text(design_brief.get(field))
        if text:
            refs.append(
                {
                    "kind": "brief_field",
                    "id": f"design_brief.{field}",
                    "summary": text,
                    "source_idea_ids": _string_list(design_brief.get("source_idea_ids")),
                }
            )

    signal_sources: dict[str, list[str]] = {}
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            signal_sources.setdefault(signal_id, []).append(idea["id"])
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "kind": "insight",
                    "id": insight_id,
                    "summary": f"Inspiring insight linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )

    for signal_id in sorted(signal_sources):
        signal = store.get_signal(signal_id)
        if signal:
            source_type = (
                signal.source_type.value
                if hasattr(signal.source_type, "value")
                else str(signal.source_type)
            )
            summary = signal.title
            refs.append(
                {
                    "kind": "signal",
                    "id": signal.id,
                    "summary": summary,
                    "source_type": source_type,
                    "source_adapter": signal.source_adapter,
                    "url": signal.url,
                    "credibility": round(float(signal.credibility or 0.0), 2),
                    "tags": list(signal.tags),
                    "source_idea_ids": list(dict.fromkeys(signal_sources[signal_id])),
                }
            )
        else:
            refs.append(
                {
                    "kind": "signal",
                    "id": signal_id,
                    "summary": "Evidence signal linked to source ideas but not available in the store.",
                    "source_idea_ids": list(dict.fromkeys(signal_sources[signal_id])),
                }
            )
    return _dedupe_refs(refs)


def _support_handoff(
    context: dict[str, Any], limitations: list[dict[str, Any]], source_ids: list[str]
) -> list[dict[str, Any]]:
    primary_limitation = (
        limitations[0]["description"] if limitations else "No explicit limitation captured."
    )
    return [
        {
            "id": "SH1",
            "topic": "Primary support path",
            "detail": f"Help {context['target_user']} complete {context['workflow_context']} and capture first-use outcomes.",
            "owner": "Support owner",
            "source_fields": ["specific_user", "workflow_context", "validation_plan"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "SH2",
            "topic": "Scope clarification",
            "detail": f"The release scope is {context['primary_scope']}.",
            "owner": "Product lead",
            "source_fields": ["mvp_scope"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "SH3",
            "topic": "Escalation trigger",
            "detail": f"Escalate when customer impact touches: {primary_limitation}",
            "owner": "Release owner",
            "source_fields": ["risks"],
            "source_idea_ids": source_ids,
        },
    ]


def _follow_up_milestones(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    milestones = _string_list(design_brief.get("first_milestones"))
    if not milestones:
        milestones = [
            f"Review first-release evidence for {context['primary_scope']}",
            "Decide whether to expand, revise, or pause rollout",
        ]
    return [
        {
            "id": f"FM{index}",
            "name": milestone,
            "owner": "Product lead" if index == 1 else "Release owner",
            "success_signal": f"Milestone reviewed with evidence from {context['workflow_context']}.",
            "source_fields": ["first_milestones", "workflow_context"],
            "source_idea_ids": source_ids,
        }
        for index, milestone in enumerate(milestones[:5], start=1)
    ]


def _release_stage(design_brief: dict[str, Any]) -> str:
    status = str(design_brief.get("design_status") or "")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_customer_rollout"
    if status in {"approved", "published"}:
        return "approved_needs_validation"
    return "internal_draft"


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


def _first_with_label(fallbacks: list[str], field: str, *candidates: tuple[Any, str]) -> str:
    for value, label in candidates:
        text = _first_text(value) if not isinstance(value, list) else _first_text(*value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe_strings(values)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for ref in refs:
        deduped.setdefault((ref["kind"], ref["id"]), ref)
    return list(deduped.values())


def _sentence_title(value: str) -> str:
    text = _compact(value).rstrip(".")
    return text[:1].upper() + text[1:] if text else "Release capability"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "design-brief"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
