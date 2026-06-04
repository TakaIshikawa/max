from max.profiles.loader import load_profile


def test_clinical_trial_operations_profile_loads_with_domain_context() -> None:
    profile = load_profile("clinical_trial_operations")

    assert profile.name == "clinical_trial_operations"
    assert profile.domain.name == "clinical_trial_operations"
    assert "data_pipeline" in profile.domain.categories
    assert "study coordinators" in profile.domain.target_user_types
    assert "patient recruitment tracking" in profile.domain.workflows
    assert any("patient privacy" in item for item in profile.domain.hard_constraints)


def test_clinical_trial_operations_profile_sources_and_quality_weights() -> None:
    profile = load_profile("clinical_trial_operations")

    assert {source.adapter for source in profile.sources} == {
        "clinical_trials",
        "github",
        "hackernews",
    }
    assert profile.evaluation.min_score == 58.0
    assert profile.domain_quality.enabled is True
    assert set(profile.domain_quality.scoring_dimensions) == {
        "patient_recruitment_fit",
        "protocol_compliance",
        "evidence_traceability",
    }
