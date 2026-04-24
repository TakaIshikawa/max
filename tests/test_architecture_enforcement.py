from __future__ import annotations

from max.analysis.architecture_enforcement import build_architecture_enforcement_report
from max.profiles.schema import ArchitectureConstraintsConfig, DomainContext, PipelineProfile
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def _profile(*, constraints: ArchitectureConstraintsConfig | None = None) -> PipelineProfile:
    return PipelineProfile(
        name="arch",
        domain=DomainContext(
            name="architecture",
            description="Architecture test profile",
            categories=["cli_tool", "library"],
            target_user_types=["humans", "agents"],
        ),
        architecture_constraints=constraints or ArchitectureConstraintsConfig(),
    )


def _unit(
    unit_id: str,
    *,
    category: str = "cli_tool",
    target_users: str = "humans",
    domain: str = "architecture",
    tech_approach: str = "",
    suggested_stack: dict | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="A test idea",
        category=category,
        problem="Problem",
        solution="Solution",
        target_users=target_users,
        value_proposition="Value",
        tech_approach=tech_approach,
        suggested_stack=suggested_stack or {},
        domain=domain,
    )


def test_architecture_enforcement_flags_constraint_violations(tmp_path) -> None:
    db_path = str(tmp_path / "arch.db")
    profile = _profile(
        constraints=ArchitectureConstraintsConfig(
            allowed_categories=["cli_tool"],
            allowed_target_users=["humans"],
            required_stack_decisions=["language", "runtime", "deployment"],
            allowed_stack_items={"language": ["python"]},
            rejected_stack_items={"language": ["ruby"]},
            allowed_deployment_patterns=["local", "container"],
            rejected_deployment_patterns=["cloud"],
            allowed_integrations=["github"],
            rejected_integrations=["slack"],
        )
    )
    unit = _unit(
        "bad-arch",
        category="application",
        target_users="both",
        tech_approach="Deploy as a cloud service with Slack notifications.",
        suggested_stack={
            "language": "ruby",
            "deployment": "cloud",
            "integrations": ["slack"],
        },
    )

    with Store(db_path=db_path) as store:
        store.insert_buildable_unit(unit)
        report = build_architecture_enforcement_report(profile, store)

    assert report.status == "violation"
    codes = {finding.code for finding in report.findings}
    assert "unsupported_category" in codes
    assert "unsupported_target_users" in codes
    assert "missing_stack_decision" in codes
    assert "unsupported_stack_item" in codes
    assert "rejected_stack_item" in codes
    assert "unsupported_deployment_assumption" in codes
    assert "rejected_deployment_assumption" in codes
    assert "unsupported_integration_assumption" in codes
    assert "rejected_integration_assumption" in codes


def test_architecture_enforcement_no_constraint_fallback_uses_profile_basics(tmp_path) -> None:
    db_path = str(tmp_path / "arch.db")
    profile = _profile()
    unit = _unit(
        "good-arch",
        tech_approach="Run locally as a CLI tool and call the GitHub API.",
        suggested_stack={
            "language": "python",
            "runtime": "local",
            "deployment": "local",
            "integrations": ["github"],
        },
    )

    with Store(db_path=db_path) as store:
        store.insert_buildable_unit(unit)
        report = build_architecture_enforcement_report(profile, store)

    assert report.constraints_configured is False
    assert report.status == "ok"
    assert report.findings == []
    assert report.categories_allowed == ["cli_tool", "library"]
    assert report.evaluation_weights
    assert any("required_stack_decisions" in item for item in report.recommended_constraint_additions)
