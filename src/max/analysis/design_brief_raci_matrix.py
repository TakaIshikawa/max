"""Deterministic RACI matrix export for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.raci_matrix.v1"


CSV_COLUMNS: tuple[str, ...] = (
    "activity_id",
    "phase",
    "phase_id",
    "activity",
    "responsible",
    "accountable",
    "consulted",
    "informed",
    "ownership_status",
    "gap_ids",
    "source_fields",
    "source_idea_ids",
    "source_summary",
)


PHASE_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "alignment",
        "title": "Alignment",
        "description": "Confirm buyer, user, and decision ownership before implementation handoff.",
    },
    {
        "id": "implementation_handoff",
        "title": "Implementation Handoff",
        "description": "Translate the brief into build ownership, support needs, and playbook inputs.",
    },
    {
        "id": "validation",
        "title": "Validation",
        "description": "Run the validation plan and resolve buyer-visible risks.",
    },
    {
        "id": "launch_readiness",
        "title": "Launch Readiness",
        "description": "Sequence launch checklist decisions and operational escalation ownership.",
    },
)

REQUIRED_ROLE_SIGNALS: tuple[dict[str, str], ...] = (
    {
        "field": "buyer",
        "role": "buyer",
        "message": "Buyer or accountable sponsor is not explicit in the brief lineage.",
    },
    {
        "field": "specific_user",
        "role": "primary_user",
        "message": "Primary user or workflow owner is not explicit in the brief lineage.",
    },
    {
        "field": "validation_plan",
        "role": "validation_owner",
        "message": "Validation plan ownership needs confirmation before handoff.",
    },
    {
        "field": "risks",
        "role": "risk_approver",
        "message": "Risk approver is not explicit because no risks are captured.",
    },
    {
        "field": "support_needs",
        "role": "support_playbook_owner",
        "message": "Support or playbook owner is not explicit in the brief lineage.",
    },
)


def build_design_brief_raci_matrix(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic RACI matrix from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _raci_context(design_brief, source_ideas)
    gaps = _ownership_gaps(context)
    activities = _activities(design_brief, source_ideas, source_idea_ids, context, gaps)
    phases = _phases(activities)
    role_assignments = _role_assignments(activities)
    escalation_notes = _escalation_notes(design_brief, context, gaps)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.raci_matrix",
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
            "buyer": context["buyer"],
            "specific_user": context["specific_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "phase_count": len(phases),
            "activity_count": len(activities),
            "role_count": len(role_assignments),
            "gap_count": len(gaps),
            "escalation_note_count": len(escalation_notes),
            "source_idea_count": len(source_idea_ids),
        },
        "raci_context": context,
        "phases": phases,
        "activities": activities,
        "role_assignments": role_assignments,
        "gaps": gaps,
        "escalation_notes": escalation_notes,
        "source_ideas": source_ideas,
    }


def render_design_brief_raci_matrix(matrix: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a RACI matrix as Markdown, deterministic JSON, or parseable CSV."""
    if fmt == "json":
        return json.dumps(matrix, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(matrix)
    if fmt != "markdown":
        raise ValueError(f"Unsupported RACI matrix format: {fmt}")

    brief = matrix["design_brief"]
    lines = [
        f"# RACI Matrix: {brief['title']}",
        "",
        f"Schema: `{matrix['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {brief['buyer']}",
        f"User: {brief['specific_user']}",
        f"Workflow: {brief['workflow_context']}",
        f"Ownership gaps: {matrix['summary']['gap_count']}",
        "",
    ]

    for phase in matrix["phases"]:
        lines.extend(
            [
                f"## {phase['title']}",
                "",
                phase["description"],
                "",
                "| Activity | Responsible | Accountable | Consulted | Informed | Gaps |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for activity in phase["activities"]:
            lines.append(
                "| "
                f"{activity['activity']} | "
                f"{activity['responsible_role']} | "
                f"{activity['accountable_role']} | "
                f"{_inline_list(activity['consulted_roles'])} | "
                f"{_inline_list(activity['informed_roles'])} | "
                f"{_inline_list(activity['gap_ids'])} |"
            )
        lines.append("")

    lines.extend(["## Ownership Gaps", ""])
    if matrix["gaps"]:
        lines.extend(f"- **{gap['id']}** ({gap['field']}): {gap['message']}" for gap in matrix["gaps"])
    else:
        lines.append("- None")

    lines.extend(["", "## Escalation Notes", ""])
    lines.extend(f"- {note}" for note in matrix["escalation_notes"])
    return "\n".join(lines).rstrip() + "\n"


def raci_matrix_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-raci-matrix.{extension}"
    )


def _render_csv(matrix: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(matrix):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(matrix: dict[str, Any]) -> list[dict[str, str]]:
    phases_by_id = {phase["id"]: phase["title"] for phase in matrix["phases"]}
    return [
        _csv_row(activity, phase=phases_by_id.get(activity.get("phase_id"), ""))
        for activity in matrix["activities"]
    ]


def _csv_row(activity: dict[str, Any], *, phase: str) -> dict[str, str]:
    row = {
        "activity_id": activity.get("id"),
        "phase": phase,
        "phase_id": activity.get("phase_id"),
        "activity": activity.get("activity"),
        "responsible": activity.get("responsible_role"),
        "accountable": activity.get("accountable_role"),
        "consulted": activity.get("consulted_roles"),
        "informed": activity.get("informed_roles"),
        "ownership_status": activity.get("ownership_status"),
        "gap_ids": activity.get("gap_ids"),
        "source_fields": activity.get("source_fields"),
        "source_idea_ids": activity.get("source_idea_ids"),
        "source_summary": activity.get("source_summary"),
    }
    return {column: _csv_cell(row.get(column)) for column in CSV_COLUMNS}


def _raci_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    buyer = _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"))
    specific_user = _first_text(
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
    )
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
    )
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    validation = _first_text(design_brief.get("validation_plan"), _field_values(source_ideas, "validation_plan"))
    support_needs = _support_needs(design_brief, source_ideas, risks)
    role_signals = _role_signals(buyer, specific_user, workflow, risks, validation, support_needs)

    return {
        "buyer": buyer or "TBD buyer owner",
        "specific_user": specific_user or "TBD primary user",
        "workflow_context": workflow or f"{design_brief['title']} workflow",
        "risks": risks,
        "validation_plan": validation,
        "support_needs": support_needs,
        "role_signals": role_signals,
        "missing_role_fields": [
            field
            for field, value in (
                ("buyer", buyer),
                ("specific_user", specific_user),
                ("validation_plan", validation),
                ("risks", risks),
                ("support_needs", support_needs),
            )
            if not value
        ],
    }


def _role_signals(
    buyer: str,
    specific_user: str,
    workflow: str,
    risks: list[str],
    validation: str,
    support_needs: str,
) -> dict[str, str]:
    risk_text = " ".join(risks).lower()
    risk_role = "Security/legal approver" if any(term in risk_text for term in ("security", "privacy", "legal", "compliance")) else "Risk approver"
    return {
        "product_lead": "Product lead",
        "buyer": buyer or "TBD buyer owner",
        "primary_user": specific_user or "TBD primary user",
        "implementation_owner": "Engineering lead" if workflow or validation else "TBD implementation owner",
        "validation_owner": specific_user or ("Validation owner" if validation else "TBD validation owner"),
        "risk_approver": risk_role if risks else "TBD risk approver",
        "support_playbook_owner": "Support/playbook owner" if support_needs else "TBD support/playbook owner",
    }


def _ownership_gaps(context: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    missing_fields = set(context.get("missing_role_fields") or [])
    for item in REQUIRED_ROLE_SIGNALS:
        value = context.get(item["field"])
        is_missing = item["field"] in missing_fields or not value
        if isinstance(value, list):
            is_missing = item["field"] in missing_fields or not value
        if is_missing:
            gaps.append(
                {
                    "id": f"gap-{len(gaps) + 1}",
                    "field": item["field"],
                    "role": item["role"],
                    "message": item["message"],
                    "resolution": f"Name the {item['role'].replace('_', ' ')} before treating related RACI rows as final.",
                }
            )
    return gaps


def _activities(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    context: dict[str, Any],
    gaps: list[dict[str, str]],
) -> list[dict[str, Any]]:
    roles = context["role_signals"]
    gap_ids = {gap["field"]: gap["id"] for gap in gaps}
    specs = [
        {
            "phase_id": "alignment",
            "activity": "Confirm buyer outcome and approval path.",
            "responsible_role": roles["product_lead"],
            "accountable_role": roles["buyer"],
            "consulted_roles": [roles["primary_user"], roles["risk_approver"]],
            "informed_roles": [roles["implementation_owner"]],
            "source_fields": ["buyer", "why_this_now", "synthesis_rationale"],
            "gap_fields": ["buyer"],
        },
        {
            "phase_id": "alignment",
            "activity": "Validate target workflow, primary user, and adoption constraints.",
            "responsible_role": roles["primary_user"],
            "accountable_role": roles["product_lead"],
            "consulted_roles": [roles["buyer"]],
            "informed_roles": [roles["implementation_owner"], roles["support_playbook_owner"]],
            "source_fields": ["specific_user", "workflow_context", "current_workaround"],
            "gap_fields": ["specific_user"],
        },
        {
            "phase_id": "implementation_handoff",
            "activity": "Convert MVP scope and milestones into implementation ownership.",
            "responsible_role": roles["implementation_owner"],
            "accountable_role": roles["product_lead"],
            "consulted_roles": [roles["primary_user"]],
            "informed_roles": [roles["buyer"]],
            "source_fields": ["mvp_scope", "first_milestones", "tech_approach", "suggested_stack"],
            "gap_fields": [],
        },
        {
            "phase_id": "implementation_handoff",
            "activity": "Prepare support and playbook handoff for pilot operators.",
            "responsible_role": roles["support_playbook_owner"],
            "accountable_role": roles["product_lead"],
            "consulted_roles": [roles["primary_user"], roles["implementation_owner"]],
            "informed_roles": [roles["buyer"]],
            "source_fields": ["support_needs", "workflow_context", "validation_plan", "domain_risks"],
            "gap_fields": ["support_needs"],
        },
        {
            "phase_id": "validation",
            "activity": "Run validation plan and capture decision evidence.",
            "responsible_role": roles["validation_owner"],
            "accountable_role": roles["product_lead"],
            "consulted_roles": [roles["buyer"], roles["primary_user"]],
            "informed_roles": [roles["implementation_owner"]],
            "source_fields": ["validation_plan", "first_10_customers", "evidence_rationale"],
            "gap_fields": ["validation_plan"],
        },
        {
            "phase_id": "validation",
            "activity": "Review risks, mitigations, and buyer-visible blockers.",
            "responsible_role": roles["risk_approver"],
            "accountable_role": roles["product_lead"],
            "consulted_roles": [roles["implementation_owner"], roles["support_playbook_owner"]],
            "informed_roles": [roles["buyer"]],
            "source_fields": ["risks", "domain_risks"],
            "gap_fields": ["risks"],
        },
        {
            "phase_id": "launch_readiness",
            "activity": "Complete launch checklist and go/no-go decision.",
            "responsible_role": roles["product_lead"],
            "accountable_role": roles["buyer"],
            "consulted_roles": [roles["implementation_owner"], roles["risk_approver"]],
            "informed_roles": [roles["primary_user"], roles["support_playbook_owner"]],
            "source_fields": ["design_status", "readiness_score", "first_milestones"],
            "gap_fields": ["buyer"],
        },
        {
            "phase_id": "launch_readiness",
            "activity": "Set escalation path for support, risk, and rollout decisions.",
            "responsible_role": roles["support_playbook_owner"],
            "accountable_role": roles["product_lead"],
            "consulted_roles": [roles["risk_approver"], roles["implementation_owner"]],
            "informed_roles": [roles["buyer"], roles["primary_user"]],
            "source_fields": ["support_needs", "risks", "validation_plan"],
            "gap_fields": ["support_needs", "risks"],
        },
    ]

    activities = []
    for index, spec in enumerate(specs, start=1):
        activity_gap_ids = [gap_ids[field] for field in spec.pop("gap_fields") if field in gap_ids]
        fields = tuple(spec["source_fields"])
        activities.append(
            {
                "id": f"DBRACI{index}",
                **spec,
                "consulted_roles": _dedupe(spec["consulted_roles"]),
                "informed_roles": _dedupe(spec["informed_roles"]),
                "source_idea_ids": _source_ids_for_fields(source_ideas, fields, source_idea_ids),
                "source_summary": _source_summary(design_brief, source_ideas, fields, context),
                "gap_ids": activity_gap_ids,
                "ownership_status": "gap" if activity_gap_ids else "assigned",
            }
        )
    return activities


def _phases(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    activities_by_phase: dict[str, list[dict[str, Any]]] = {}
    for activity in activities:
        activities_by_phase.setdefault(activity["phase_id"], []).append(activity)
    return [
        {
            "id": config["id"],
            "title": config["title"],
            "description": config["description"],
            "activities": activities_by_phase.get(config["id"], []),
        }
        for config in PHASE_CONFIGS
    ]


def _role_assignments(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    for activity in activities:
        for field, bucket in (
            ("responsible_role", "responsible_activity_ids"),
            ("accountable_role", "accountable_activity_ids"),
        ):
            role = activity[field]
            assignments.setdefault(
                role,
                {
                    "role": role,
                    "responsible_activity_ids": [],
                    "accountable_activity_ids": [],
                    "consulted_activity_ids": [],
                    "informed_activity_ids": [],
                },
            )[bucket].append(activity["id"])
        for role in activity["consulted_roles"]:
            assignments.setdefault(
                role,
                {
                    "role": role,
                    "responsible_activity_ids": [],
                    "accountable_activity_ids": [],
                    "consulted_activity_ids": [],
                    "informed_activity_ids": [],
                },
            )["consulted_activity_ids"].append(activity["id"])
        for role in activity["informed_roles"]:
            assignments.setdefault(
                role,
                {
                    "role": role,
                    "responsible_activity_ids": [],
                    "accountable_activity_ids": [],
                    "consulted_activity_ids": [],
                    "informed_activity_ids": [],
                },
            )["informed_activity_ids"].append(activity["id"])
    return [assignments[role] for role in sorted(assignments)]


def _escalation_notes(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    gaps: list[dict[str, str]],
) -> list[str]:
    notes = [
        "Escalate any activity marked with an ownership gap to the product lead before implementation starts.",
        f"Use {context['buyer']} as accountable launch sponsor only after buyer authority is confirmed.",
        "Treat validation results as the decision record for launch readiness and rollout scope.",
    ]
    if context["risks"]:
        notes.append(f"Route top risk to {context['role_signals']['risk_approver']}: {context['risks'][0]}")
    if design_brief.get("design_status") not in {"approved", "published"}:
        notes.insert(0, "Design brief is not approved; use this matrix as planning input, not final handoff.")
    if gaps:
        fields = ", ".join(gap["field"] for gap in gaps)
        notes.insert(0, f"Resolve explicit ownership gaps before final handoff: {fields}.")
    return _dedupe(notes)


def _support_needs(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    risks: list[str],
) -> str:
    validation = _first_text(design_brief.get("validation_plan"), _field_values(source_ideas, "validation_plan"))
    workflow = _first_text(design_brief.get("workflow_context"), _field_values(source_ideas, "workflow_context"))
    milestones = "; ".join(_string_list(design_brief.get("first_milestones")))
    playbook = _joined_fields(source_ideas, ("composability_notes", "tech_approach"))
    if validation and workflow:
        return f"Support {workflow} while capturing validation evidence: {validation}"
    if milestones and playbook:
        return f"Prepare pilot playbook for {milestones}: {playbook}"
    if risks:
        return f"Support plan should cover top risk: {risks[0]}"
    return ""


def _source_summary(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    fields: tuple[str, ...],
    context: dict[str, Any],
) -> str:
    values: list[str] = []
    for field in fields:
        if field == "support_needs":
            values.extend(_string_list(context.get("support_needs")))
        elif field == "risks":
            values.extend(_string_list(design_brief.get("risks")))
        else:
            values.extend(_string_list(design_brief.get(field)))
        values.extend(_field_values(source_ideas, field))
    return "; ".join(_dedupe(values)) or "No specific source text captured for this RACI row."


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


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _joined_fields(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for field in fields:
        values.extend(_field_values(source_ideas, field))
    return "; ".join(_dedupe(values))


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
        return [_compact(f"{key}: {item}") for key, item in value.items() if _compact(key)]
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _compact("; ".join(value))
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _compact(value)


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
