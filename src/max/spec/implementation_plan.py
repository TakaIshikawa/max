"""Generate autonomous-agent implementation plans from spec previews."""

from __future__ import annotations

import re
from typing import Any

from max.spec.generator import generate_spec_preview
from max.spec.readiness import evaluate_spec_readiness
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


IMPLEMENTATION_PLAN_SCHEMA_VERSION = "max-implementation-plan/v1"


def generate_implementation_plan(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    spec_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an idea, evaluation, and spec preview into an execution outline."""
    preview = spec_preview or generate_spec_preview(unit, evaluation)
    readiness = evaluate_spec_readiness(unit, evaluation)
    expected_files = _expected_files(unit, preview)
    validation_steps = _validation_steps(unit, preview)
    milestones = _milestones(unit, preview, expected_files, validation_steps)

    return {
        "schema_version": IMPLEMENTATION_PLAN_SCHEMA_VERSION,
        "kind": "max.implementation_plan",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "spec_preview_schema_version": preview.get("schema_version"),
            "spec_kind": preview.get("kind"),
        },
        "summary": {
            "title": unit.title,
            "one_liner": unit.one_liner,
            "target_user": unit.specific_user or unit.target_users,
            "workflow_context": unit.workflow_context,
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
            "readiness_status": readiness["status"],
            "readiness_score": readiness["score"],
        },
        "milestones": milestones,
        "task_breakdown": _flatten_tasks(milestones),
        "validation_steps": validation_steps,
        "expected_files_modules": expected_files,
        "risks": _risks(unit, evaluation, readiness),
        "open_questions": _open_questions(unit, evaluation, readiness),
        "agent_handoff": {
            "start_here": [
                "Confirm the target repository structure and package manager.",
                "Map expected files/modules onto the existing codebase before editing.",
                "Keep spec readiness findings visible, but use this plan as the execution outline.",
            ],
            "definition_of_done": [
                "MVP scope from the spec preview is implemented.",
                "Validation steps pass locally and are documented for handoff.",
                "Known risks and unanswered questions are either resolved or explicitly deferred.",
            ],
        },
    }


def render_implementation_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a generated implementation plan as deterministic Markdown."""
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    title = _text(summary.get("title")) or _text(plan.get("idea_id")) or "Untitled Idea"

    lines = [
        f"# Implementation Plan: {title}",
        "",
        f"- Schema version: {_text(plan.get('schema_version')) or 'none'}",
        f"- Idea ID: {_text(plan.get('idea_id')) or _text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Source domain: {_text(source.get('domain')) or 'none'}",
        f"- Spec preview schema: {_text(source.get('spec_preview_schema_version')) or 'none'}",
        f"- Spec kind: {_text(source.get('spec_kind')) or 'none'}",
        f"- One-liner: {_text(summary.get('one_liner')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context')) or 'none'}",
        f"- Target user: {_text(summary.get('target_user')) or 'none'}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        f"- Readiness status: {_text(summary.get('readiness_status')) or 'none'}",
        f"- Readiness score: {_text(summary.get('readiness_score')) or 'none'}",
        "",
    ]

    _extend_section(lines, "Milestones", _dict_items(plan.get("milestones")), _render_milestone)
    _extend_section(
        lines,
        "Expected Files and Modules",
        _dict_items(plan.get("expected_files_modules")),
        _render_expected_file,
    )
    _extend_section(
        lines,
        "Validation Steps",
        _dict_items(plan.get("validation_steps")),
        _render_validation_step,
    )
    _extend_section(lines, "Risks", _dict_items(plan.get("risks")), _render_risk)
    _extend_section(
        lines,
        "Open Questions",
        _list_items(plan.get("open_questions")),
        _render_bullet_item,
    )
    _render_agent_handoff(lines, plan.get("agent_handoff"))

    return "\n".join(lines).rstrip() + "\n"


def _milestones(
    unit: BuildableUnit,
    preview: dict[str, Any],
    expected_files: list[dict[str, str]],
    validation_steps: list[dict[str, str]],
) -> list[dict[str, Any]]:
    core_files = [item["path"] for item in expected_files if item["role"] in {"core", "interface"}]
    test_files = [item["path"] for item in expected_files if item["role"] == "test"]

    return [
        {
            "id": "M1",
            "title": "Spec Alignment",
            "goal": "Convert the spec preview into concrete repository acceptance criteria.",
            "tasks": [
                _task(
                    "T1",
                    "Review project, problem, solution, and execution sections from the spec preview.",
                    "Acceptance criteria capture the intended MVP behavior and non-goals.",
                    ["spec-preview"],
                ),
                _task(
                    "T2",
                    "Identify existing modules, conventions, commands, and test harnesses to extend.",
                    "Implementation targets are mapped before new abstractions are added.",
                    ["repository"],
                ),
            ],
            "validation": ["Document accepted scope and deferred scope before coding."],
            "expected_files_modules": [],
        },
        {
            "id": "M2",
            "title": "MVP Implementation",
            "goal": _compact(preview.get("solution", {}).get("approach")) or f"Build {unit.title}.",
            "tasks": [
                _task(
                    "T3",
                    "Add the core domain model and execution path for the MVP workflow.",
                    "Primary workflow can run with representative local inputs.",
                    core_files,
                ),
                _task(
                    "T4",
                    "Expose the user-facing interface appropriate for the idea category.",
                    "Target users can trigger the workflow without reaching into internals.",
                    [item["path"] for item in expected_files if item["role"] == "interface"],
                    ["T3"],
                ),
                _task(
                    "T5",
                    "Integrate configured stack choices and persistence or external-service boundaries.",
                    "Dependencies are isolated behind clear modules and can be tested with fixtures.",
                    [item["path"] for item in expected_files if item["role"] in {"config", "integration"}],
                    ["T3"],
                ),
            ],
            "validation": ["Run the primary workflow against a fixture or small real-world sample."],
            "expected_files_modules": core_files,
        },
        {
            "id": "M3",
            "title": "Validation Harness",
            "goal": "Prove the MVP works and catches the failure modes named in the spec.",
            "tasks": [
                _task(
                    "T6",
                    "Add focused unit tests for core behavior, edge cases, and error handling.",
                    "Core behavior has deterministic automated coverage.",
                    test_files,
                    ["T3"],
                ),
                _task(
                    "T7",
                    "Add integration or acceptance coverage for the end-to-end MVP workflow.",
                    "The workflow passes through the public interface using realistic fixtures.",
                    test_files,
                    ["T4", "T5"],
                ),
            ],
            "validation": [step["description"] for step in validation_steps],
            "expected_files_modules": test_files,
        },
        {
            "id": "M4",
            "title": "Release Handoff",
            "goal": "Make the result operable for the next autonomous or human maintainer.",
            "tasks": [
                _task(
                    "T8",
                    "Update usage documentation, configuration notes, and operational limits.",
                    "A new user can install, configure, and run the MVP path.",
                    [item["path"] for item in expected_files if item["role"] == "docs"],
                    ["T6", "T7"],
                ),
                _task(
                    "T9",
                    "Run the full validation command and record unresolved risks or open questions.",
                    "Handoff includes passing checks or explicit blockers.",
                    ["validation"],
                    ["T8"],
                ),
            ],
            "validation": ["All planned validation steps have a passing result or a named blocker."],
            "expected_files_modules": [item["path"] for item in expected_files if item["role"] == "docs"],
        },
    ]


def _task(
    task_id: str,
    description: str,
    acceptance: str,
    files: list[str],
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "description": description,
        "acceptance": acceptance,
        "expected_files_modules": files,
        "depends_on": depends_on or [],
    }


def _flatten_tasks(milestones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for milestone in milestones:
        for task in milestone["tasks"]:
            tasks.append(
                {
                    **task,
                    "milestone_id": milestone["id"],
                    "milestone_title": milestone["title"],
                }
            )
    return tasks


def _expected_files(unit: BuildableUnit, preview: dict[str, Any]) -> list[dict[str, str]]:
    slug = _slug(unit.title)
    stack = _stack_values(preview)
    language = " ".join(stack).lower()
    category = str(unit.category)
    files: list[dict[str, str]]

    if "typescript" in language or "node" in language or "javascript" in language:
        files = [
            {"path": "package.json", "role": "config", "reason": "Declare runtime scripts and dependencies."},
            {"path": "src/index.ts", "role": "core", "reason": "Export the MVP domain workflow."},
            {"path": f"src/{slug}.ts", "role": "core", "reason": "Implement the main product behavior."},
            {"path": f"tests/{slug}.test.ts", "role": "test", "reason": "Cover core behavior and edge cases."},
        ]
        if category == "cli_tool":
            files.insert(2, {"path": "src/cli.ts", "role": "interface", "reason": "Expose the command-line entry point."})
        else:
            files.insert(2, {"path": "src/api.ts", "role": "interface", "reason": "Expose the public application interface."})
    elif "python" in language:
        package = slug.replace("-", "_")
        files = [
            {"path": "pyproject.toml", "role": "config", "reason": "Declare package metadata and tooling."},
            {"path": f"src/{package}/__init__.py", "role": "core", "reason": "Expose package exports."},
            {"path": f"src/{package}/core.py", "role": "core", "reason": "Implement the main product behavior."},
            {"path": f"tests/test_{package}.py", "role": "test", "reason": "Cover core behavior and edge cases."},
        ]
        if category == "cli_tool":
            files.insert(3, {"path": f"src/{package}/cli.py", "role": "interface", "reason": "Expose the command-line entry point."})
        else:
            files.insert(3, {"path": f"src/{package}/api.py", "role": "interface", "reason": "Expose the public application interface."})
    else:
        files = [
            {"path": "src/core", "role": "core", "reason": "Implement the main product behavior."},
            {"path": "src/interface", "role": "interface", "reason": "Expose the workflow to target users."},
            {"path": "tests", "role": "test", "reason": "Cover core and end-to-end behavior."},
        ]

    files.append({"path": "README.md", "role": "docs", "reason": "Document setup, usage, and validation."})
    if preview.get("execution", {}).get("validation_plan"):
        files.append(
            {
                "path": f"tests/fixtures/{slug}",
                "role": "test",
                "reason": "Store representative inputs for the validation plan.",
            }
        )
    if unit.evidence_signals or unit.inspiring_insights:
        files.append(
            {
                "path": "docs/evidence.md",
                "role": "docs",
                "reason": "Preserve traceability to idea evidence and assumptions.",
            }
        )

    return files


def _validation_steps(unit: BuildableUnit, preview: dict[str, Any]) -> list[dict[str, str]]:
    steps = [
        {
            "id": "V1",
            "description": "Run focused unit tests for the core workflow and failure handling.",
            "evidence": "Passing automated test output.",
        },
        {
            "id": "V2",
            "description": "Run the public interface against representative fixture data.",
            "evidence": "Recorded command/API output or acceptance-test result.",
        },
    ]
    validation_plan = _compact(preview.get("execution", {}).get("validation_plan"))
    if validation_plan:
        steps.append(
            {
                "id": "V3",
                "description": validation_plan,
                "evidence": "Validation notes with sample size, observed result, and decision.",
            }
        )
    if unit.first_10_customers:
        steps.append(
            {
                "id": "V4",
                "description": f"Validate with target early customers: {unit.first_10_customers}.",
                "evidence": "Interview notes, pilot usage, or written feedback.",
            }
        )
    steps.append(
        {
            "id": f"V{len(steps) + 1}",
            "description": "Run formatting, linting, type checks, and the repository test suite before handoff.",
            "evidence": "Passing local validation command output.",
        }
    )
    return steps


def _risks(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    readiness: dict[str, Any],
) -> list[dict[str, str]]:
    risks = [
        {"source": "idea", "description": risk, "mitigation": "Address during MVP scope and validation."}
        for risk in unit.domain_risks
    ]
    if evaluation:
        risks.extend(
            {
                "source": "evaluation",
                "description": weakness,
                "mitigation": "Convert into an acceptance test, spike, or explicit non-goal.",
            }
            for weakness in evaluation.weaknesses
        )
        if evaluation.build_effort.value < 6.0:
            risks.append(
                {
                    "source": "evaluation",
                    "description": "Build effort score is low relative to the rest of the evaluation.",
                    "mitigation": "Start with a technical spike and narrow the first milestone if needed.",
                }
            )
    else:
        risks.append(
            {
                "source": "evaluation",
                "description": "No utility evaluation is available for this idea.",
                "mitigation": "Run evaluation before treating the plan as implementation-ready.",
            }
        )
    if readiness["failed_check_ids"]:
        risks.append(
            {
                "source": "readiness",
                "description": f"Spec readiness still has failing checks: {', '.join(readiness['failed_check_ids'])}.",
                "mitigation": readiness["remediation"],
            }
        )
    return risks


def _open_questions(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    readiness: dict[str, Any],
) -> list[str]:
    questions: list[str] = []
    if not unit.specific_user:
        questions.append("Which specific user persona should the MVP optimize for first?")
    if not unit.buyer:
        questions.append("Who is the economic buyer or internal sponsor for adoption?")
    if not unit.workflow_context:
        questions.append("Where in the user's workflow should the first version be invoked?")
    if not unit.validation_plan:
        questions.append("What concrete validation artifact proves the MVP is useful?")
    if not unit.first_10_customers:
        questions.append("Which first 10 customers or pilot users should be targeted?")
    if not unit.suggested_stack:
        questions.append("Which language, framework, and runtime should the implementation use?")
    if not unit.domain_risks:
        questions.append("What domain, compliance, security, or adoption risks must be handled?")
    if evaluation is None:
        questions.append("What utility evaluation recommendation should gate autonomous implementation?")
    for check_id in readiness["failed_check_ids"]:
        questions.append(f"How should the failing readiness check be resolved: {check_id}?")
    return list(dict.fromkeys(questions))


def _stack_values(preview: dict[str, Any]) -> list[str]:
    stack = preview.get("solution", {}).get("suggested_stack") or {}
    return [str(value) for value in stack.values() if str(value).strip()]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "implementation"


def _render_milestone(item: dict[str, Any]) -> list[str]:
    lines = [
        f"### {_text(item.get('id')) or 'M'}: {_text(item.get('title')) or 'Untitled milestone'}",
        f"- Goal: {_text(item.get('goal')) or 'not specified'}",
    ]
    lines.extend(_render_optional_owner_timeline(item))
    lines.append(f"- Expected files/modules: {_join_code(item.get('expected_files_modules'))}")

    validation = [_text(step) for step in _list_items(item.get("validation")) if _text(step)]
    lines.append("- Validation:")
    lines.extend(_indented_bullets(validation))

    tasks = _dict_items(item.get("tasks"))
    if tasks:
        lines.extend(["", "#### Tasks", ""])
        for task in tasks:
            lines.extend(_render_task(task))
            lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
    return lines


def _render_task(item: dict[str, Any]) -> list[str]:
    lines = [
        f"##### {_text(item.get('id')) or 'T'}",
        f"- Description: {_text(item.get('description')) or 'not specified'}",
        f"- Acceptance: {_text(item.get('acceptance')) or 'not specified'}",
        f"- Depends on: {_join_code(item.get('depends_on'))}",
        f"- Expected files/modules: {_join_code(item.get('expected_files_modules'))}",
    ]
    lines.extend(_render_optional_owner_timeline(item))
    return lines


def _render_expected_file(item: dict[str, Any]) -> list[str]:
    path = _text(item.get("path")) or "unspecified"
    lines = [
        f"### `{path}`",
        f"- Role: {_text(item.get('role')) or 'none'}",
        f"- Reason: {_text(item.get('reason')) or 'not specified'}",
    ]
    lines.extend(_render_optional_owner_timeline(item))
    return lines


def _render_validation_step(item: dict[str, Any]) -> list[str]:
    lines = [
        f"### {_text(item.get('id')) or 'V'}",
        f"- Description: {_text(item.get('description')) or 'not specified'}",
        f"- Evidence: {_text(item.get('evidence')) or 'not specified'}",
    ]
    lines.extend(_render_optional_owner_timeline(item))
    return lines


def _render_risk(item: dict[str, Any]) -> list[str]:
    title = _text(item.get("id")) or _text(item.get("source")) or "risk"
    lines = [
        f"### {title}",
        f"- Source: {_text(item.get('source')) or 'none'}",
        f"- Description: {_text(item.get('description')) or 'not specified'}",
        f"- Mitigation: {_text(item.get('mitigation')) or 'not specified'}",
    ]
    lines.extend(_render_optional_owner_timeline(item))
    return lines


def _render_bullet_item(item: Any) -> list[str]:
    return [f"- {_text(item) or 'not specified'}"]


def _render_agent_handoff(lines: list[str], handoff: Any) -> None:
    lines.extend(["## Agent Handoff", ""])
    if not isinstance(handoff, dict):
        lines.extend(["None.", ""])
        return

    start_here = [_text(item) for item in _list_items(handoff.get("start_here")) if _text(item)]
    definition_of_done = [
        _text(item) for item in _list_items(handoff.get("definition_of_done")) if _text(item)
    ]
    lines.extend(["### Start Here", ""])
    lines.extend(_indented_bullets(start_here, empty="None."))
    lines.extend(["", "### Definition of Done", ""])
    lines.extend(_indented_bullets(definition_of_done, empty="None."))
    lines.append("")


def _extend_section(lines: list[str], title: str, items: list[Any], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_optional_owner_timeline(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, label in (
        ("owner", "Owner"),
        ("suggested_owner", "Suggested owner"),
        ("timeline", "Timeline"),
        ("start_date", "Start date"),
        ("due_date", "Due date"),
        ("target_date", "Target date"),
    ):
        value = _text(item.get(key))
        if value:
            lines.append(f"- {label}: {value}")
    return lines


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _list_items(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value


def _join_code(value: Any) -> str:
    items = [_text(item) for item in _list_items(value) if _text(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _indented_bullets(items: list[str], empty: str = "None.") -> list[str]:
    if not items:
        return [f"  - {empty}"]
    return [f"  - {item}" for item in items]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
