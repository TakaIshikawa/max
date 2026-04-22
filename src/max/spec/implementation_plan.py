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
