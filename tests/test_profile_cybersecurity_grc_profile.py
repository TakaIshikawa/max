from max.profiles.loader import load_profile


def test_cybersecurity_grc_profile_loads_with_domain_context() -> None:
    profile = load_profile("cybersecurity_grc")

    assert profile.name == "cybersecurity_grc"
    assert profile.domain.name == "cybersecurity_grc"
    assert "reporting_tool" in profile.domain.categories
    assert "GRC analysts" in profile.domain.target_user_types
    assert "control evidence collection" in profile.domain.workflows
    assert any("audit evidence" in item for item in profile.domain.hard_constraints)


def test_cybersecurity_grc_profile_sources_and_quality_weights() -> None:
    profile = load_profile("cybersecurity_grc")

    assert {source.adapter for source in profile.sources} == {
        "security_advisories",
        "github",
        "hackernews",
    }
    assert profile.evaluation.min_score == 57.0
    assert profile.domain_quality.enabled is True
    assert profile.domain_quality.scoring_dimensions["audit_evidence"].weight == 1.5
    assert "control_mapping" in profile.domain_quality.scoring_dimensions
