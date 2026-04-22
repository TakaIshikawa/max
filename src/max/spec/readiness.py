"""Readiness checks for generating useful tact specs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


PASSING_RECOMMENDATIONS = {"strong_yes", "yes"}


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    label: str
    passed: bool
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "passed": self.passed,
            "remediation": "" if self.passed else self.remediation,
        }


def evaluate_spec_readiness(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
) -> dict[str, Any]:
    """Evaluate whether a buildable unit has enough detail for a tact spec."""
    checks = [
        _problem_clarity(unit),
        _target_user(unit),
        _validation_plan(unit),
        _evidence(unit),
        _risks(unit),
        _stack_specificity(unit),
        _evaluation_recommendation(evaluation),
    ]
    failed = [check for check in checks if not check.passed]
    score = round((len(checks) - len(failed)) / len(checks) * 100.0, 1)

    return {
        "idea_id": unit.id,
        "score": score,
        "status": "pass" if not failed else "fail",
        "passed": not failed,
        "failed_check_ids": [check.id for check in failed],
        "remediation": _remediation_text(failed),
        "checks": [check.to_dict() for check in checks],
    }


def _problem_clarity(unit: BuildableUnit) -> ReadinessCheck:
    passed = all(
        [
            _meaningful(unit.problem, min_words=5),
            _meaningful(unit.solution, min_words=5),
            _meaningful(unit.value_proposition, min_words=4),
        ]
    )
    return ReadinessCheck(
        id="problem_clarity",
        label="Problem clarity",
        passed=passed,
        remediation=(
            "Clarify the problem, proposed solution, and value proposition with "
            "specific language that a spec author can turn into scope."
        ),
    )


def _target_user(unit: BuildableUnit) -> ReadinessCheck:
    passed = _meaningful(unit.specific_user, min_words=2) or (
        unit.target_users in {"humans", "agents"}
        and _meaningful(unit.workflow_context, min_words=3)
    )
    return ReadinessCheck(
        id="target_user",
        label="Target user",
        passed=passed,
        remediation=(
            "Name a specific user persona and workflow context instead of only a "
            "broad target_users value."
        ),
    )


def _validation_plan(unit: BuildableUnit) -> ReadinessCheck:
    passed = _meaningful(unit.validation_plan, min_words=5)
    return ReadinessCheck(
        id="validation_plan",
        label="Validation plan",
        passed=passed,
        remediation=(
            "Add a validation plan with concrete users, artifacts, or measurable "
            "acceptance criteria for the MVP."
        ),
    )


def _evidence(unit: BuildableUnit) -> ReadinessCheck:
    evidence_sets = {
        "insights": unit.inspiring_insights,
        "signals": unit.evidence_signals,
        "source_ideas": unit.source_idea_ids,
    }
    evidence_count = sum(len(values) for values in evidence_sets.values())
    diversity_count = sum(1 for values in evidence_sets.values() if values)
    if _meaningful(unit.evidence_rationale, min_words=4):
        diversity_count += 1

    passed = evidence_count >= 2 and diversity_count >= 2
    return ReadinessCheck(
        id="evidence_count_diversity",
        label="Evidence count and diversity",
        passed=passed,
        remediation=(
            "Attach at least two evidence references from at least two evidence "
            "types, such as insights, signals, source ideas, or a clear evidence rationale."
        ),
    )


def _risks(unit: BuildableUnit) -> ReadinessCheck:
    passed = any(_meaningful(risk, min_words=2) for risk in unit.domain_risks)
    return ReadinessCheck(
        id="risks",
        label="Risks",
        passed=passed,
        remediation=(
            "List the main domain, product, technical, or adoption risks the tact "
            "spec should address."
        ),
    )


def _stack_specificity(unit: BuildableUnit) -> ReadinessCheck:
    stack_values = [str(value).strip() for value in unit.suggested_stack.values()]
    passed = (
        _meaningful(unit.tech_approach, min_words=4)
        and len([value for value in stack_values if value]) >= 2
    )
    return ReadinessCheck(
        id="stack_specificity",
        label="Stack specificity",
        passed=passed,
        remediation=(
            "Specify the technical approach and at least two concrete stack choices "
            "such as language, framework, runtime, database, or deployment target."
        ),
    )


def _evaluation_recommendation(evaluation: UtilityEvaluation | None) -> ReadinessCheck:
    passed = evaluation is not None and evaluation.recommendation in PASSING_RECOMMENDATIONS
    return ReadinessCheck(
        id="evaluation_recommendation",
        label="Evaluation recommendation",
        passed=passed,
        remediation=(
            "Run utility evaluation and address weaknesses until the recommendation "
            "is yes or strong_yes."
        ),
    )


def _meaningful(value: str | None, *, min_words: int) -> bool:
    if not value:
        return False
    words = [word for word in value.strip().split() if word]
    return len(words) >= min_words and len(value.strip()) >= 12


def _remediation_text(failed: list[ReadinessCheck]) -> str:
    if not failed:
        return "Ready to generate a tact spec."
    return " ".join(check.remediation for check in failed)
