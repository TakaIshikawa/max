"""Deterministic pilot outreach pack export for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.outreach_pack.v1"

OUTREACH_PACK_CSV_COLUMNS: tuple[str, ...] = (
    "section",
    "type",
    "order",
    "id",
    "title_name",
    "channel_stage",
    "body_detail",
    "cta",
    "evidence_source_idea_ids",
    "design_brief_id",
    "design_brief_title",
    "design_brief_domain",
    "design_brief_theme",
    "design_status",
    "readiness_score",
    "buyer",
    "specific_user",
    "workflow_context",
    "value_proposition",
)


def build_design_brief_outreach_pack(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a recruiting outreach pack from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _audience_context(design_brief, source_ideas, lead_idea)
    target_segments = _target_segments(design_brief, source_ideas, context, source_idea_ids)
    hypotheses = _outreach_hypotheses(design_brief, source_ideas, context, source_idea_ids)
    templates = _templates(design_brief, context, target_segments, source_idea_ids)
    objections = _objection_handling(design_brief, source_ideas, source_idea_ids)
    questions = _qualification_questions(design_brief, context, source_idea_ids)
    follow_up = _follow_up_artifacts(design_brief, context, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.outreach_pack",
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
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "pilot_goal": f"Recruit validation pilots for {design_brief['title']}.",
            "buyer": context["buyer"],
            "specific_user": context["specific_user"],
            "workflow_context": context["workflow_context"],
            "value_proposition": context["value_proposition"],
            "fallbacks_used": context["fallbacks_used"],
            "target_segment_count": len(target_segments),
            "template_count": len(templates),
            "qualification_question_count": len(questions),
        },
        "target_segments": target_segments,
        "outreach_hypotheses": hypotheses,
        "templates": templates,
        "objection_handling": objections,
        "qualification_questions": questions,
        "follow_up_artifacts": follow_up,
        "source_ideas": source_ideas,
    }


def render_design_brief_outreach_pack(pack: dict[str, Any], fmt: str = "json") -> str:
    """Render the outreach pack as JSON, CSV, or Markdown."""
    if fmt == "json":
        return json.dumps(pack, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(pack)
    if fmt != "markdown":
        raise ValueError(f"Unsupported outreach pack format: {fmt}")

    brief = pack["design_brief"]
    summary = pack["summary"]
    lines = [
        f"# Outreach Pack: {brief['title']}",
        "",
        f"Schema: `{pack['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Recruiting Context",
        "",
        f"- Pilot goal: {summary['pilot_goal']}",
        f"- Buyer: {summary['buyer']}",
        f"- Specific user: {summary['specific_user']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Value proposition: {summary['value_proposition']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Target Segments",
        "",
    ]

    for segment in pack["target_segments"]:
        lines.extend(
            [
                f"### {segment['name']}",
                "",
                f"- Buyer: {segment['buyer']}",
                f"- User: {segment['user']}",
                f"- Workflow: {segment['workflow_context']}",
                f"- Recruiting angle: {segment['recruiting_angle']}",
                f"- Inclusion signal: {segment['inclusion_signal']}",
                f"- Exclusion signal: {segment['exclusion_signal']}",
                f"- Source ideas: {', '.join(segment['source_idea_ids']) or 'design brief'}",
                "",
            ]
        )

    lines.extend(["## Outreach Hypotheses", ""])
    for hypothesis in pack["outreach_hypotheses"]:
        lines.extend(
            [
                f"### {hypothesis['id']}: {hypothesis['hypothesis']}",
                "",
                f"- Why it should work: {hypothesis['rationale']}",
                f"- Evidence to capture: {hypothesis['evidence_to_capture']}",
                f"- Success signal: {hypothesis['success_signal']}",
                "",
            ]
        )

    lines.extend(["## Templates", ""])
    for template in pack["templates"]:
        lines.extend(
            [
                f"### {template['name']}",
                "",
                f"- Channel: {template['channel']}",
                f"- Subject: {template['subject']}",
                "",
                template["body"],
                "",
                f"- CTA: {template['call_to_action']}",
                "",
            ]
        )

    lines.extend(["## Objection Handling", ""])
    for objection in pack["objection_handling"]:
        lines.extend(
            [
                f"### {objection['objection']}",
                "",
                f"- Response: {objection['response']}",
                f"- Proof to offer: {objection['proof_to_offer']}",
                f"- Escalation: {objection['escalation']}",
                "",
            ]
        )

    lines.extend(["## Qualification Questions", ""])
    for question in pack["qualification_questions"]:
        lines.append(f"- [{question['stage']}] {question['question']}")

    lines.extend(["", "## Follow-up Steps", ""])
    for artifact in pack["follow_up_artifacts"]:
        lines.extend(
            [
                f"### {artifact['name']}",
                "",
                f"- Timing: {artifact['timing']}",
                f"- Purpose: {artifact['purpose']}",
                f"- Owner: {artifact['owner']}",
                f"- Content: {artifact['content']}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_design_brief_outreach_pack(path: Path, pack: dict[str, Any], fmt: str = "json") -> None:
    """Write a rendered outreach pack to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_design_brief_outreach_pack(pack, fmt=fmt), encoding="utf-8")


