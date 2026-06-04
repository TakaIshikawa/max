from max.profiles.loader import load_profile


def test_aerospace_maintenance_profile_loads_with_domain_context() -> None:
    profile = load_profile("aerospace_maintenance")

    assert profile.name == "aerospace_maintenance"
    assert profile.domain.name == "aerospace_maintenance"
    assert "data_pipeline" in profile.domain.categories
    assert "reliability engineers" in profile.domain.target_user_types
    assert "maintenance record auditing" in profile.domain.workflows
    assert any("regulatory" in item for item in profile.domain.hard_constraints)


def test_aerospace_maintenance_profile_sources_and_quality_weights() -> None:
    profile = load_profile("aerospace_maintenance")

    assert {source.adapter for source in profile.sources} == {"github", "hackernews", "reddit"}
    assert profile.evaluation.weight_profile == "default"
    assert profile.evaluation.min_score == 58.0
    assert profile.domain_quality.enabled is True
    assert profile.domain_quality.scoring_dimensions["safety_compliance"].weight == 1.6
    assert "traceability" in profile.domain_quality.scoring_dimensions
