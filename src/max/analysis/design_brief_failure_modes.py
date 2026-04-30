"""Deterministic FMEA-style failure mode reports for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.failure_modes"
SCHEMA_VERSION = "max.design_brief.failure_modes.v1"

_CRITICAL_TERMS = (
    "compliance",
    "credential",
    "legal",
    "pii",
    "privacy",
    "regulated",
    "security",
)
_TECHNICAL_TERMS = (
    "api",
    "data",
    "integration",
    "latency",
    "migration",
    "sync",
    "technical",
)
_ADOPTION_TERMS = (
    "adoption",
    "buyer",
    "market",
    "onboarding",
    "pricing",
    "workflow",
)


def build_design_brief_failure_modes(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a lightweight FMEA-style report from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _failure_mode_context(design_brief, source_ideas, lead_idea)
    evidence = _evidence_references(design_brief, source_ideas)
    assumptions = _known_assumptions(design_brief, context, source_idea_ids, evidence)
    failure_modes = _failure_modes(
        design_brief,
        source_ideas,
        context,
        assumptions,
        evidence,
        source_idea_ids,
    )

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
            "failure_mode_count": len(failure_modes),
            "top_risk_priority_number": failure_modes[0]["risk_priority_number"]
            if failure_modes
            else 0,
            "critical_failure_mode_count": sum(
                1 for mode in failure_modes if mode["severity_label"] == "critical"
            ),
            "assumption_count": len(assumptions),
            "evidence_reference_count": len(evidence),
            "fallbacks_used": context["fallbacks_used"],
        },
        "failure_context": context,
        "known_assumptions": assumptions,
        "failure_modes": failure_modes,
        "evidence_references": evidence,
        "source_ideas": source_ideas,
    }


def render_design_brief_failure_modes(report: dict[str, Any], fmt: str = "json") -> str:
    """Render failure modes as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported failure modes format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    modes = sorted(
        report["failure_modes"],
        key=lambda mode: (-mode["risk_priority_number"], -mode["severity"], mode["id"]),
    )
    lines = [
        f"# Failure Modes: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Summary",
        "",
        f"- Failure modes: {summary['failure_mode_count']}",
        f"- Top RPN: {summary['top_risk_priority_number']}",
        f"- Critical modes: {summary['critical_failure_mode_count']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Prioritized Failure Modes",
        "",
    ]

    for mode in modes:
        lines.extend(
            [
                f"### {mode['rank']}. {mode['title']} (RPN {mode['risk_priority_number']})",
                "",
                f"- Failure mode: {mode['failure_mode']}",
                f"- Cause: {mode['cause']}",
                f"- Effect: {mode['effect']}",
                f"- Scores: severity {mode['severity']}, likelihood {mode['likelihood']}, detectability {mode['detectability']}",
                f"- Detection method: {mode['detection_method']}",
                f"- Mitigation: {mode['mitigation']}",
                f"- Owner role: {mode['owner_role']}",
                f"- Source references: {_reference_text(mode['source_references'])}",
                "",
            ]
        )

    lines.extend(["## Known Assumptions", ""])
    if report["known_assumptions"]:
        for assumption in report["known_assumptions"]:
            lines.append(
                f"- **{assumption['id']}** ({assumption['field']}): {assumption['assumption']}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for item in report["evidence_references"]:
            lines.append(f"- **{item['id']}** ({item['type']}): {item['summary']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def failure_modes_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a failure modes export."""
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    title = _filename_part(str(design_brief.get("title") or "failure-modes"))
    return f"{brief_id}-{title}-failure-modes.{extension}"


def _failure_modes(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    context: dict[str, Any],
    assumptions: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    modes: list[dict[str, Any]] = []
    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )

    for risk in risks[:5]:
        _add_failure_mode(
            modes,
            title=f"Risk materializes: {_short_title(risk)}",
            failure_mode=risk,
            cause=_cause_for_risk(risk, context),
            effect=_effect_for_risk(risk, context),
            detection_method=_detection_for_risk(risk, context),
            mitigation=_mitigation_for_risk(risk, context),
            owner_role=_owner_for_risk(risk),
            source_references=_source_references(
                "risk", ["risks", "domain_risks"], _source_ids_for_text(risk, source_ideas, source_idea_ids)
            ),
            severity=_severity_score(risk, design_brief),
            likelihood=_likelihood_score(risk, design_brief),
            detectability=_detectability_score(risk, evidence, design_brief),
        )

    for assumption in assumptions[:4]:
        field = assumption["field"]
        _add_failure_mode(
            modes,
            title=f"Assumption invalid: {field}",
            failure_mode=assumption["assumption"],
            cause=f"The design brief does not yet prove `{field}` for {context['title']}.",
            effect=assumption["failure_effect"],
            detection_method=assumption["validation_action"],
            mitigation=assumption["mitigation"],
            owner_role=assumption["owner_role"],
            source_references=_source_references("assumption", [field], assumption["source_idea_ids"]),
            severity=assumption["severity"],
            likelihood=assumption["likelihood"],
            detectability=assumption["detectability"],
        )

    for scope in _string_list(design_brief.get("mvp_scope"))[:3]:
        _add_failure_mode(
            modes,
            title=f"MVP scope misses workflow value: {_short_title(scope)}",
            failure_mode=f"{context['target_user']} cannot get useful workflow value from `{scope}`.",
            cause=f"The MVP slice may be implementation-readable but not complete enough for {context['workflow_context']}.",
            effect=f"Pilot users abandon {context['product_concept']} or continue using the incumbent workaround.",
            detection_method=(
                f"Run a task-completion test for `{scope}` with target users and require observed completion plus value articulation."
            ),
            mitigation=(
                "Split or revise the MVP scope until one pilot task has a clear start, completion signal, support path, and acceptance threshold."
            ),
            owner_role="Product owner",
            source_references=_source_references(
                "scope", ["mvp_scope"], _source_ids_for_text(scope, source_ideas, source_idea_ids)
            ),
            severity=7,
            likelihood=5,
            detectability=4 if evidence else 6,
        )

    if len(modes) < 4:
        _add_failure_mode(
            modes,
            title="Validation evidence is too thin for implementation handoff",
            failure_mode="The project advances to implementation without enough user, buyer, risk, or workflow proof.",
            cause="The persisted design brief has sparse evidence references or missing validation details.",
            effect="Implementation agents may build the wrong workflow or miss stop conditions until launch.",
            detection_method="Run an evidence audit and require every critical assumption to have a validation owner and pass/fail threshold.",
            mitigation="Gate implementation tasks behind the top three validation actions and record a build, revise, or stop decision.",
            owner_role="Product owner",
            source_references=_source_references(
                "evidence_gap", ["evidence_references", "validation_plan"], source_idea_ids
            ),
            severity=8,
            likelihood=7 if not evidence else 5,
            detectability=7 if not evidence else 5,
        )

    ranked = sorted(
        modes,
        key=lambda mode: (-mode["risk_priority_number"], -mode["severity"], mode["id"]),
    )
    for rank, mode in enumerate(ranked, start=1):
        mode["rank"] = rank
    return ranked


def _add_failure_mode(
    modes: list[dict[str, Any]],
    *,
    title: str,
    failure_mode: str,
    cause: str,
    effect: str,
    detection_method: str,
    mitigation: str,
    owner_role: str,
    source_references: list[dict[str, Any]],
    severity: int,
    likelihood: int,
    detectability: int,
) -> None:
    severity = _bounded_score(severity)
    likelihood = _bounded_score(likelihood)
    detectability = _bounded_score(detectability)
    modes.append(
        {
            "id": f"FM{len(modes) + 1}",
            "rank": 0,
            "title": title,
            "failure_mode": failure_mode,
            "cause": cause,
            "effect": effect,
            "detection_method": detection_method,
            "mitigation": mitigation,
            "severity": severity,
            "severity_label": _severity_label(severity),
            "likelihood": likelihood,
            "detectability": detectability,
            "risk_priority_number": severity * likelihood * detectability,
            "owner_role": owner_role,
            "source_references": source_references,
        }
    )


def _failure_mode_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = _first_text(design_brief.get("title"), "Untitled design brief")
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
        ("economic buyer", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    workaround = _first_text(
        design_brief.get("current_workaround"),
        lead_idea and lead_idea.get("current_workaround"),
        _field_values(source_ideas, "current_workaround"),
        "current manual or incumbent workflow",
    )
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "current_workaround": workaround,
        "product_concept": _first_text(
            design_brief.get("merged_product_concept"),
            lead_idea and lead_idea.get("solution"),
            f"{title} product concept",
        ),
        "validation_plan": _first_text(
            design_brief.get("validation_plan"),
            lead_idea and lead_idea.get("validation_plan"),
            "Run the smallest validation that can produce a written proceed, revise, or stop decision.",
        ),
        "fallbacks_used": fallbacks,
    }


def _known_assumptions(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assumptions: list[dict[str, Any]] = []
    checks = [
        (
            "specific_user",
            f"{context['target_user']} is reachable and represents the primary workflow user.",
            f"Validation recruits may not match the real user, so usability and adoption signals mislead implementation.",
            "Interview 5 qualified users and require each to describe the current workflow and trigger.",
            "Tighten the target persona and exclude implementation work that cannot name a qualifying user segment.",
            "Product owner",
            8,
        ),
        (
            "buyer",
            f"{context['buyer']} can approve pilot access, budget, or workflow change.",
            "The team may validate with users but fail at launch because no buyer owns the decision.",
            "Run a buyer review with explicit proceed, revise, or stop criteria before launch planning.",
            "Assign a buyer or workflow approver and make launch tasks conditional on written approval.",
            "Product owner",
            7,
        ),
        (
            "workflow_context",
            f"{context['workflow_context']} is the workflow where the product must create value.",
            "The MVP may optimize the wrong workflow step and miss required handoffs or exceptions.",
            "Map the current workflow with users and confirm the MVP entry and completion points.",
            "Revise scope until the workflow owner can identify the start state, end state, and exception path.",
            "Workflow owner",
            8,
        ),
        (
            "validation_plan",
            f"The validation plan can catch launch-blocking failures before implementation handoff: {context['validation_plan']}",
            "Known risks may remain invisible until a pilot or production launch.",
            "Create a pass/fail validation rubric tied to the highest-RPN failure modes.",
            "Block launch tasks until the rubric has owners, sample size, thresholds, and stop conditions.",
            "Product owner",
            8,
        ),
    ]
    for field, assumption, effect, validation, mitigation, owner, severity in checks:
        missing = not _string_list(design_brief.get(field)) or field in context["fallbacks_used"]
        weak = field == "validation_plan" and not evidence
        if missing or weak:
            assumptions.append(
                {
                    "id": f"A{len(assumptions) + 1}",
                    "field": field,
                    "assumption": assumption,
                    "failure_effect": effect,
                    "validation_action": validation,
                    "mitigation": mitigation,
                    "owner_role": owner,
                    "severity": severity,
                    "likelihood": 7 if missing else 5,
                    "detectability": 7 if missing else 5,
                    "source_idea_ids": source_idea_ids,
                }
            )
    if not _string_list(design_brief.get("mvp_scope")):
        assumptions.append(
            {
                "id": f"A{len(assumptions) + 1}",
                "field": "mvp_scope",
                "assumption": "A smallest valuable MVP scope can be inferred from the design brief.",
                "failure_effect": "Implementation tasks may be too broad, too vague, or disconnected from first value.",
                "validation_action": "Define one task-level MVP slice and run a prototype or concierge completion test.",
                "mitigation": "Create an MVP scope checkpoint before writing implementation tasks.",
                "owner_role": "Product owner",
                "severity": 7,
                "likelihood": 7,
                "detectability": 6,
                "source_idea_ids": source_idea_ids,
            }
        )
    return assumptions


def _severity_score(risk: str, design_brief: dict[str, Any]) -> int:
    lowered = risk.lower()
    if any(term in lowered for term in _CRITICAL_TERMS):
        return 10
    if any(term in lowered for term in _TECHNICAL_TERMS):
        return 8
    if any(term in lowered for term in _ADOPTION_TERMS):
        return 7
    readiness = float(design_brief.get("readiness_score") or 0.0)
    return 7 if readiness < 50 else 6


def _likelihood_score(risk: str, design_brief: dict[str, Any]) -> int:
    lowered = risk.lower()
    score = 5
    if any(term in lowered for term in (*_CRITICAL_TERMS, *_TECHNICAL_TERMS, *_ADOPTION_TERMS)):
        score += 1
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if readiness < 50:
        score += 2
    elif readiness < 75:
        score += 1
    return score


def _detectability_score(
    risk: str, evidence: list[dict[str, Any]], design_brief: dict[str, Any]
) -> int:
    lowered = risk.lower()
    score = 5
    if not evidence:
        score += 2
    if not _first_text(design_brief.get("validation_plan")):
        score += 1
    if any(term in lowered for term in ("privacy", "security", "compliance", "legal")):
        score -= 1
    return score


def _cause_for_risk(risk: str, context: dict[str, Any]) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _CRITICAL_TERMS):
        return f"Sensitive policy, access, or review requirements are unresolved for {context['product_concept']}."
    if any(term in lowered for term in _TECHNICAL_TERMS):
        return f"Technical contracts, data shape, or integration ownership may be incomplete for {context['workflow_context']}."
    if any(term in lowered for term in _ADOPTION_TERMS):
        return f"The target workflow, buyer path, or launch behavior may not be proven for {context['target_user']}."
    return "The design brief names a material risk that needs an explicit owner and validation threshold."


def _effect_for_risk(risk: str, context: dict[str, Any]) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _CRITICAL_TERMS):
        return "Launch is blocked, rework is required, or sensitive data is exposed without approval."
    if any(term in lowered for term in _TECHNICAL_TERMS):
        return f"{context['target_user']} cannot complete {context['workflow_context']} reliably during pilot or launch."
    if any(term in lowered for term in _ADOPTION_TERMS):
        return f"{context['buyer']} does not approve rollout or users continue using {context['current_workaround']}."
    return "Implementation work proceeds with hidden uncertainty and may need late redesign."


def _detection_for_risk(risk: str, context: dict[str, Any]) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _CRITICAL_TERMS):
        return "Run expert review before pilot activation and require written approval plus a launch-blocker list."
    if any(term in lowered for term in _TECHNICAL_TERMS):
        return "Run a technical spike with staging data, contract checks, reconciliation, and rollback rehearsal."
    if any(term in lowered for term in _ADOPTION_TERMS):
        return f"Run buyer and user validation for {context['workflow_context']} with explicit acceptance and rejection thresholds."
    return "Assign a risk owner and review the risk in the validation plan before implementation task generation."


