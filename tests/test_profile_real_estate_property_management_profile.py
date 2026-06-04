from max.profiles.loader import load_profile


def test_real_estate_property_management_profile_loads_with_domain_context() -> None:
    profile = load_profile("real_estate_property_management")

    assert profile.name == "real_estate_property_management"
    assert profile.domain.name == "real_estate_property_management"
    assert "reporting_tool" in profile.domain.categories
    assert "maintenance coordinators" in profile.domain.target_user_types
    assert "tenant communication tracking" in profile.domain.workflows
    assert any("compliance" in item for item in profile.domain.hard_constraints)


def test_real_estate_property_management_profile_sources_and_quality_weights() -> None:
    profile = load_profile("real_estate_property_management")

    assert {source.adapter for source in profile.sources} == {"hackernews", "github", "reddit"}
    assert profile.evaluation.min_score == 55.0
    assert profile.domain_quality.enabled is True
    assert set(profile.domain_quality.scoring_dimensions) == {
        "maintenance_triage",
        "tenant_communication",
        "portfolio_compliance",
    }
