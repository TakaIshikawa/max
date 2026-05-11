"""Generate deterministic accessibility compliance plans for buildable specs."""

from __future__ import annotations

from typing import Any

from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


ACCESSIBILITY_COMPLIANCE_PLAN_SCHEMA_VERSION = "max-accessibility-compliance-plan/v1"
KIND = "max.accessibility_compliance_plan"


def generate_accessibility_compliance_plan(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an idea, evaluation, and optional TactSpec into accessibility guidance."""
    spec = tact_spec or generate_spec_preview(unit, evaluation)
    context = _context(unit, evaluation, spec)
    checks = _compliance_checks(context)
    tests = _assistive_technology_tests(context)
    backlog = _remediation_backlog(context, checks)
    owners = _owner_roles(context)
    checklist = _launch_gate_checklist(context)

    return {
        "schema_version": ACCESSIBILITY_COMPLIANCE_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": unit.category,
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evaluation_available": evaluation is not None,
            "evidence_available": context["evidence_available"],
        },
        "summary": {
            "title": context["title"],
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "recommendation": context["recommendation"],
            "overall_score": context["overall_score"],
            "accessibility_gate": context["accessibility_gate"],
            "highest_severity": _highest_severity(checks),
            "compliance_check_count": len(checks),
            "assistive_technology_test_count": len(tests),
            "remediation_item_count": len(backlog),
        },
        "audit_scope": _audit_scope(context),
        "compliance_checks": checks,
        "assistive_technology_tests": tests,
        "remediation_backlog": backlog,
        "owner_roles": owners,
        "launch_gate_checklist": checklist,
    }


def render_accessibility_compliance_plan_markdown(plan: dict[str, Any]) -> str:
    """Render an accessibility compliance plan as deterministic Markdown."""
    summary = plan.get("summary") or {}
    source = plan.get("source") or {}
    title = _text(summary.get("title")) or _text(plan.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Accessibility Compliance Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Kind: {_text(plan.get('kind'))}",
        f"- Idea ID: {_text(plan.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Category: {_text(source.get('category')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Evaluation available: {_bool_text(source.get('evaluation_available'))}",
        f"- Evidence available: {_bool_text(source.get('evidence_available'))}",
        f"- Accessibility gate: {_text(summary.get('accessibility_gate'))}",
        f"- Highest severity: {_text(summary.get('highest_severity'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        "",
    ]

    _extend_section(lines, "Audit Scope", plan.get("audit_scope") or [], _render_scope)
    _extend_section(lines, "WCAG-Oriented Checks", plan.get("compliance_checks") or [], _render_check)
    _extend_section(
        lines,
        "Assistive Technology Tests",
        plan.get("assistive_technology_tests") or [],
        _render_at_test,
    )
    _extend_section(lines, "Remediation Backlog", plan.get("remediation_backlog") or [], _render_backlog)
    _extend_section(lines, "Owner Roles", plan.get("owner_roles") or [], _render_owner)
    _extend_section(
        lines,
        "Launch Gate Checklist",
        plan.get("launch_gate_checklist") or [],
        _render_gate,
    )

    return "\n".join(lines).rstrip() + "\n"


def _context(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
) -> dict[str, Any]:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    evaluation_payload = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}
    text = _haystack(unit, spec)
    evidence_refs = [
        ref
        for ref in [
            *(_list(evidence.get("insight_ids")) or unit.inspiring_insights),
            *(_list(evidence.get("signal_ids")) or unit.evidence_signals),
            _compact(evidence.get("rationale") or unit.evidence_rationale),
        ]
        if _compact(ref)
    ]
    uses_visual_ui = _contains_any(
        text,
        ("dashboard", "ui", "screen", "form", "table", "report", "workflow", "browser"),
    )
    uses_cli = _contains_any(text, ("cli", "terminal", "command line", "shell"))
    has_automation = _contains_any(text, ("automation", "ci", "pipeline", "job", "integration"))
    recommendation = (
        evaluation.recommendation if evaluation else evaluation_payload.get("recommendation")
    )
    overall_score = evaluation.overall_score if evaluation else evaluation_payload.get("overall_score")
    gate = _accessibility_gate(evaluation, evidence_refs)

    return {
        "title": _compact(project.get("title")) or unit.title,
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or unit.specific_user
        or unit.target_users
        or "primary user",
        "buyer": _compact(project.get("buyer")) or unit.buyer or "launch sponsor",
        "workflow_context": _compact(project.get("workflow_context"))
        or unit.workflow_context
        or "target workflow",
        "solution": _compact(solution.get("approach")) or unit.solution,
        "technical_approach": _compact(solution.get("technical_approach")) or unit.tech_approach,
        "validation_plan": _compact(execution.get("validation_plan"))
        or unit.validation_plan
        or "run representative workflow validation",
        "mvp_scope": [_compact(item) for item in _list(execution.get("mvp_scope")) if _compact(item)]
        or [item for item in [unit.solution, unit.tech_approach, unit.validation_plan] if item],
        "domain_risks": [_compact(risk) for risk in unit.domain_risks if _compact(risk)],
        "recommendation": recommendation,
        "overall_score": overall_score,
        "evaluation_available": evaluation is not None,
        "evidence_references": evidence_refs,
        "evidence_available": bool(evidence_refs),
        "uses_visual_ui": uses_visual_ui,
        "uses_cli": uses_cli,
        "has_automation": has_automation,
        "accessibility_gate": gate,
    }


def _audit_scope(context: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [
        _scope(
            "scope_1",
            "Primary workflow",
            context["workflow_context"],
            "Confirm every required user step can be completed without mouse-only or vision-only assumptions.",
            "idea.workflow_context",
        ),
        _scope(
            "scope_2",
            "MVP interaction surface",
            "; ".join(context["mvp_scope"]) or context["solution"] or "first-release scope",
            "Audit screens, commands, forms, states, errors, and generated outputs in the launch path.",
            "execution.mvp_scope",
        ),
        _scope(
            "scope_3",
            "Validation evidence",
            context["validation_plan"],
            "Attach accessibility evidence to the same validation path used for release approval.",
            "execution.validation_plan",
        ),
    ]
    if context["uses_cli"]:
        entries.append(
            _scope(
                "scope_4",
                "CLI output and terminal ergonomics",
                context["technical_approach"] or "command-line workflow",
                "Verify non-color status output, readable help text, deterministic exit codes, and parseable errors.",
                "solution.technical_approach",
            )
        )
    return entries


def _compliance_checks(context: dict[str, Any]) -> list[dict[str, Any]]:
    severity = _base_severity(context)
    checks = [
        _check(
            "A11Y-C1",
            "WCAG 2.2 1.1.1 Non-text Content",
            "Perceivable",
            "Text alternatives exist for icons, charts, media, generated reports, and status indicators.",
            severity,
            "manual_review",
            "accessibility_owner",
            context["evidence_available"],
        ),
        _check(
            "A11Y-C2",
            "WCAG 2.2 1.3.1 Info and Relationships",
            "Perceivable",
            "Headings, labels, tables, regions, form relationships, and output structure preserve semantic meaning.",
            severity,
            "semantic_inspection",
            "frontend_owner",
            context["evidence_available"],
        ),
        _check(
            "A11Y-C3",
            "WCAG 2.2 1.4.3 Contrast",
            "Perceivable",
            "Text, controls, charts, and focus indicators meet contrast expectations in default and error states.",
            "high" if context["uses_visual_ui"] else "medium",
            "automated_and_manual",
            "design_owner",
            context["evidence_available"],
        ),
        _check(
            "A11Y-C4",
            "WCAG 2.2 2.1.1 Keyboard",
            "Operable",
            "All required actions can be reached, triggered, dismissed, and repeated with keyboard-only input.",
            "critical" if context["uses_visual_ui"] else severity,
            "keyboard_walkthrough",
            "qa_owner",
            context["evidence_available"],
        ),
        _check(
            "A11Y-C5",
            "WCAG 2.2 2.4.3 Focus Order",
            "Operable",
            "Focus order follows the visual and workflow sequence, with visible focus on every interactive element.",
            "high" if context["uses_visual_ui"] else "medium",
            "keyboard_walkthrough",
            "frontend_owner",
            context["evidence_available"],
        ),
        _check(
            "A11Y-C6",
            "WCAG 2.2 3.3.1 Error Identification",
            "Understandable",
            "Validation errors, blocked states, and failed automation outcomes identify the problem and next step.",
            severity,
            "error_state_review",
            "product_owner",
            context["evidence_available"],
        ),
        _check(
            "A11Y-C7",
            "WCAG 2.2 4.1.2 Name, Role, Value",
            "Robust",
            "Controls expose stable names, roles, states, and values to assistive technology and automation.",
            "critical" if context["uses_visual_ui"] else "high",
            "screen_reader_probe",
            "frontend_owner",
            context["evidence_available"],
        ),
    ]
    if not context["evaluation_available"]:
        checks.append(
            _check(
                "A11Y-C8",
                "Evaluation-backed accessibility risk",
                "Governance",
                "No utility evaluation is attached; launch approval must explicitly accept unresolved accessibility risk.",
                "high",
                "launch_review",
                "product_owner",
                False,
            )
        )
    return checks


def _assistive_technology_tests(context: dict[str, Any]) -> list[dict[str, Any]]:
    tests = [
        _at_test(
            "AT-1",
            "Keyboard-only workflow",
            "Keyboard",
            context["workflow_context"],
            "Complete the primary workflow without pointer input, with no traps and visible focus throughout.",
            "qa_owner",
            True,
        ),
        _at_test(
            "AT-2",
            "Screen reader happy path",
            "NVDA or VoiceOver",
            context["workflow_context"],
            "Confirm page, region, control, error, and completion announcements are meaningful and ordered.",
            "accessibility_owner",
            context["uses_visual_ui"],
        ),
        _at_test(
            "AT-3",
            "Zoom and reflow",
            "Browser zoom to 200%",
            context["workflow_context"],
            "Verify no required content or controls overlap, truncate critical labels, or require two-axis scrolling.",
            "design_owner",
            context["uses_visual_ui"],
        ),
        _at_test(
            "AT-4",
            "Reduced motion and status changes",
            "OS accessibility settings",
            context["validation_plan"],
            "Confirm animation, progress, errors, and generated results remain understandable without motion cues.",
            "frontend_owner",
            context["uses_visual_ui"] or context["has_automation"],
        ),
    ]
    if context["uses_cli"]:
        tests.append(
            _at_test(
                "AT-5",
                "Terminal screen reader and text output",
                "Screen reader with terminal",
                context["technical_approach"] or "CLI workflow",
                "Confirm command help, progress, errors, and summaries are readable as plain text without color dependence.",
                "technical_owner",
                True,
            )
        )
    return tests


def _remediation_backlog(
    context: dict[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    backlog = [
        _backlog(
            "A11Y-R1",
            "Attach accessibility acceptance criteria to release scope",
            "Define pass/fail expectations for the primary workflow before launch approval.",
            "product_owner",
            "P0" if context["accessibility_gate"] == "blocked" else "P1",
            ["A11Y-C4", "A11Y-C7"],
        ),
        _backlog(
            "A11Y-R2",
            "Capture assistive technology evidence",
            "Record keyboard, screen reader, zoom, and error-state test results with links to release evidence.",
            "qa_owner",
            "P0" if not context["evidence_available"] else "P1",
            [check["id"] for check in checks if not check["evidence_available"]],
        ),
        _backlog(
            "A11Y-R3",
            "Fix critical keyboard and semantic blockers",
            "Resolve any blocker that prevents target users from completing the documented workflow.",
            "frontend_owner",
            "P0",
            ["A11Y-C2", "A11Y-C4", "A11Y-C7"],
        ),
        _backlog(
            "A11Y-R4",
            "Document known accessibility limitations",
            "Publish launch notes for accepted limitations, workarounds, owners, and follow-up dates.",
            "accessibility_owner",
            "P1",
            ["A11Y-C1", "A11Y-C3", "A11Y-C6"],
        ),
    ]
    if not context["evaluation_available"]:
        backlog.append(
            _backlog(
                "A11Y-R5",
                "Complete utility evaluation before widening launch",
                "Add evaluation findings or a signed waiver before broad user exposure.",
                "product_owner",
                "P0",
                ["A11Y-C8"],
            )
        )
    return backlog


def _owner_roles(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _owner("product_owner", context["buyer"], "Owns launch gate decision, accepted risk, and remediation priority."),
        _owner("accessibility_owner", "accessibility reviewer", "Owns WCAG interpretation, evidence quality, and exception review."),
        _owner("design_owner", "design owner", "Owns contrast, visible focus, information hierarchy, and non-text alternatives."),
        _owner("frontend_owner", "engineering owner", "Owns semantic implementation, keyboard behavior, and assistive technology defects."),
        _owner("qa_owner", context["target_user"], "Owns repeatable assistive technology coverage and release evidence capture."),
    ]


def _launch_gate_checklist(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _gate("A11Y-G1", "Audit scope covers the primary workflow and MVP interaction surface.", "product_owner", True, True),
        _gate("A11Y-G2", "Keyboard-only test passes for all required launch actions.", "qa_owner", True, context["evidence_available"]),
        _gate("A11Y-G3", "Screen reader checks cover names, roles, values, errors, and completion states.", "accessibility_owner", True, context["evidence_available"]),
        _gate("A11Y-G4", "Contrast, focus, zoom, and reflow issues have no open critical defects.", "design_owner", True, context["evidence_available"]),
        _gate("A11Y-G5", "Known limitations and remediation owners are documented for launch notes.", "product_owner", True, True),
        _gate("A11Y-G6", "Utility evaluation is present or explicitly waived.", "product_owner", True, context["evaluation_available"]),
    ]


def _accessibility_gate(evaluation: UtilityEvaluation | None, evidence_refs: list[str]) -> str:
    if evaluation is None:
        return "blocked"
    if evaluation.recommendation in {"no", "strong_no"}:
        return "blocked"
    if not evidence_refs:
        return "needs_evidence"
    if evaluation.overall_score is not None and evaluation.overall_score < 60:
        return "needs_review"
    return "ready_with_checks"


def _base_severity(context: dict[str, Any]) -> str:
    if context["accessibility_gate"] == "blocked":
        return "high"
    if context["accessibility_gate"] == "needs_evidence":
        return "high"
    return "medium"


def _highest_severity(checks: list[dict[str, Any]]) -> str:
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return min((check["severity"] for check in checks), key=lambda value: rank.get(value, 99))


def _scope(
    scope_id: str,
    name: str,
    surface: str,
    audit_goal: str,
    evidence_source: str,
) -> dict[str, Any]:
    return {
        "id": scope_id,
        "name": name,
        "surface": surface,
        "audit_goal": audit_goal,
        "evidence_source": evidence_source,
    }


def _check(
    check_id: str,
    wcag_reference: str,
    principle: str,
    requirement: str,
    severity: str,
    method: str,
    owner: str,
    evidence_available: bool,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "wcag_reference": wcag_reference,
        "principle": principle,
        "requirement": requirement,
        "severity": severity,
        "method": method,
        "owner": owner,
        "evidence_available": evidence_available,
        "status": "pending",
    }


def _at_test(
    test_id: str,
    name: str,
    assistive_technology: str,
    coverage_target: str,
    expected_result: str,
    owner: str,
    required: bool,
) -> dict[str, Any]:
    return {
        "id": test_id,
        "name": name,
        "assistive_technology": assistive_technology,
        "coverage_target": coverage_target,
        "expected_result": expected_result,
        "owner": owner,
        "required": required,
        "status": "pending",
    }


def _backlog(
    item_id: str,
    title: str,
    remediation: str,
    owner: str,
    priority: str,
    related_checks: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "remediation": remediation,
        "owner": owner,
        "priority": priority,
        "related_checks": related_checks,
        "status": "open",
    }


def _owner(role: str, assigned_to: str, responsibility: str) -> dict[str, Any]:
    return {
        "role": role,
        "assigned_to": assigned_to,
        "responsibility": responsibility,
    }


def _gate(
    gate_id: str,
    task: str,
    owner: str,
    required: bool,
    evidence_required_before_launch: bool,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "task": task,
        "owner": owner,
        "required": required,
        "evidence_required_before_launch": evidence_required_before_launch,
        "status": "pending",
    }


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer,
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend([f"No {title.lower()} were listed.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
    lines.append("")


def _render_scope(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Surface: {_text(item.get('surface'))}",
        f"- Audit goal: {_text(item.get('audit_goal'))}",
        f"- Evidence source: {_text(item.get('evidence_source'))}",
        "",
    ]


def _render_check(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('wcag_reference'))}",
        "",
        f"- Principle: {_text(item.get('principle'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Method: {_text(item.get('method'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Evidence available: {_bool_text(item.get('evidence_available'))}",
        f"- Requirement: {_text(item.get('requirement'))}",
        "",
    ]


def _render_at_test(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Assistive technology: {_text(item.get('assistive_technology'))}",
        f"- Coverage target: {_text(item.get('coverage_target'))}",
        f"- Required: {_bool_text(item.get('required'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Expected result: {_text(item.get('expected_result'))}",
        "",
    ]


def _render_backlog(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        "",
        f"- Priority: {_text(item.get('priority'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Related checks: {_join(item.get('related_checks'))}",
        f"- Remediation: {_text(item.get('remediation'))}",
        "",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"- {_text(item.get('role'))}: {_text(item.get('assigned_to'))} - {_text(item.get('responsibility'))}"
    ]


def _render_gate(item: dict[str, Any]) -> list[str]:
    return [
        f"- [{_text(item.get('status'))}] {_text(item.get('id'))} "
        f"({_text(item.get('owner'))}; required={_bool_text(item.get('required'))}; "
        f"evidence_before_launch={_bool_text(item.get('evidence_required_before_launch'))}): "
        f"{_text(item.get('task'))}"
    ]


def _haystack(unit: BuildableUnit, spec: dict[str, Any]) -> str:
    values = [
        unit.title,
        unit.one_liner,
        unit.problem,
        unit.solution,
        unit.target_users,
        unit.specific_user,
        unit.buyer,
        unit.workflow_context,
        unit.current_workaround,
        unit.validation_plan,
        unit.tech_approach,
        unit.composability_notes,
        *unit.domain_risks,
        spec,
    ]
    return " ".join(_text(value).lower() for value in values if _text(value))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _join(value: Any) -> str:
    items = [_text(item) for item in _list(value) if _text(item)]
    return "; ".join(items) if items else "none"


def _compact(value: Any) -> str:
    return _text(value)


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()