def _mitigation_for_risk(risk: str, context: dict[str, Any]) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _CRITICAL_TERMS):
        return "Add a launch gate for risk owner approval, remove sensitive data from the MVP path, and keep a rollback plan ready."
    if any(term in lowered for term in _TECHNICAL_TERMS):
        return "Constrain the first release to one verified integration path with telemetry, reconciliation, and rollback ownership."
    if any(term in lowered for term in _ADOPTION_TERMS):
        return f"Pilot with qualified {context['target_user']} users and make rollout conditional on buyer sign-off and usage evidence."
    return "Document owner, mitigation task, detection method, and stop threshold before launch planning."


def _owner_for_risk(risk: str) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in _CRITICAL_TERMS):
        return "Risk reviewer"
    if any(term in lowered for term in _TECHNICAL_TERMS):
        return "Engineering owner"
    if any(term in lowered for term in _ADOPTION_TERMS):
        return "Product owner"
    return "Product owner"


def _source_references(
    reference_type: str, fields: list[str], source_idea_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "type": reference_type,
            "fields": fields,
            "source_idea_ids": list(dict.fromkeys(source_idea_ids)),
        }
    ]


def _evidence_references(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field in ("why_this_now", "synthesis_rationale", "validation_plan"):
        text = _first_text(design_brief.get(field))
        if text:
            refs.append(
                {
                    "id": f"design_brief.{field}",
                    "type": "brief_field",
                    "summary": text,
                    "source_idea_ids": list(design_brief.get("source_idea_ids") or []),
                }
            )
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            refs.append(
                {
                    "id": signal_id,
                    "type": "evidence_signal",
                    "summary": _first_text(idea.get("one_liner"), idea.get("problem"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "inspiring_insight",
                    "summary": _first_text(idea.get("value_proposition"), idea.get("solution"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
    return _dedupe_refs(refs)


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


def _source_ids_for_text(
    text: str, source_ideas: list[dict[str, Any]], fallback: list[str]
) -> list[str]:
    tokens = {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 3}
    matches: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        haystack = " ".join(
            str(idea.get(field) or "")
            for field in (
                "title",
                "one_liner",
                "problem",
                "solution",
                "tech_approach",
                "value_proposition",
                "workflow_context",
                "domain_risks",
            )
        ).lower()
        if tokens and tokens & set(re.findall(r"[a-z0-9]+", haystack)):
            matches.append(idea["id"])
    return matches or fallback


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _first_with_label(fallbacks: list[str], field: str, *candidates: tuple[Any, str]) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list | tuple | set):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        deduped.setdefault(ref["id"], ref)
    return list(deduped.values())


def _reference_text(references: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for ref in references:
        fields = ", ".join(ref.get("fields") or [])
        source_ids = ", ".join(ref.get("source_idea_ids") or [])
        if fields and source_ids:
            parts.append(f"{fields} ({source_ids})")
        elif fields:
            parts.append(fields)
        elif source_ids:
            parts.append(source_ids)
    return "; ".join(parts) or "design brief"


def _severity_label(severity: int) -> str:
    if severity >= 9:
        return "critical"
    if severity >= 7:
        return "high"
    if severity >= 4:
        return "medium"
    return "low"


def _bounded_score(value: int) -> int:
    return max(1, min(10, int(value)))


def _short_title(text: str) -> str:
    stripped = _compact(text).rstrip(".")
    if len(stripped) <= 72:
        return stripped
    return stripped[:69].rstrip() + "..."


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
