from max.profiles.loader import load_profile


def test_manufacturing_quality_profile_loads_with_domain_context() -> None:
    profile = load_profile("manufacturing_quality")

    assert profile.name == "manufacturing_quality"
    assert profile.domain.name == "manufacturing_quality"
    assert "analytics_tool" in profile.domain.categories
    assert "quality engineers" in profile.domain.target_user_types
    assert "CAPA tracking" in profile.domain.workflows
    assert any("traceability" in item for item in profile.domain.hard_constraints)


def test_manufacturing_quality_profile_sources_and_quality_weights() -> None:
    profile = load_profile("manufacturing_quality")

    assert {source.adapter for source in profile.sources} == {"github", "hackernews", "reddit"}
    assert profile.evaluation.min_score == 57.0
    assert profile.domain_quality.enabled is True
    assert set(profile.domain_quality.scoring_dimensions) == {
        "quality_traceability",
        "downtime_relevance",
        "regulatory_readiness",
    }
