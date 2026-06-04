from max.profiles.loader import load_profile


def test_edtech_operations_profile_loads_with_domain_context() -> None:
    profile = load_profile("edtech_operations")

    assert profile.name == "edtech_operations"
    assert profile.domain.name == "edtech_operations"
    assert "workflow_tool" in profile.domain.categories
    assert "student success managers" in profile.domain.target_user_types
    assert "LMS course operations" in profile.domain.workflows
    assert any("student privacy" in item for item in profile.domain.hard_constraints)


def test_edtech_operations_profile_sources_and_quality_weights() -> None:
    profile = load_profile("edtech_operations")

    assert {source.adapter for source in profile.sources} == {"hackernews", "github", "reddit"}
    assert profile.evaluation.weight_profile == "default"
    assert profile.evaluation.min_score == 56.0
    assert profile.domain_quality.enabled is True
    assert profile.domain_quality.min_score == 68.0
    assert set(profile.domain_quality.scoring_dimensions) == {
        "learner_privacy",
        "operational_fit",
        "intervention_traceability",
    }
