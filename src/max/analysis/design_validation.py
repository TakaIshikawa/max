"""Build deterministic validation plans for persisted design briefs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.validation_plan.v1"


def build_validation_plan(
    store: Store,
    design_brief: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a structured validation plan from persisted brief and idea fields."""
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    lead_or_brief = lead_idea or {}

    target_user = _first_text(
        design_brief.get("specific_user"),
        lead_or_brief.get("specific_user"),
        "the primary workflow owner",
    )
    buyer = _first_text(
        design_brief.get("buyer"),
        lead_or_brief.get("buyer"),
        "the budget owner for this workflow",
    )
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_or_brief.get("workflow_context"),
        "the target workflow",
    )
    concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_or_brief.get("solution"),
        design_brief.get("title"),
    )
    value_prop = _first_text(
        lead_or_brief.get("value_proposition"),
        design_brief.get("why_this_now"),
        concept,
    )
    workaround = _first_text(lead_or_brief.get("current_workaround"), "the current workaround")
    first_customers = _split_candidates(lead_or_brief.get("first_10_customers"))
    risks = list(dict.fromkeys([*design_brief.get("risks", []), *_source_risks(source_ideas)]))

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": generated,
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": design_brief.get("source_idea_ids", []),
        },
        "target_user_hypotheses": [
            {
                "id": "H1",
                "hypothesis": (
                    f"{target_user} has an urgent, repeated need in {workflow} that is "
                    f"not satisfied by {workaround}."
                ),
                "target_user": target_user,
                "buyer": buyer,
                "workflow_context": workflow,
                "rationale": _first_text(
                    lead_or_brief.get("problem"),
                    design_brief.get("why_this_now"),
                    "The persisted brief identifies this workflow as the core adoption surface.",
                ),
            },
            {
                "id": "H2",
                "hypothesis": f"{buyer} will support a pilot if {concept} creates a measurable improvement.",
                "target_user": target_user,
                "buyer": buyer,
                "workflow_context": workflow,
                "rationale": value_prop,
            },
            {
                "id": "H3",
                "hypothesis": (
                    f"A smoke-test page can convert qualified {target_user} prospects into "
                    "interview or pilot requests before the MVP is built."
                ),
                "target_user": target_user,
                "buyer": buyer,
                "workflow_context": workflow,
                "rationale": _first_text(
                    design_brief.get("validation_plan"),
                    lead_or_brief.get("validation_plan"),
                    "The first validation step should measure demand before implementation.",
                ),
            },
        ],
        "recruiting_criteria": {
            "target_sample_size": "8-12 interviews, with at least 5 matching the primary user profile",
            "ideal_participants": _ideal_participants(target_user, buyer, first_customers),
            "inclusion_criteria": [
                f"Owns or performs {workflow}",
                f"Matches the persisted target user: {target_user}",
                "Can describe recent attempts to solve the problem without prompting",
                "Can participate in a 30 minute discovery call within two weeks",
            ],
            "exclusion_criteria": [
                "No direct exposure to the target workflow",
                "Only interested in the category as a general observer",
                "Cannot discuss current process, tools, constraints, or buying path",
            ],
            "screener_questions": [
                f"What role do you play in {workflow}?",
                "How often did this workflow matter in the last 30 days?",
                f"What do you use today instead of {design_brief['title']}?",
                f"Who would approve a paid pilot for this workflow: you, {buyer}, or someone else?",
            ],
            "suggested_channels": first_customers
            or [
                "Existing warm network matching the buyer/user profile",
                "Communities where the target workflow is discussed",
                "Direct outreach to teams using adjacent tools",
            ],
        },
        "interview_script": {
            "duration_minutes": 30,
            "intro": (
                "Thanks for joining. We are validating a product direction, not selling a finished "
                "product. I am most interested in your current workflow and recent examples."
            ),
            "warmup_questions": [
                "What is your role and what outcomes are you responsible for?",
                f"Where does {workflow} fit into your week?",
            ],
            "problem_discovery_questions": [
                f"Walk me through the last time {workflow} was painful or risky.",
                "What triggered the work, who was involved, and what happened next?",
                f"What are you using today as {workaround}?",
                "What makes the current approach expensive, slow, risky, or unreliable?",
            ],
            "concept_reaction_questions": [
                f"If {concept} existed, where would it fit into your workflow?",
                f"Which part of this promise feels most valuable: {value_prop}?",
                "What would make this a must-have rather than a nice-to-have?",
                "What would block adoption even if the product worked?",
            ],
            "smoke_test_questions": [
                "Would you join a pilot waitlist after seeing this positioning?",
                "What proof would you need before sharing a work email or booking a demo?",
                "What pricing or procurement path would be realistic for a first pilot?",
            ],
            "closing_questions": [
                "Who else should we talk to?",
                "Can we follow up with a prototype or landing page once it is ready?",
            ],
        },
        "smoke_test_landing_page_copy": {
            "headline": design_brief["title"],
            "subheadline": value_prop,
            "primary_cta": "Request pilot access",
            "secondary_cta": "Book a discovery call",
            "problem_points": [
                _first_text(lead_or_brief.get("problem"), design_brief.get("why_this_now")),
                f"Current workaround: {workaround}",
                f"Critical workflow: {workflow}",
            ],
            "solution_bullets": _solution_bullets(design_brief, lead_or_brief),
            "proof_points": [
                f"Synthesized from {len(design_brief.get('source_idea_ids', [])) or 1} persisted source idea(s)",
                f"Readiness score: {float(design_brief.get('readiness_score') or 0.0):.1f}/100",
                f"Designed for {target_user} and {buyer}",
            ],
            "signup_form_fields": ["Work email", "Role", "Team size", "Current workaround"],
        },
        "success_metrics": [
            {
                "metric": "Qualified interview completion",
                "target": "8 completed interviews in 10 business days, 5+ from the primary profile",
                "rationale": "Enough signal to compare repeated pain patterns across target users.",
            },
            {
                "metric": "Problem intensity",
                "target": "60%+ rate the problem 4 or 5 out of 5",
                "rationale": "Confirms urgency before implementation.",
            },
            {
                "metric": "Smoke-test conversion",
                "target": "8%+ visitor-to-CTA conversion or 5+ qualified pilot requests",
                "rationale": "Tests demand for the persisted product concept.",
            },
            {
                "metric": "Pilot pull",
                "target": "3+ participants agree to review a prototype or pilot scope",
                "rationale": "Separates curiosity from buying intent.",
            },
        ],
        "failure_thresholds": [
            {
                "metric": "Qualified recruiting",
                "threshold": "Fewer than 5 qualified interviews booked by day 7",
                "action": "Narrow or revise the target user and recruiting channels.",
            },
            {
                "metric": "Problem intensity",
                "threshold": "Fewer than 40% rate the problem 4 or 5 out of 5",
                "action": "Revisit the problem framing before building.",
            },
            {
                "metric": "Smoke-test conversion",
                "threshold": "Below 3% CTA conversion with 100+ relevant visits",
                "action": "Change positioning or pause the concept.",
            },
            {
                "metric": "Risk concentration",
                "threshold": "3+ interviews cite the same adoption blocker",
                "action": "Convert the blocker into a design requirement or kill criterion.",
            },
        ],
        "two_week_timeline": [
            {
                "days": "1-2",
                "focus": "Prepare validation assets",
                "activities": [
                    "Finalize screener and interview script",
                    "Publish smoke-test landing page copy",
                    "Prepare outreach list from recruiting criteria",
                ],
            },
            {
                "days": "3-5",
                "focus": "Recruit and launch smoke test",
                "activities": [
                    "Send first outreach batch",
                    "Run first 3 discovery interviews",
                    "Review early landing page conversion and CTA quality",
                ],
            },
            {
                "days": "6-9",
                "focus": "Interview and synthesize",
                "activities": [
                    "Complete remaining interviews",
                    "Tag repeated pains, blockers, and buying triggers",
                    "Adjust copy only if the target user is unchanged",
                ],
            },
            {
                "days": "10",
                "focus": "Decision review",
                "activities": [
                    "Compare results against success metrics and failure thresholds",
                    "Decide build, revise, or stop",
                    "Write next MVP milestone from validation findings",
                ],
            },
        ],
        "risks_to_probe": risks,
        "source_ideas": source_ideas,
    }


