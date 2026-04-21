"""Synthesize reviewed ideas into implementation-ready project briefs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


@dataclass
class Candidate:
    unit: BuildableUnit
    evaluation: UtilityEvaluation | None = None
    feedback: dict | None = None
    readiness_score: float = 0.0
    selection_score: float = 0.0
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


@dataclass
class ProjectBrief:
    title: str
    domain: str
    theme: str
    lead: Candidate
    supporting: list[Candidate] = field(default_factory=list)
    readiness_score: float = 0.0
    why_this_now: str = ""
    mvp_scope: list[str] = field(default_factory=list)
    first_milestones: list[str] = field(default_factory=list)
    validation_plan: str = ""
    risks: list[str] = field(default_factory=list)
    source_idea_ids: list[str] = field(default_factory=list)


def build_candidates(
    units: list[BuildableUnit],
    *,
    evaluations: dict[str, UtilityEvaluation | None],
    feedback: dict[str, dict | None],
    accepted_statuses: set[str] | None = None,
) -> list[Candidate]:
    """Create ranked implementation candidates from reviewed ideas."""
    accepted = accepted_statuses or {"approved", "published"}
    candidates = [
        _score_candidate(unit, evaluations.get(unit.id), feedback.get(unit.id))
        for unit in units
        if unit.status in accepted
    ]
    candidates.sort(key=lambda c: c.selection_score, reverse=True)
    return candidates


def synthesize_project_briefs(
    candidates: list[Candidate],
    *,
    top: int = 8,
    max_supporting: int = 3,
) -> list[ProjectBrief]:
    """Group ranked candidates into a small set of designable project briefs."""
    groups: dict[tuple[str, str], list[Candidate]] = {}
    for candidate in candidates:
        key = (candidate.unit.domain or "general", _theme_key(candidate.unit))
        groups.setdefault(key, []).append(candidate)

    briefs: list[ProjectBrief] = []
    for (domain, theme), members in groups.items():
        members.sort(key=lambda c: c.selection_score, reverse=True)
        lead = members[0]
        supporting = members[1 : max_supporting + 1]
        briefs.append(_build_brief(domain, theme, lead, supporting))

    briefs.sort(key=lambda b: b.readiness_score, reverse=True)
    return briefs[:top]


def render_markdown(briefs: list[ProjectBrief], *, title: str = "Design Candidates") -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# {title}",
        "",
        f"Generated: {generated_at}",
        "",
        "These are synthesized from approved or published ideas and ranked for near-term design/implementation readiness.",
        "",
    ]
    for i, brief in enumerate(briefs, 1):
        lead = brief.lead.unit
        lines.extend(
            [
                f"## {i}. {brief.title}",
                "",
                f"- **Domain**: {brief.domain}",
                f"- **Theme**: {brief.theme}",
                f"- **Readiness**: {brief.readiness_score:.1f}/100",
                f"- **Lead idea**: `{lead.id}` — {lead.title}",
                f"- **Buyer**: {lead.buyer or 'TBD'}",
                f"- **Specific user**: {lead.specific_user or 'TBD'}",
                f"- **Workflow**: {lead.workflow_context or 'TBD'}",
                "",
                "### Why This",
                "",
                brief.why_this_now or lead.why_now or lead.value_proposition,
                "",
                "### MVP Scope",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in brief.mvp_scope)
        lines.extend(["", "### First Milestones", ""])
        lines.extend(f"- {item}" for item in brief.first_milestones)
        lines.extend(["", "### Validation", "", brief.validation_plan or "Define a 2-week validation test.", ""])
        if brief.risks:
            lines.extend(["### Risks", ""])
            lines.extend(f"- {risk}" for risk in brief.risks)
            lines.append("")
        if brief.supporting:
            lines.extend(["### Supporting Ideas", ""])
            for candidate in brief.supporting:
                unit = candidate.unit
                lines.append(f"- `{unit.id}` — {unit.title} ({candidate.readiness_score:.1f}/100)")
            lines.append("")
        lines.extend(["### Source IDs", "", ", ".join(f"`{sid}`" for sid in brief.source_idea_ids), ""])
    return "\n".join(lines)


def render_json(briefs: list[ProjectBrief]) -> str:
    return json.dumps([_brief_to_dict(brief) for brief in briefs], indent=2)


def write_briefs(path: Path, briefs: list[ProjectBrief], *, fmt: str = "markdown") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_json(briefs) if fmt == "json" else render_markdown(briefs)
    path.write_text(content)


def _score_candidate(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    feedback: dict | None,
) -> Candidate:
    strengths: list[str] = []
    gaps: list[str] = []

    eval_score = evaluation.overall_score if evaluation else 0.0
    build_effort = evaluation.build_effort.value if evaluation else 0.0
    composability = evaluation.composability.value if evaluation else 0.0
    pain = evaluation.pain_severity.value if evaluation else 0.0
    timing = evaluation.timing_fit.value if evaluation else 0.0

    readiness = 0.0
    readiness += min(eval_score, 100.0) * 0.30
    readiness += build_effort * 2.0
    readiness += composability * 1.0
    readiness += pain * 1.0
    readiness += timing * 1.0
    readiness += _field_bonus(unit.buyer, 8.0, "clear buyer", "buyer missing", strengths, gaps)
    readiness += _field_bonus(unit.specific_user, 7.0, "specific user", "specific user missing", strengths, gaps)
    readiness += _field_bonus(unit.workflow_context, 8.0, "workflow-owned", "workflow context missing", strengths, gaps)
    readiness += _field_bonus(unit.validation_plan, 8.0, "validation plan", "validation plan missing", strengths, gaps)
    readiness += _field_bonus(unit.first_10_customers, 5.0, "customer path", "first customers unclear", strengths, gaps)
    readiness += _field_bonus(unit.tech_approach, 5.0, "technical approach", "technical approach thin", strengths, gaps)
    readiness += min(max(unit.quality_score, 0.0), 10.0) * 1.5

    approval_score = 0.0
    if feedback and feedback.get("approval_score") is not None:
        approval_score = float(feedback["approval_score"])
    selection = readiness + approval_score * 2.0
    if evaluation and evaluation.recommendation in {"strong_yes", "yes"}:
        selection += 5.0
    if unit.status == "published":
        selection += 4.0

    return Candidate(
        unit=unit,
        evaluation=evaluation,
        feedback=feedback,
        readiness_score=round(min(readiness, 100.0), 2),
        selection_score=round(selection, 2),
        strengths=strengths,
        gaps=gaps,
    )


def _field_bonus(
    value: Any,
    bonus: float,
    strength: str,
    gap: str,
    strengths: list[str],
    gaps: list[str],
) -> float:
    if isinstance(value, str) and value.strip():
        strengths.append(strength)
        return bonus
    if isinstance(value, list) and value:
        strengths.append(strength)
        return bonus
    gaps.append(gap)
    return 0.0


def _theme_key(unit: BuildableUnit) -> str:
    text = " ".join(
        [
            unit.title,
            unit.one_liner,
            unit.problem,
            unit.solution,
            unit.workflow_context,
            unit.category,
        ]
    ).lower()
    themes = [
        ("agent-security-evaluation", ["adversarial", "threat", "security", "probe", "jailbreak", "eval"]),
        ("agent-delivery-ops", ["promote", "ci/cd", "deployment", "runtime", "observability"]),
        ("compliance-traceability", ["compliance", "audit", "hipaa", "traceability", "regulatory"]),
        ("workflow-automation", ["workflow", "intake", "authorization", "reconciliation", "automation"]),
        ("developer-experience", ["developer", "api", "sdk", "cli", "mcp"]),
        ("data-integration", ["integration", "ehr", "data", "sync", "etl"]),
    ]
    for key, needles in themes:
        if any(needle in text for needle in needles):
            return key
    normalized_category = re.sub(r"[^a-z0-9]+", "-", unit.category.lower()).strip("-")
    return normalized_category or "implementation-candidate"


def _build_brief(
    domain: str,
    theme: str,
    lead: Candidate,
    supporting: list[Candidate],
) -> ProjectBrief:
    unit = lead.unit
    source_ids = [unit.id]
    for candidate in supporting:
        source_ids.append(candidate.unit.id)
    for source_id in unit.source_idea_ids:
        if source_id not in source_ids:
            source_ids.append(source_id)

    readiness = lead.readiness_score
    if supporting:
        readiness = round((lead.readiness_score * 0.75) + (sum(c.readiness_score for c in supporting) / len(supporting) * 0.25), 2)

    return ProjectBrief(
        title=unit.title,
        domain=domain,
        theme=theme,
        lead=lead,
        supporting=supporting,
        readiness_score=readiness,
        why_this_now=unit.why_now or unit.evidence_rationale or unit.value_proposition,
        mvp_scope=_mvp_scope(unit),
        first_milestones=_first_milestones(unit),
        validation_plan=unit.validation_plan,
        risks=unit.domain_risks[:4],
        source_idea_ids=source_ids,
    )


def _mvp_scope(unit: BuildableUnit) -> list[str]:
    scope = [
        f"Own one narrow workflow: {unit.workflow_context or unit.problem}",
        f"Serve one buyer/user pair: {unit.buyer or 'TBD buyer'} / {unit.specific_user or 'TBD user'}",
        f"Implement the smallest product loop: {unit.solution[:220]}",
    ]
    if unit.tech_approach:
        scope.append(f"Use this technical spine: {unit.tech_approach[:220]}")
    if unit.current_workaround:
        scope.append(f"Replace the current workaround: {unit.current_workaround[:220]}")
    return scope


def _first_milestones(unit: BuildableUnit) -> list[str]:
    return [
        "Write a one-page product brief with user, buyer, workflow, and non-goals.",
        "Design the workflow states, data inputs, outputs, and failure modes.",
        "Build a clickable or CLI prototype for the core workflow only.",
        "Run the 2-week validation plan with the first target users.",
    ]


def _brief_to_dict(brief: ProjectBrief) -> dict:
    lead = brief.lead.unit
    return {
        "title": brief.title,
        "domain": brief.domain,
        "theme": brief.theme,
        "readiness_score": brief.readiness_score,
        "lead_idea_id": lead.id,
        "lead_idea_title": lead.title,
        "buyer": lead.buyer,
        "specific_user": lead.specific_user,
        "workflow_context": lead.workflow_context,
        "why_this_now": brief.why_this_now,
        "mvp_scope": brief.mvp_scope,
        "first_milestones": brief.first_milestones,
        "validation_plan": brief.validation_plan,
        "risks": brief.risks,
        "supporting_ideas": [
            {
                "id": candidate.unit.id,
                "title": candidate.unit.title,
                "readiness_score": candidate.readiness_score,
            }
            for candidate in brief.supporting
        ],
        "source_idea_ids": brief.source_idea_ids,
    }
