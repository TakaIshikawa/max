"""Deterministic QA test plans for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.qa_test_plan"
SCHEMA_VERSION = "max.design_brief.qa_test_plan.v1"

TEST_SUITE_TYPES: tuple[str, ...] = (
    "unit",
    "integration",
    "acceptance",
    "regression",
)

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "area",
    "scenario_name",
    "priority",
    "test_type",
    "preconditions",
    "steps",
    "expected_result",
    "owner",
    "evidence_source_references",
)


def build_design_brief_qa_test_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build executable QA guidance from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _qa_context(design_brief, source_ideas)
    evidence_refs = _evidence_references(design_brief, source_ideas)
    evidence_gaps = _evidence_gaps(design_brief, source_ideas, context, evidence_refs, source_idea_ids)
    test_suites = _test_suites(context, evidence_gaps, source_idea_ids)
    critical_paths = _critical_paths(context, source_idea_ids)
    test_data_needs = _test_data_needs(context, source_idea_ids)
    automation_candidates = _automation_candidates(context, test_suites, source_idea_ids)
    manual_review_checks = _manual_review_checks(context, evidence_gaps, source_idea_ids)

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
            "suite_count": len(test_suites),
            "critical_path_count": len(critical_paths),
            "test_data_need_count": len(test_data_needs),
            "automation_candidate_count": len(automation_candidates),
            "manual_review_check_count": len(manual_review_checks),
            "evidence_gap_count": len(evidence_gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "source_metadata": {
            "source_idea_count": len(source_idea_ids),
            "evidence_reference_count": len(evidence_refs),
            "missing_source_idea_ids": [
                idea["id"] for idea in source_ideas if idea.get("missing")
            ],
        },
        "qa_context": context,
        "test_suites": test_suites,
        "critical_paths": critical_paths,
        "test_data_needs": test_data_needs,
        "automation_candidates": automation_candidates,
        "manual_review_checks": manual_review_checks,
        "evidence_references": evidence_refs,
        "evidence_gaps": evidence_gaps,
        "source_ideas": source_ideas,
    }


def render_design_brief_qa_test_plan(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a QA test plan as Markdown, CSV, or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_qa_test_plan_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported QA test plan format: {fmt}")

    return render_qa_test_plan_markdown(report)


def render_qa_test_plan_markdown(report: dict[str, Any]) -> str:
    """Render a QA test plan as deterministic Markdown for handoff review."""
    brief = report.get("design_brief") or {}
    summary = report.get("summary") or {}
    context = report.get("qa_context") or {}
    test_suites = report.get("test_suites") or []
    critical_paths = report.get("critical_paths") or []
    test_data_needs = report.get("test_data_needs") or []
    automation_candidates = report.get("automation_candidates") or []
    manual_review_checks = report.get("manual_review_checks") or []
    evidence_refs = report.get("evidence_references") or []
    evidence_gaps = report.get("evidence_gaps") or []
    source_idea_ids = _string_list(brief.get("source_idea_ids"))

    lines = [
        f"# QA Test Plan: {brief.get('title') or context.get('title') or 'Untitled design brief'}",
        "",
        f"Schema: `{report.get('schema_version') or SCHEMA_VERSION}`",
        f"Design brief: `{brief.get('id') or 'unknown'}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {_inline_list(source_idea_ids)}",
        f"Evidence gaps: {summary.get('evidence_gap_count', len(evidence_gaps))}",
        "",
        "## Scope",
        "",
        f"- Product concept: {context.get('product_concept') or 'not specified'}",
        f"- Primary user: {context.get('target_user') or 'not specified'}",
        f"- Buyer: {context.get('buyer') or 'not specified'}",
        f"- Workflow: {context.get('workflow_context') or 'not specified'}",
        f"- Primary scope: {context.get('primary_scope') or 'not specified'}",
        f"- Secondary scope: {context.get('secondary_scope') or 'not specified'}",
        f"- Validation plan: {context.get('validation_plan') or 'not specified'}",
        "",
        "## QA Summary",
        "",
        f"- Suite count: {summary.get('suite_count', len(test_suites))}",
        f"- Critical path count: {summary.get('critical_path_count', len(critical_paths))}",
        f"- Test data need count: {summary.get('test_data_need_count', len(test_data_needs))}",
        f"- Automation candidate count: {summary.get('automation_candidate_count', len(automation_candidates))}",
        f"- Manual review check count: {summary.get('manual_review_check_count', len(manual_review_checks))}",
        f"- Fallbacks used: {_inline_list(_string_list(summary.get('fallbacks_used')))}",
        "",
        "## Test Scenarios",
        "",
    ]

    if test_suites:
        for suite in test_suites:
            _extend_suite_markdown(lines, suite, include_priority=True)
    else:
        lines.extend(["- None", ""])

    lines.extend(["## Risks", ""])
    risks = _string_list(context.get("risks"))
    if risks:
        lines.extend(f"- {risk}" for risk in risks)
    else:
        lines.append("- None")
    if evidence_gaps:
        lines.extend(["", "### Evidence Gaps", ""])
        for gap in evidence_gaps:
            _extend_gap_markdown(lines, gap)

    lines.extend(["", "## Environments", ""])
    environments = report.get("environments") or _default_environments(test_data_needs, source_idea_ids)
    if environments:
        for environment in environments:
            lines.extend(
                [
                    f"- **{environment.get('id') or environment.get('name') or 'ENV'} {environment.get('name') or 'Test environment'}**",
                    f"  Purpose: {environment.get('purpose') or environment.get('description') or 'not specified'}",
                    f"  Data: {environment.get('data') or environment.get('test_data') or 'not specified'}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Acceptance Evidence", ""])
    if evidence_refs:
        lines.append("- Evidence references:")
        for ref in evidence_refs:
            lines.append(
                f"  - {ref.get('id') or 'reference'} ({ref.get('type') or 'evidence'}): {ref.get('summary') or 'not specified'}"
            )
    else:
        lines.append("- Evidence references: none")
    if manual_review_checks:
        lines.append("- Manual review checks:")
        for item in manual_review_checks:
            lines.append(
                f"  - {item.get('id') or 'MR'} {item.get('check') or 'Review'} ({item.get('owner') or 'unassigned'}): {item.get('required_evidence') or 'not specified'}"
            )
    else:
        lines.append("- Manual review checks: none")

    lines.extend(
        [
            "",
            "## Test Suites",
            "",
        ]
    )
    if test_suites:
        for suite in test_suites:
            _extend_suite_markdown(lines, suite)
    else:
        lines.extend(["- None", ""])

    lines.extend(["## Critical Paths", ""])
    if critical_paths:
        for path in critical_paths:
            lines.extend(
                [
                    f"### {path.get('id') or 'CP'}: {path.get('name') or 'Unnamed critical path'}",
                    "",
                    f"- User journey: {path.get('user_journey') or 'not specified'}",
                    f"- Expected outcome: {path.get('expected_outcome') or 'not specified'}",
                    f"- Failure signal: {path.get('failure_signal') or 'not specified'}",
                    f"- Source ideas: {_inline_list(_string_list(path.get('source_idea_ids')))}",
                    "",
                ]
            )
    else:
        lines.extend(["- None", ""])

    lines.extend(["## Test Data Needs", ""])
    if test_data_needs:
        for item in test_data_needs:
            lines.extend(
                [
                    f"- **{item.get('id') or 'TD'} {item.get('name') or 'Test data'}** ({item.get('data_type') or 'unspecified'}): {item.get('need') or 'not specified'}",
                    f"  Validation: {item.get('validation') or 'not specified'}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Automation Candidates", ""])
    if automation_candidates:
        for item in automation_candidates:
            lines.extend(
                [
                    f"- **{item.get('id') or 'AC'} {item.get('candidate') or 'Automation'}** ({item.get('priority') or 'unspecified'}): {item.get('automation_type') or 'not specified'}",
                    f"  Trigger: {item.get('trigger') or 'not specified'}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Manual Review Checks", ""])
    if manual_review_checks:
        for item in manual_review_checks:
            lines.extend(
                [
                    f"- **{item.get('id') or 'MR'} {item.get('check') or 'Review'}** ({item.get('owner') or 'unassigned'}): {item.get('review_prompt') or 'not specified'}",
                    f"  Required evidence: {item.get('required_evidence') or 'not specified'}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence Gaps", ""])
    if evidence_gaps:
        for gap in evidence_gaps:
            _extend_gap_markdown(lines, gap)
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def _extend_suite_markdown(
    lines: list[str],
    suite: dict[str, Any],
    *,
    include_priority: bool = False,
) -> None:
    lines.extend(
        [
            f"### {suite.get('id') or 'QAS'}: {suite.get('name') or 'Unnamed suite'}",
            "",
            f"- Coverage type: {suite.get('coverage_type') or 'unspecified'}",
        ]
    )
    if include_priority:
        lines.append(f"- Priority: {_suite_priority(suite) or 'unspecified'}")
    lines.extend(
        [
            f"- Objective: {suite.get('objective') or 'not specified'}",
            f"- Owner: {suite.get('owner') or 'unassigned'}",
            f"- Source ideas: {_inline_list(_string_list(suite.get('source_idea_ids')))}",
            "- Test cases:",
        ]
    )
    _extend_indented_list(lines, _string_list(suite.get("test_cases")))
    lines.append("- Exit criteria:")
    _extend_indented_list(lines, _string_list(suite.get("exit_criteria")))
    lines.append("")


def _extend_indented_list(lines: list[str], values: list[str]) -> None:
    if values:
        lines.extend(f"  - {value}" for value in values)
    else:
        lines.append("  - None")


def _extend_gap_markdown(lines: list[str], gap: dict[str, Any]) -> None:
    lines.extend(
        [
            f"- **{gap.get('id') or 'EG'} {gap.get('field') or 'unknown'}** ({gap.get('severity') or 'unknown'}): {gap.get('gap') or 'not specified'}",
            f"  Needed for QA: {gap.get('needed_for_qa') or 'not specified'}",
        ]
    )


def _default_environments(
    test_data_needs: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, str]]:
    if not test_data_needs and not source_idea_ids:
        return []
    data_values = [
        item.get("name") or item.get("id") or "test data"
        for item in test_data_needs
        if isinstance(item, dict)
    ]
    return [
        {
            "id": "ENV1",
            "name": "Local deterministic test run",
            "purpose": "Run unit, integration, acceptance, and regression checks without external services.",
            "data": _inline_list(data_values),
        }
    ]


def qa_test_plan_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Return a stable filename for a QA test plan export."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-qa-test-plan.{extension}"
    )


def render_qa_test_plan_csv(report: dict[str, Any]) -> str:
    """Render QA scenarios and test cases as deterministic CSV text."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()

    for row in _csv_rows(report):
        writer.writerow(row)

    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    brief = report.get("design_brief") or {}
    design_brief_id = _csv_cell(brief.get("id"))
    evidence_reference_ids = _evidence_reference_ids(report)

    for suite in report.get("test_suites", []):
        source_references = _csv_references(suite.get("source_idea_ids"), evidence_reference_ids)
        for test_case in suite.get("test_cases", []):
            rows.append(
                {
                    "design_brief_id": design_brief_id,
                    "area": _csv_cell(suite.get("name") or suite.get("id")),
                    "scenario_name": _csv_cell(test_case),
                    "priority": _csv_cell(_suite_priority(suite)),
                    "test_type": _csv_cell(suite.get("coverage_type")),
                    "preconditions": _csv_cell(suite.get("objective")),
                    "steps": _csv_cell(test_case),
                    "expected_result": _csv_cell(suite.get("exit_criteria")),
                    "owner": _csv_cell(suite.get("owner")),
                    "evidence_source_references": source_references,
                }
            )

    for path in report.get("critical_paths", []):
        rows.append(
            {
                "design_brief_id": design_brief_id,
                "area": "Critical Path",
                "scenario_name": _csv_cell(path.get("name") or path.get("id")),
                "priority": "high",
                "test_type": "acceptance",
                "preconditions": _csv_cell(path.get("user_journey")),
                "steps": _csv_cell(path.get("user_journey")),
                "expected_result": _csv_cell(path.get("expected_outcome")),
                "owner": "Product owner",
                "evidence_source_references": _csv_references(
                    path.get("source_idea_ids"),
                    evidence_reference_ids,
                ),
            }
        )

    return rows