def render_validation_plan(plan: dict[str, Any], *, fmt: str) -> str:
    """Render a validation plan as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(plan, indent=2) + "\n"
    if fmt == "markdown":
        return render_validation_plan_markdown(plan)
    raise ValueError(f"Unsupported validation plan format: {fmt}")


def render_validation_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a structured validation plan as Markdown."""
    brief = plan["design_brief"]
    lines = [
        f"# Validation Plan: {brief['title']}",
        "",
        f"- **Design brief**: `{brief['id']}`",
        f"- **Domain**: {brief.get('domain') or 'general'}",
        f"- **Theme**: {brief.get('theme') or 'implementation-candidate'}",
        f"- **Readiness**: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        "",
        "## Target User Hypotheses",
        "",
    ]
    for item in plan["target_user_hypotheses"]:
        lines.extend(
            [
                f"### {item['id']}",
                "",
                item["hypothesis"],
                "",
                f"- **Target user**: {item['target_user']}",
                f"- **Buyer**: {item['buyer']}",
                f"- **Workflow**: {item['workflow_context']}",
                f"- **Rationale**: {item['rationale']}",
                "",
            ]
        )

    recruiting = plan["recruiting_criteria"]
    lines.extend(["## Recruiting Criteria", "", f"- **Target sample**: {recruiting['target_sample_size']}"])
    lines.extend(f"- **Ideal participant**: {item}" for item in recruiting["ideal_participants"])
    lines.extend(["", "### Inclusion", ""])
    lines.extend(f"- {item}" for item in recruiting["inclusion_criteria"])
    lines.extend(["", "### Exclusion", ""])
    lines.extend(f"- {item}" for item in recruiting["exclusion_criteria"])
    lines.extend(["", "### Screener Questions", ""])
    lines.extend(f"- {item}" for item in recruiting["screener_questions"])
    lines.extend(["", "## Interview Script", ""])
    script = plan["interview_script"]
    lines.extend([f"Duration: {script['duration_minutes']} minutes", "", script["intro"], ""])
    for section in [
        "warmup_questions",
        "problem_discovery_questions",
        "concept_reaction_questions",
        "smoke_test_questions",
        "closing_questions",
    ]:
        lines.extend([f"### {_titleize(section)}", ""])
        lines.extend(f"- {item}" for item in script[section])
        lines.append("")

    copy = plan["smoke_test_landing_page_copy"]
    lines.extend(
        [
            "## Smoke-Test Landing Page Copy",
            "",
            f"- **Headline**: {copy['headline']}",
            f"- **Subheadline**: {copy['subheadline']}",
            f"- **Primary CTA**: {copy['primary_cta']}",
            f"- **Secondary CTA**: {copy['secondary_cta']}",
            "",
            "### Problem Points",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in copy["problem_points"])
    lines.extend(["", "### Solution Bullets", ""])
    lines.extend(f"- {item}" for item in copy["solution_bullets"])
    lines.extend(["", "## Success Metrics", ""])
    for item in plan["success_metrics"]:
        lines.append(f"- **{item['metric']}**: {item['target']} ({item['rationale']})")
    lines.extend(["", "## Failure Thresholds", ""])
    for item in plan["failure_thresholds"]:
        lines.append(f"- **{item['metric']}**: {item['threshold']} -> {item['action']}")
    lines.extend(["", "## Two-Week Timeline", ""])
    for item in plan["two_week_timeline"]:
        lines.append(f"### Days {item['days']}: {item['focus']}")
        lines.append("")
        lines.extend(f"- {activity}" for activity in item["activities"])
        lines.append("")
    if plan.get("risks_to_probe"):
        lines.extend(["## Risks To Probe", ""])
        lines.extend(f"- {risk}" for risk in plan["risks_to_probe"])
        lines.append("")
    lines.extend(["## Source Ideas", ""])
    for idea in plan["source_ideas"]:
        label = idea.get("title") or "(missing source idea)"
        missing = " missing" if idea.get("missing") else ""
        lines.append(f"- `{idea['id']}` ({idea['role']}{missing}) - {label}")
    lines.append("")
    return "\n".join(lines)


def write_validation_plan(path: Path, plan: dict[str, Any], *, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_validation_plan(plan, fmt=fmt))


def validation_plan_filename(design_brief: dict[str, Any], *, fmt: str) -> str:
    extension = "json" if fmt == "json" else "md"
    return f"{design_brief['id']}-validation-plan.{extension}"


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    sources = list(design_brief.get("sources", []))
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        source_ids = list(design_brief.get("source_idea_ids", []))
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        sources.extend(
            {"idea_id": idea_id, "role": "source", "rank": rank}
            for rank, idea_id in enumerate(source_ids)
            if idea_id != lead_id
        )

    for source in sources:
        idea_id = source["idea_id"]
        role = source["role"]
        key = (idea_id, role)
        if key in seen:
            continue
        seen.add(key)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append(
                {
                    "id": idea_id,
                    "role": role,
                    "rank": source["rank"],
                    "missing": True,
                }
            )
            continue
        ideas.append(
            {
                "id": unit.id,
                "role": role,
                "rank": source["rank"],
                "title": unit.title,
                "one_liner": unit.one_liner,
                "domain": unit.domain,
                "category": unit.category,
                "status": unit.status,
                "problem": unit.problem,
                "solution": unit.solution,
                "target_users": unit.target_users,
                "value_proposition": unit.value_proposition,
                "specific_user": unit.specific_user,
                "buyer": unit.buyer,
                "workflow_context": unit.workflow_context,
                "current_workaround": unit.current_workaround,
                "why_now": unit.why_now,
                "validation_plan": unit.validation_plan,
                "first_10_customers": unit.first_10_customers,
                "domain_risks": unit.domain_risks,
                "tech_approach": unit.tech_approach,
                "quality_score": unit.quality_score,
            }
        )
    return ideas


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _split_candidates(value: Any) -> list[str]:
    text = _first_text(value)
    if not text:
        return []
    separators = ["\n", ";"]
    for separator in separators:
        if separator in text:
            return [item.strip(" -") for item in text.split(separator) if item.strip(" -")]
    return [text]


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        risks.extend(idea.get("domain_risks") or [])
    return risks


def _ideal_participants(target_user: str, buyer: str, first_customers: list[str]) -> list[str]:
    participants = [target_user]
    if buyer != target_user:
        participants.append(buyer)
    participants.extend(first_customers[:3])
    return list(dict.fromkeys(participants))


def _solution_bullets(design_brief: dict[str, Any], lead_idea: dict[str, Any]) -> list[str]:
    bullets = [str(item) for item in design_brief.get("mvp_scope", []) if str(item).strip()]
    if not bullets:
        bullets = [_first_text(lead_idea.get("solution"), design_brief.get("merged_product_concept"))]
    if design_brief.get("first_milestones"):
        bullets.append(f"First milestone: {design_brief['first_milestones'][0]}")
    return [bullet for bullet in bullets if bullet]


def _titleize(value: str) -> str:
    return value.replace("_", " ").title()
