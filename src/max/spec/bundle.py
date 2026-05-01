"""Bundle implementation-ready spec artifacts for one idea."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from max.analysis.contradictions import build_idea_contradiction_report
from max.analysis.evidence_density import build_evidence_density_report
from max.analysis.review_gate import build_review_gate_decision
from max.server.evidence_chain import build_evidence_chain_graph
from max.spec.acceptance_criteria import generate_acceptance_criteria
from max.spec.experiment_card import generate_experiment_card
from max.spec.generator import generate_spec_preview
from max.spec.implementation_plan import generate_implementation_plan
from max.spec.launch_checklist import generate_launch_checklist
from max.spec.readiness import evaluate_spec_readiness
from max.spec.rollback_plan import generate_rollback_plan
from max.spec.risk_register import generate_risk_register
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


SPEC_BUNDLE_SCHEMA_VERSION = "max-spec-bundle/v1"


def generate_spec_bundle(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    store: Store,
) -> dict[str, Any]:
    """Build a complete implementation packet without adding persistence."""
    warnings: list[str] = []
    if evaluation is None:
        warnings.append(
            "Utility evaluation is missing; evaluation-dependent artifacts were generated with explicit missing-evaluation gates."
        )

    spec_preview = generate_spec_preview(unit, evaluation)
    readiness = evaluate_spec_readiness(unit, evaluation)
    evidence_density = build_evidence_density_report(unit, store)
    contradictions = build_idea_contradiction_report(unit, store)
    implementation_plan = generate_implementation_plan(unit, evaluation, spec_preview)
    launch_checklist = generate_launch_checklist(unit, evaluation, spec_preview)
    rollback_plan = generate_rollback_plan(unit, evaluation, spec_preview)
    acceptance_criteria = generate_acceptance_criteria(unit, evaluation, evidence_density)
    experiment_card = generate_experiment_card(unit, evaluation)
    risk_register = generate_risk_register(unit, evaluation, evidence_density, contradictions)
    review_gate = _review_gate(unit.id, store, warnings)
    evidence_chain_summary = _evidence_chain_summary(unit, store)

    warnings.extend(evidence_density.get("missing_evidence_warnings", []))
    warnings.extend(review_gate.get("warnings", []))

    return {
        "schema_version": SPEC_BUNDLE_SCHEMA_VERSION,
        "kind": "max.spec_bundle",
        "idea_id": unit.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warnings": list(dict.fromkeys(warnings)),
        "artifacts": {
            "spec_preview": spec_preview,
            "readiness": readiness,
            "implementation_plan": implementation_plan,
            "launch_checklist": launch_checklist,
            "rollback_plan": rollback_plan,
            "acceptance_criteria": acceptance_criteria,
            "experiment_card": experiment_card,
            "risk_register": risk_register,
            "review_gate": review_gate,
            "evidence_density": evidence_density,
            "evidence_chain_summary": evidence_chain_summary,
        },
    }


def render_spec_bundle_markdown(bundle: dict[str, Any]) -> str:
    """Render a bundled implementation packet as one readable markdown document."""
    artifacts = bundle["artifacts"]
    preview = artifacts["spec_preview"]
    project = preview["project"]
    problem = preview["problem"]
    solution = preview["solution"]
    readiness = artifacts["readiness"]
    plan = artifacts["implementation_plan"]
    checklist = artifacts["launch_checklist"]
    rollback_plan = artifacts["rollback_plan"]
    criteria = artifacts["acceptance_criteria"]
    experiment = artifacts["experiment_card"]
    risk_register = artifacts["risk_register"]
    review_gate = artifacts["review_gate"]
    density = artifacts["evidence_density"]
    chain = artifacts["evidence_chain_summary"]

    lines = [
        f"# {project['title']} Implementation Packet",
        "",
        f"- Schema version: {bundle['schema_version']}",
        f"- Idea ID: {bundle['idea_id']}",
        f"- Generated: {bundle['generated_at']}",
        f"- Summary: {_text(project.get('summary'))}",
        "",
    ]

    lines.extend(_section("Warnings", _bullets(bundle.get("warnings", []), empty="No warnings.")))
    lines.extend(
        _section(
            "Spec Preview",
            [
                f"Problem: {_text(problem.get('statement'))}",
                f"Solution: {_text(solution.get('approach'))}",
                f"Target user: {_text(project.get('specific_user') or project.get('target_users'))}",
                f"Workflow context: {_text(project.get('workflow_context'))}",
                f"Value proposition: {_text(project.get('value_proposition'))}",
            ],
        )
    )
    lines.extend(
        _section(
            "Readiness",
            [
                f"Status: {readiness['status']} ({readiness['score']})",
                f"Failed checks: {', '.join(readiness['failed_check_ids']) or 'none'}",
                f"Remediation: {_text(readiness.get('remediation'))}",
            ],
        )
    )
    lines.extend(
        _section(
            "Implementation Plan",
            [
                f"Recommendation: {_text(plan['summary'].get('recommendation'))}",
                "Milestones:",
                *_bullets([f"{item['id']} - {item['title']}: {item['goal']}" for item in plan["milestones"]]),
                "Validation steps:",
                *_bullets([item["description"] for item in plan["validation_steps"]]),
            ],
        )
    )
    lines.extend(
        _section(
            "Launch Checklist",
            [
                f"Launch gate: {_text(checklist['summary'].get('launch_gate'))}",
                *_bullets(
                    [
                        f"{item['id']} [{item['section_title']}]: {item['task']}"
                        for item in checklist["checklist_items"][:12]
                    ]
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Rollback Plan",
            [
                f"Rollback window: {_text(rollback_plan['summary'].get('rollback_window'))}",
                "Rollback triggers:",
                *_bullets(
                    [
                        f"{item['id']} [{item['severity']}]: {item['name']} - {item['threshold']}"
                        for item in rollback_plan["rollback_triggers"][:8]
                    ]
                ),
                "Go/no-go checklist:",
                *_bullets(
                    [
                        f"{item['id']} [{item['owner']}]: {item['task']}"
                        for item in rollback_plan["go_no_go_checklist"]
                    ]
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Acceptance Criteria",
            [
                "Functional:",
                *_bullets([f"{item['id']} - {item['statement']}" for item in criteria["functional_criteria"]]),
                "Non-functional:",
                *_bullets([f"{item['id']} - {item['statement']}" for item in criteria["non_functional_criteria"]]),
            ],
        )
    )
    lines.extend(
        _section(
            "Experiment Card",
            [
                f"Primary hypothesis: {_text(experiment['primary_hypothesis'])}",
                f"Target participant: {_text(experiment['target_participant'].get('persona'))}",
                "Riskiest assumptions:",
                *_bullets([item["assumption"] for item in experiment["riskiest_assumptions"]]),
            ],
        )
    )
    lines.extend(
        _section(
            "Risk Register",
            [
                f"Risk count: {risk_register['summary']['risk_count']}",
                f"Critical: {risk_register['summary']['critical_risk_count']}; High: {risk_register['summary']['high_risk_count']}",
                *_bullets([f"{item['id']} ({item['severity']}): {item['description']}" for item in risk_register["risks"][:10]]),
            ],
        )
    )
    lines.extend(
        _section(
            "Review Gate",
            [
                f"Decision: {review_gate['decision']}",
                f"Confidence: {review_gate['confidence']}",
                "Blocking reasons:",
                *_bullets(review_gate["blocking_reasons"], empty="None."),
                "Required remediations:",
                *_bullets(review_gate["required_remediations"], empty="None."),
            ],
        )
    )
    lines.extend(
        _section(
            "Evidence Density",
            [
                f"Signals: {density['signal_count']}; Insights: {density['insight_count']}; Density score: {density['density_score']}",
                f"Average credibility: {_text(density.get('average_credibility'))}",
                "Evidence warnings:",
                *_bullets(density["missing_evidence_warnings"], empty="None."),
            ],
        )
    )
    lines.extend(
        _section(
            "Evidence Links",
            [
                *_bullets(
                    [
                        f"{edge['source']} -> {edge['target']} ({edge['type']}; {edge['role']})"
                        for edge in chain["edges"]
                    ],
                    empty="None.",
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Evidence Chain Summary",
            [
                f"Insight IDs: {', '.join(chain['insight_ids']) or 'none'}",
                f"Signal IDs: {', '.join(chain['signal_ids']) or 'none'}",
                f"Edge count: {chain['edge_count']}",
            ],
        )
    )

    return "\n".join(lines).rstrip() + "\n"


def render_spec_bundle_yaml(bundle: dict[str, Any]) -> str:
    """Render a bundled implementation packet as deterministic YAML."""
    import yaml

    return yaml.safe_dump(bundle, sort_keys=False, allow_unicode=True)


def _review_gate(idea_id: str, store: Store, warnings: list[str]) -> dict[str, Any]:
    try:
        return asdict(build_review_gate_decision(store, idea_id))
    except ValueError as exc:
        warnings.append(str(exc))
        return {
            "schema_version": "max-review-gate/v1",
            "kind": "max.review_gate",
            "idea_id": idea_id,
            "title": "",
            "decision": "hold",
            "confidence": 0.0,
            "blocking_reasons": [str(exc)],
            "warnings": [str(exc)],
            "required_remediations": ["Resolve review gate error before approval."],
            "evidence_used": [],
        }


def _evidence_chain_summary(unit: BuildableUnit, store: Store) -> dict[str, Any]:
    graph = build_evidence_chain_graph(unit, store)
    return {
        "idea_id": unit.id,
        "insight_count": len(graph["insights"]),
        "signal_count": len(graph["signals"]),
        "edge_count": len(graph["edges"]),
        "insight_ids": [item["id"] for item in graph["insights"]],
        "signal_ids": [item["id"] for item in graph["signals"]],
        "edges": graph["edges"],
    }


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", "", *body, ""]


def _bullets(items: list[Any], *, empty: str | None = None) -> list[str]:
    values = [f"- {_text(item)}" for item in items if _text(item)]
    if values:
        return values
    return [empty] if empty else []


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