def _evidence_reference_ids(report: dict[str, Any]) -> list[str]:
    return [
        _csv_cell(reference.get("id"))
        for reference in report.get("evidence_references", [])
        if _csv_cell(reference.get("id"))
    ]


def _csv_references(source_idea_ids: Any, evidence_reference_ids: list[str]) -> str:
    values = [*_string_list(source_idea_ids), *evidence_reference_ids]
    return _csv_cell(_dedupe_strings(values))


def _suite_priority(suite: dict[str, Any]) -> str:
    coverage_type = suite.get("coverage_type")
    if coverage_type in {"unit", "integration", "acceptance"}:
        return "high"
    if coverage_type == "regression":
        return "medium"
    return _csv_cell(suite.get("priority"))


def _qa_context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    fallbacks: list[str] = []
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    title = _first_text(design_brief.get("title"), "Untitled design brief")
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("product owner", "explicit_fallback"),
    )
    product_concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        f"{title} product concept",
    )
    validation_plan = _first_with_label(
        fallbacks,
        "validation_plan",
        (design_brief.get("validation_plan"), "design_brief.validation_plan"),
        (lead_idea and lead_idea.get("validation_plan"), "lead_idea.validation_plan"),
        (_field_values(source_ideas, "validation_plan"), "source_ideas.validation_plan"),
        ("Define owner-reviewed acceptance criteria before autonomous implementation.", "explicit_fallback"),
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    if not scope:
        fallbacks.append("mvp_scope")
    risks = _dedupe_strings(
        [
            *_string_list(design_brief.get("risks")),
            *_field_values(source_ideas, "domain_risks"),
        ]
    )
    if not risks:
        risks = ["Implementation risk is under-specified; validate behavior with conservative regression coverage."]
        fallbacks.append("risks")
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "product_concept": product_concept,
        "validation_plan": validation_plan,
        "primary_scope": scope[0] if scope else f"first usable {title} workflow",
        "secondary_scope": scope[1] if len(scope) > 1 else "handoff, reporting, and support behavior",
        "risks": risks[:5],
        "risk_count": len(risks),
        "fallbacks_used": _dedupe_strings(fallbacks),
    }