def _render_csv(pack: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=OUTREACH_PACK_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(pack):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(pack: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for order, segment in enumerate(pack.get("target_segments") or [], start=1):
        rows.append(
            _csv_row(
                pack,
                section="target_segments",
                row_type="segment",
                order=order,
                item_id=segment.get("id"),
                title_name=segment.get("name"),
                body_detail=_csv_join(
                    [
                        f"Buyer: {_csv_text(segment.get('buyer'))}",
                        f"User: {_csv_text(segment.get('user'))}",
                        f"Workflow: {_csv_text(segment.get('workflow_context'))}",
                        f"Recruiting angle: {_csv_text(segment.get('recruiting_angle'))}",
                        f"Inclusion signal: {_csv_text(segment.get('inclusion_signal'))}",
                        f"Exclusion signal: {_csv_text(segment.get('exclusion_signal'))}",
                    ],
                    separator=" | ",
                ),
                evidence_source_idea_ids=segment.get("source_idea_ids"),
            )
        )

    for order, hypothesis in enumerate(pack.get("outreach_hypotheses") or [], start=1):
        rows.append(
            _csv_row(
                pack,
                section="outreach_hypotheses",
                row_type="hypothesis",
                order=order,
                item_id=hypothesis.get("id"),
                title_name=hypothesis.get("hypothesis"),
                body_detail=_csv_join(
                    [
                        f"Rationale: {_csv_text(hypothesis.get('rationale'))}",
                        f"Evidence to capture: {_csv_text(hypothesis.get('evidence_to_capture'))}",
                        f"Success signal: {_csv_text(hypothesis.get('success_signal'))}",
                    ],
                    separator=" | ",
                ),
                evidence_source_idea_ids=hypothesis.get("source_idea_ids"),
            )
        )

    for order, template in enumerate(pack.get("templates") or [], start=1):
        rows.append(
            _csv_row(
                pack,
                section="templates",
                row_type="template",
                order=order,
                item_id=template.get("id"),
                title_name=template.get("name"),
                channel_stage=template.get("channel"),
                body_detail=_csv_join(
                    [
                        f"Subject: {_csv_text(template.get('subject'))}",
                        template.get("body"),
                    ],
                    separator=" | ",
                ),
                cta=template.get("call_to_action"),
                evidence_source_idea_ids=template.get("source_idea_ids"),
            )
        )

    for order, objection in enumerate(pack.get("objection_handling") or [], start=1):
        rows.append(
            _csv_row(
                pack,
                section="objection_handling",
                row_type="objection",
                order=order,
                item_id=objection.get("id"),
                title_name=objection.get("objection"),
                body_detail=_csv_join(
                    [
                        f"Response: {_csv_text(objection.get('response'))}",
                        f"Proof to offer: {_csv_text(objection.get('proof_to_offer'))}",
                        f"Escalation: {_csv_text(objection.get('escalation'))}",
                    ],
                    separator=" | ",
                ),
                evidence_source_idea_ids=objection.get("source_idea_ids"),
            )
        )

    for order, question in enumerate(pack.get("qualification_questions") or [], start=1):
        rows.append(
            _csv_row(
                pack,
                section="qualification_questions",
                row_type="qualification_question",
                order=order,
                item_id=question.get("id"),
                title_name=question.get("question"),
                channel_stage=question.get("stage"),
                body_detail=question.get("question"),
                evidence_source_idea_ids=question.get("source_idea_ids"),
            )
        )

    for order, artifact in enumerate(pack.get("follow_up_artifacts") or [], start=1):
        rows.append(
            _csv_row(
                pack,
                section="follow_up_artifacts",
                row_type="follow_up_artifact",
                order=order,
                item_id=artifact.get("id"),
                title_name=artifact.get("name"),
                channel_stage=artifact.get("timing"),
                body_detail=_csv_join(
                    [
                        f"Purpose: {_csv_text(artifact.get('purpose'))}",
                        f"Owner: {_csv_text(artifact.get('owner'))}",
                        f"Content: {_csv_text(artifact.get('content'))}",
                    ],
                    separator=" | ",
                ),
                evidence_source_idea_ids=artifact.get("source_idea_ids"),
            )
        )

    return rows


def _csv_row(pack: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = pack.get("design_brief") or {}
    summary = pack.get("summary") or {}
    row = {
        "section": values.get("section"),
        "type": values.get("row_type"),
        "order": values.get("order"),
        "id": values.get("item_id"),
        "title_name": values.get("title_name"),
        "channel_stage": values.get("channel_stage"),
        "body_detail": values.get("body_detail"),
        "cta": values.get("cta"),
        "evidence_source_idea_ids": values.get("evidence_source_idea_ids"),
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "design_brief_domain": brief.get("domain"),
        "design_brief_theme": brief.get("theme"),
        "design_status": brief.get("design_status"),
        "readiness_score": brief.get("readiness_score"),
        "buyer": summary.get("buyer"),
        "specific_user": summary.get("specific_user"),
        "workflow_context": summary.get("workflow_context"),
        "value_proposition": summary.get("value_proposition"),
    }
    return {column: _csv_text(row.get(column)) for column in OUTREACH_PACK_CSV_COLUMNS}


def _audience_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("economic buyer (fallback: missing buyer)", "explicit_fallback"),
    )
    user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        ("target user (fallback: missing specific_user)", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        ("target workflow (fallback: missing workflow_context)", "explicit_fallback"),
    )
    value = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("value_proposition"),
        lead_idea and lead_idea.get("solution"),
        "Validate the proposed product concept with a narrow pilot cohort.",
    )
    problem = _first_text(
        lead_idea and lead_idea.get("problem"),
        "The current workflow has unresolved validation pain.",
    )
    workaround = _first_text(
        lead_idea and lead_idea.get("current_workaround"),
        "manual workaround or status quo process",
    )
    return {
        "buyer": buyer,
        "specific_user": user,
        "workflow_context": workflow,
        "value_proposition": value,
        "problem": problem,
        "current_workaround": workaround,
        "fallbacks_used": fallbacks,
    }


def _target_segments(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    context: dict[str, Any],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    adjacent_users = _dedupe_strings(_field_values(source_ideas, "specific_user"))
    if context["specific_user"] not in adjacent_users:
        adjacent_users.append(context["specific_user"])
    scope = _first_text("; ".join(_string_list(design_brief.get("mvp_scope"))), context["value_proposition"])
    return [
        {
            "id": "primary_workflow_owner",
            "name": "Primary workflow owners",
            "buyer": context["buyer"],
            "user": context["specific_user"],
            "workflow_context": context["workflow_context"],
            "recruiting_angle": f"Validate whether {scope} solves a high-friction step in {context['workflow_context']}.",
            "inclusion_signal": f"Owns or frequently performs {context['workflow_context']}.",
            "exclusion_signal": "No current pain, ownership, or decision influence around the workflow.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "economic_sponsors",
            "name": "Economic sponsors",
            "buyer": context["buyer"],
            "user": context["specific_user"],
            "workflow_context": context["workflow_context"],
            "recruiting_angle": "Test budget ownership, urgency, and pilot approval path.",
            "inclusion_signal": "Can approve pilot time, data access, or procurement next steps.",
            "exclusion_signal": "Cannot sponsor a pilot or name the approval owner.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "adjacent_evaluators",
            "name": "Adjacent evaluators",
            "buyer": context["buyer"],
            "user": ", ".join(adjacent_users[:3]) or context["specific_user"],
            "workflow_context": context["workflow_context"],
            "recruiting_angle": "Find nearby users who can compare the proposed workflow against the status quo.",
            "inclusion_signal": f"Currently uses {context['current_workaround']} or evaluates alternatives.",
            "exclusion_signal": "Too far from the workflow to provide concrete pilot feedback.",
            "source_idea_ids": source_ids,
        },
    ]


def _outreach_hypotheses(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    context: dict[str, Any],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    why_now = _first_text(design_brief.get("why_this_now"), *_field_values(source_ideas, "why_now"), "Timing is relevant now.")
    risk = _first_text(*_string_list(design_brief.get("risks")), *_source_risks(source_ideas), "Pilot risk is unknown.")
    return [
        {
            "id": "OH1",
            "hypothesis": f"{context['specific_user']} will respond to a workflow-pain message.",
            "rationale": context["problem"],
            "evidence_to_capture": "Reply rate, named pain severity, and willingness to schedule discovery.",
            "success_signal": "At least three qualified conversations from the first outreach cohort.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "OH2",
            "hypothesis": f"{context['buyer']} will sponsor a narrow validation pilot when urgency is framed around timing.",
            "rationale": why_now,
            "evidence_to_capture": "Sponsor priority, pilot approval path, and budget or time constraints.",
            "success_signal": "One sponsor agrees to define pilot success criteria.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "OH3",
            "hypothesis": "Named objections will reveal the highest-risk adoption blocker before build expansion.",
            "rationale": risk,
            "evidence_to_capture": "Objection frequency, severity, and required proof.",
            "success_signal": "Top two objections have mitigation or stop criteria.",
            "source_idea_ids": source_ids,
        },
    ]


def _templates(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    segments: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    title = design_brief["title"]
    workflow = context["workflow_context"]
    value = context["value_proposition"]
    return [
        {
            "id": "email_primary_user",
            "name": "Primary User Email",
            "channel": "email",
            "segment_id": segments[0]["id"],
            "subject": f"Question about {workflow}",
            "body": (
                f"Hi {{first_name}},\n\n"
                f"I am researching how {context['specific_user']} handle {workflow}. "
                f"The concept is: {value}\n\n"
                "Would you be open to a 20 minute discovery call to compare it against your current process? "
                "I am looking for concrete workflow feedback, not a sales commitment."
            ),
            "call_to_action": "Ask for a 20 minute discovery call this week.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "dm_sponsor",
            "name": "Sponsor DM",
            "channel": "direct_message",
            "segment_id": segments[1]["id"],
            "subject": f"Pilot validation for {title}",
            "body": (
                f"Hi {{first_name}}, I am validating {title} for teams where {workflow} creates measurable drag. "
                f"If this is on your roadmap, could I ask two questions about pilot fit and approval criteria?"
            ),
            "call_to_action": "Ask for permission to send two qualification questions.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "warm_intro",
            "name": "Warm Intro Request",
            "channel": "email",
            "segment_id": segments[2]["id"],
            "subject": f"Intro to someone who owns {workflow}",
            "body": (
                f"Hi {{first_name}}, do you know a {context['specific_user']} or {context['buyer']} "
                f"who owns {workflow}? I am recruiting validation pilots for {title} and need practical feedback "
                "from teams with an active workflow pain."
            ),
            "call_to_action": "Ask for one named intro to a workflow owner.",
            "source_idea_ids": source_ids,
        },
    ]


def _objection_handling(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    risk_text = _first_text(*_string_list(design_brief.get("risks")), *_source_risks(source_ideas), "The main adoption risk is not yet known.")
    return [
        {
            "id": "too_early",
            "objection": "This is too early for us.",
            "response": "Position the ask as discovery or a narrowly scoped pilot definition, not a purchase decision.",
            "proof_to_offer": "Share the MVP scope and ask what proof would make the pilot worth revisiting.",
            "escalation": "Move to a follow-up reminder after the next milestone.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "no_bandwidth",
            "objection": "We do not have bandwidth for a pilot.",
            "response": "Offer a lighter discovery call and ask what pilot shape would fit their operating rhythm.",
            "proof_to_offer": "Provide a one-page pilot plan with timebox, owner, and expected learning.",
            "escalation": "Qualify out if no owner can be named.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "risk_or_trust",
            "objection": risk_text,
            "response": "Acknowledge the risk and ask what evidence would be required before trial use.",
            "proof_to_offer": "Map the objection to validation criteria and a stop condition.",
            "escalation": "Record as a blocker if the proof cannot be produced within MVP scope.",
            "source_idea_ids": source_ids,
        },
    ]


def _qualification_questions(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    milestones = _string_list(design_brief.get("first_milestones"))
    milestone = milestones[0] if milestones else "the first pilot milestone"
    raw_questions = [
        ("fit", f"Who owns {context['workflow_context']} today, and how often does the problem occur?"),
        ("pain", f"What happens when {context['current_workaround']} fails or slows the team down?"),
        ("urgency", "Why solve this now instead of keeping the current process for another quarter?"),
        ("authority", f"Who besides {context['buyer']} must approve a validation pilot?"),
        ("success", f"What outcome would make {milestone} valuable enough to continue?"),
        ("constraints", "What data, security, integration, or workflow constraints would block pilot participation?"),
    ]
    return [
        {
            "id": f"QQ{index}",
            "stage": stage,
            "question": question,
            "source_idea_ids": source_ids,
        }
        for index, (stage, question) in enumerate(raw_questions, start=1)
    ]


def _follow_up_artifacts(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    validation = _first_text(design_brief.get("validation_plan"), "Run discovery and pilot fit interviews.")
    return [
        {
            "id": "FU1",
            "name": "Same-day call recap",
            "timing": "Within 24 hours of discovery call",
            "purpose": "Confirm pain, workflow, and next step accuracy.",
            "owner": "research_lead",
            "content": f"Summarize {context['workflow_context']} pain, current workaround, pilot interest, and open objections.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "FU2",
            "name": "Pilot success criteria",
            "timing": "After a qualified sponsor expresses interest",
            "purpose": "Convert discovery interest into a measurable pilot.",
            "owner": "product_lead",
            "content": f"Propose success criteria derived from the validation plan: {validation}",
            "source_idea_ids": source_ids,
        },
        {
            "id": "FU3",
            "name": "No-response follow-up",
            "timing": "3 to 5 business days after first outreach",
            "purpose": "Test whether the workflow pain or audience targeting is wrong.",
            "owner": "go_to_market_lead",
            "content": "Ask whether the recipient owns the workflow, can redirect to the owner, or has no current pain.",
            "source_idea_ids": source_ids,
        },
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


def _first_with_label(fallbacks: list[str], field: str, *candidates: tuple[Any, str]) -> str:
    for value, label in candidates:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [str(idea.get(field) or "") for idea in source_ideas if not idea.get("missing")]


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        risks.extend(_string_list(idea.get("domain_risks")))
    return _dedupe_strings(risks)


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
        text = _compact(value)
        if text:
            return text
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return _csv_join(value)
    if isinstance(value, tuple):
        return _csv_join(value)
    if isinstance(value, dict):
        return _csv_join(f"{key}: {item}" for key, item in sorted(value.items()))
    return _compact(value)


def _csv_join(values: Any, *, separator: str = ";") -> str:
    return separator.join(text for value in values if (text := _csv_text(value)))
