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
from max.spec.data_classification import generate_data_classification
from max.spec.data_retention_schedule import generate_data_retention_schedule
from max.spec.dependency_inventory import generate_dependency_inventory
from max.spec.experiment_card import generate_experiment_card
from max.spec.generator import generate_spec_preview
from max.spec.implementation_plan import generate_implementation_plan
from max.spec.launch_checklist import generate_launch_checklist
from max.spec.privacy_impact_assessment import generate_privacy_impact_assessment
from max.spec.readiness import evaluate_spec_readiness
from max.spec.rollback_plan import generate_rollback_plan
from max.spec.risk_register import generate_risk_register
from max.spec.slo_plan import generate_slo_plan
from max.spec.threat_model import generate_threat_model
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
    data_classification = generate_data_classification(spec_preview)
    data_retention_schedule = generate_data_retention_schedule(unit, evaluation, spec_preview)
    privacy_impact_assessment = generate_privacy_impact_assessment(spec_preview)
    dependency_inventory = generate_dependency_inventory(unit, evaluation, spec_preview)
    risk_register = generate_risk_register(unit, evaluation, evidence_density, contradictions)
    threat_model = generate_threat_model(unit, evaluation, spec_preview)
    slo_plan = generate_slo_plan(unit, evaluation, spec_preview)
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
            "data_classification": data_classification,
            "data_retention_schedule": data_retention_schedule,
            "privacy_impact_assessment": privacy_impact_assessment,
            "dependency_inventory": dependency_inventory,
            "risk_register": risk_register,
            "threat_model": threat_model,
            "slo_plan": slo_plan,
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
    data_classification = artifacts["data_classification"]
    data_retention_schedule = artifacts["data_retention_schedule"]
    privacy_impact_assessment = artifacts["privacy_impact_assessment"]
    dependency_inventory = artifacts["dependency_inventory"]
    risk_register = artifacts["risk_register"]
    threat_model = artifacts["threat_model"]
    slo_plan = artifacts["slo_plan"]
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
                *_bullets(
                    [
                        f"{item['id']} - {item['title']}: {item['goal']}"
                        for item in plan["milestones"]
                    ]
                ),
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
                *_bullets(
                    [
                        f"{item['id']} - {item['statement']}"
                        for item in criteria["functional_criteria"]
                    ]
                ),
                "Non-functional:",
                *_bullets(
                    [
                        f"{item['id']} - {item['statement']}"
                        for item in criteria["non_functional_criteria"]
                    ]
                ),
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
            "Data Classification",
            [
                f"Sensitivity: {data_classification['summary']['sensitivity_level']}",
                f"Categories: {data_classification['summary']['category_count']}",
                "Data categories:",
                *_bullets(
                    [
                        f"{item['id']} [{item['sensitivity']}]: {item['label']}"
                        for item in data_classification["data_categories"][:10]
                    ],
                    empty="None.",
                ),
                "Risk notes:",
                *_bullets(data_classification["risk_notes"][:5], empty="None."),
                "Safeguards:",
                *_bullets(
                    [
                        f"{item['id']} [{item['owner']}]: {item['requirement']}"
                        for item in data_classification["implementation_safeguards"][:6]
                    ],
                    empty="None.",
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Privacy Impact Assessment",
            [
                f"Privacy gate: {privacy_impact_assessment['summary']['privacy_gate']}",
                f"Privacy-sensitive inputs: {privacy_impact_assessment['summary']['privacy_sensitive_input_status']}",
                "Data subjects:",
                *_bullets(
                    [
                        f"{item['id']}: {item['label']}"
                        for item in privacy_impact_assessment["data_subjects"][:8]
                    ],
                    empty="None.",
                ),
                "Personal data:",
                *_bullets(
                    [
                        f"{item['id']} [{item['risk_level']}]: {item['label']}"
                        for item in privacy_impact_assessment["personal_data"][:8]
                    ],
                    empty="No privacy-sensitive inputs were detected in the spec.",
                ),
                "Review actions:",
                *_bullets(
                    [
                        f"{item['id']} [{item['owner']}]: {item['action']}"
                        for item in privacy_impact_assessment["review_actions"][:6]
                    ],
                    empty="None.",
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Data Retention Schedule",
            [
                f"Retention gate: {data_retention_schedule['summary']['retention_gate']}",
                f"Rules: {data_retention_schedule['summary']['retention_rule_count']}",
                "Retention rules:",
                *_bullets(
                    [
                        f"{item['id']} [{item['owner']}]: {item['data_category']} - {item['retention_period']}"
                        for item in data_retention_schedule["retention_rules"][:8]
                    ],
                    empty="None.",
                ),
                "Missing inputs:",
                *_bullets(data_retention_schedule["missing_inputs"][:8], empty="None."),
                "Next actions:",
                *_bullets(
                    [
                        f"{item['id']} [{item['owner']}]: {item['action']}"
                        for item in data_retention_schedule["next_actions"][:6]
                    ],
                    empty="None.",
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Dependency Inventory",
            [
                f"Dependency count: {dependency_inventory['summary']['dependency_count']}",
                f"High risk: {dependency_inventory['summary']['high_risk_count']}",
                *_bullets(
                    [
                        f"{item['id']} [{item['type']}; {item['risk_level']}]: {item['name']}"
                        for item in dependency_inventory["dependencies"][:10]
                    ],
                    empty="None.",
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Risk Register",
            [
                f"Risk count: {risk_register['summary']['risk_count']}",
                f"Critical: {risk_register['summary']['critical_risk_count']}; High: {risk_register['summary']['high_risk_count']}",
                *_bullets(
                    [
                        f"{item['id']} ({item['severity']}): {item['description']}"
                        for item in risk_register["risks"][:10]
                    ]
                ),
            ],
        )
    )
    lines.extend(
        _section(
            "Threat Model",
            [
                f"Decision: {threat_model['review_gate']['decision']}",
                f"High severity scenarios: {len(threat_model['review_gate']['high_severity_scenario_ids'])}",
                "Threat scenarios:",
                *_bullets(
                    [
                        f"{item['id']} ({item['severity']}): {item['title']} - {item['affected_asset']}"
                        for item in threat_model["threat_scenarios"][:10]
                    ],
                    empty="None.",
                ),
                "Required mitigations:",
                *_bullets(threat_model["review_gate"]["required_mitigations"], empty="None."),
            ],
        )
    )
    lines.extend(
        _section(
            "SLO Plan",
            [
                f"Launch tier: {slo_plan['summary']['launch_tier']}",
                "Objectives:",
                *_bullets(
                    [
                        f"{item['id']} [{item['type']}]: {item['target']}"
                        for item in slo_plan["objectives"]
                    ],
                    empty="None.",
                ),
                "Alerts:",
                *_bullets(
                    [
                        f"{item['id']} ({item['severity']}): {item['name']}"
                        for item in slo_plan["alerts"][:8]
                    ],
                    empty="None.",
                ),
                "Gaps:",
                *_bullets(
                    [
                        f"{item['id']} [{item['owner']}]: {item['description']}"
                        for item in slo_plan["gaps"][:8]
                    ],
                    empty="None.",
                ),
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