def _test_suites(
    context: dict[str, Any],
    evidence_gaps: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    gap_gate = "Evidence gaps are captured as explicit blocked, skipped, or owner-review items."
    if not evidence_gaps:
        gap_gate = "All suite assumptions are linked to brief fields or source idea evidence."
    return [
        {
            "id": "QAS1",
            "coverage_type": "unit",
            "name": "Unit coverage for deterministic artifact logic",
            "objective": f"Verify core transformations for {context['product_concept']} without external services.",
            "owner": "Implementation engineer",
            "test_cases": [
                f"Build pure-function tests for {context['primary_scope']} decisions, defaults, and validation branches.",
                "Assert stable ordering, IDs, counts, and JSON-serializable output.",
                "Cover empty, malformed, and duplicate source inputs with explicit fallback behavior.",
            ],
            "exit_criteria": [
                "Unit tests pass locally and in CI without network or LLM calls.",
                gap_gate,
            ],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "QAS2",
            "coverage_type": "integration",
            "name": "Integration coverage for persisted brief workflows",
            "objective": f"Prove persisted design brief data can drive {context['workflow_context']} behavior end to end.",
            "owner": "QA engineer",
            "test_cases": [
                "Seed lead and supporting source ideas, persist a design brief, and generate the artifact by brief id.",
                "Verify linked source ideas, risks, validation plan, and timestamps are represented deterministically.",
                "Exercise missing linked ideas and sparse briefs without failing the build.",
            ],
            "exit_criteria": [
                "Integration tests use the repository store layer and clean temporary databases.",
                "Missing optional data results in evidence gaps rather than exceptions.",
            ],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "QAS3",
            "coverage_type": "acceptance",
            "name": "Acceptance coverage for build handoff readiness",
            "objective": f"Confirm {context['buyer']} can decide whether {context['target_user']} can use the first release.",
            "owner": "Product owner",
            "test_cases": [
                f"Validate the primary user can complete {context['primary_scope']} in the intended workflow.",
                f"Review acceptance evidence against the stated validation plan: {context['validation_plan']}",
                "Record open questions, manual approvals, and launch blockers before autonomous implementation proceeds.",
            ],
            "exit_criteria": [
                "Acceptance checks identify owner, expected evidence, and go/no-go threshold.",
                "Manual review sign-off is captured for product, QA, and implementation owners.",
            ],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "QAS4",
            "coverage_type": "regression",
            "name": "Regression coverage for repeated artifact generation",
            "objective": "Protect stable handoff behavior as design brief fields and linked source ideas evolve.",
            "owner": "Release owner",
            "test_cases": [
                "Snapshot Markdown headings, suite IDs, and evidence gap wording for representative rich and sparse briefs.",
                "Rerun JSON generation twice for the same brief and compare exact structures.",
                f"Add regression cases for top risks: {_inline_list(context['risks'])}",
            ],
            "exit_criteria": [
                "Markdown rendering has no Python reprs and remains deterministic.",
                "Unsupported render formats raise a clear ValueError.",
            ],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _critical_paths(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "CP1",
            "name": "Primary user completes first value workflow",
            "user_journey": f"{context['target_user']} starts and completes {context['primary_scope']} in {context['workflow_context']}.",
            "expected_outcome": f"The user receives the promised output from {context['product_concept']} without manual intervention.",
            "failure_signal": "The user cannot complete the workflow, receives incomplete output, or needs undocumented support.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "CP2",
            "name": "Owner reviews handoff evidence",
            "user_journey": f"{context['buyer']} reviews validation evidence and unresolved risks before implementation handoff.",
            "expected_outcome": "Owner can make an explicit proceed, revise, or stop decision.",
            "failure_signal": "Evidence does not map to acceptance criteria or leaves high-risk assumptions unresolved.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "CP3",
            "name": "Sparse or missing data stays actionable",
            "user_journey": "Implementation agent receives conservative defaults and evidence gaps when brief inputs are incomplete.",
            "expected_outcome": "The plan preserves coverage guidance without hiding missing validation data.",
            "failure_signal": "Generation fails or produces empty coverage sections for sparse briefs.",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _test_data_needs(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "TD1",
            "name": "Representative source ideas",
            "data_type": "fixture",
            "need": "Lead and supporting ideas with user, buyer, workflow, validation, risk, and evidence fields.",
            "validation": "Generated plan preserves source idea IDs and traceability.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "TD2",
            "name": "Sparse design brief",
            "data_type": "negative fixture",
            "need": "Brief with minimal scope, validation, risk, and evidence inputs.",
            "validation": "Generator emits explicit fallbacks and evidence gaps.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "TD3",
            "name": "Acceptance evidence",
            "data_type": "review record",
            "need": f"Validation notes showing {context['validation_plan']}",
            "validation": "Acceptance and manual review checks can be matched to owner-reviewed evidence.",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _automation_candidates(
    context: dict[str, Any],
    test_suites: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "AC1",
            "candidate": "Structured JSON contract",
            "automation_type": "unit test",
            "priority": "high",
            "trigger": "Run on every change to artifact builders or store serialization.",
            "covered_suite_ids": [suite["id"] for suite in test_suites if suite["coverage_type"] in {"unit", "regression"}],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "AC2",
            "candidate": "Persisted brief generation",
            "automation_type": "integration test",
            "priority": "high",
            "trigger": f"Run when design brief persistence or {context['workflow_context']} fields change.",
            "covered_suite_ids": ["QAS2"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "AC3",
            "candidate": "Markdown handoff rendering",
            "automation_type": "snapshot-style regression test",
            "priority": "medium",
            "trigger": "Run when renderer copy, headings, or fallback wording changes.",
            "covered_suite_ids": ["QAS3", "QAS4"],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _manual_review_checks(
    context: dict[str, Any],
    evidence_gaps: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    checks = [
        {
            "id": "MR1",
            "check": "Acceptance criteria owner review",
            "owner": "Product owner",
            "review_prompt": f"Confirm the planned tests prove {context['target_user']} can complete {context['primary_scope']}.",
            "required_evidence": "Signed acceptance criteria or annotated validation notes.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "MR2",
            "check": "Risk and regression owner review",
            "owner": "QA owner",
            "review_prompt": f"Confirm regression coverage addresses these risks: {_inline_list(context['risks'])}.",
            "required_evidence": "Risk-to-test mapping with skipped or deferred checks explained.",
            "source_idea_ids": source_idea_ids,
        },
    ]
    if evidence_gaps:
        checks.append(
            {
                "id": "MR3",
                "check": "Evidence gap disposition",
                "owner": "Implementation lead",
                "review_prompt": "Decide whether each evidence gap blocks build handoff, requires a manual test, or can be deferred.",
                "required_evidence": "Disposition for every evidence gap ID in this plan.",
                "source_idea_ids": source_idea_ids,
            }
        )
    return checks


def _evidence_gaps(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    context: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    checks = [
        ("mvp_scope", "MVP scope is missing; unit and acceptance coverage need concrete feature boundaries.", "high"),
        ("validation_plan", "Validation plan is missing; acceptance tests need owner-approved success criteria.", "high"),
        ("risks", "Risks are missing; regression coverage needs explicit failure modes.", "medium"),
        ("specific_user", "Target user is missing; critical paths need a named actor.", "medium"),
        ("workflow_context", "Workflow context is missing; integration coverage needs a concrete handoff path.", "medium"),
    ]
    for field, gap, severity in checks:
        missing = not _string_list(design_brief.get(field)) and not _field_values(source_ideas, field)
        if missing or field in context["fallbacks_used"]:
            gaps.append(
                {
                    "id": f"EG{len(gaps) + 1}",
                    "field": field,
                    "severity": severity,
                    "gap": gap,
                    "needed_for_qa": f"Provide `{field}` or record the manual review decision before build handoff.",
                    "source_idea_ids": source_idea_ids,
                }
            )
    if not evidence_refs:
        gaps.append(
            {
                "id": f"EG{len(gaps) + 1}",
                "field": "evidence_references",
                "severity": "medium",
                "gap": "No validation evidence, evidence signals, or inspiring insights are linked.",
                "needed_for_qa": "Attach evidence references or treat acceptance coverage as unvalidated.",
                "source_idea_ids": source_idea_ids,
            }
        )
    if not source_idea_ids:
        gaps.append(
            {
                "id": f"EG{len(gaps) + 1}",
                "field": "source_idea_ids",
                "severity": "medium",
                "gap": "No source idea references are available for test traceability.",
                "needed_for_qa": "Attach source idea IDs or document why this is a brief-only plan.",
                "source_idea_ids": [],
            }
        )
    return gaps


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
    return refs


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


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _first_with_label(
    fallbacks: list[str], field: str, *candidates: tuple[Any, str]
) -> str:
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


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_csv_cell(item)}" for key, item in value.items())
    if isinstance(value, set):
        return "; ".join(_csv_cell(item) for item in sorted(value, key=str))
    if isinstance(value, (list, tuple)):
        return "; ".join(_csv_cell(item) for item in value)
    return str(value)


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
