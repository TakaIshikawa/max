from max.profiles.loader import load_profile


def test_legal_operations_profile_loads_with_domain_context() -> None:
    profile = load_profile("legal_operations")

    assert profile.name == "legal_operations"
    assert profile.domain.name == "legal_operations"
    assert "workflow_tool" in profile.domain.categories
    assert "legal operations managers" in profile.domain.target_user_types
    assert "contract review routing" in profile.domain.workflows
    assert any("confidentiality" in item for item in profile.domain.hard_constraints)


def test_legal_operations_profile_sources_and_quality_weights() -> None:
    profile = load_profile("legal_operations")

    assert {source.adapter for source in profile.sources} == {"github", "hackernews", "reddit"}
    assert profile.evaluation.weight_profile == "default"
    assert profile.domain_quality.enabled is True
    assert profile.domain_quality.scoring_dimensions["confidentiality_controls"].weight == 1.5
    assert profile.domain_quality.scoring_dimensions["auditability"].weight == 1.4
