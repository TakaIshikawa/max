from max.profiles.loader import load_profile


def test_supply_chain_procurement_profile_loads_with_domain_context() -> None:
    profile = load_profile("supply_chain_procurement")

    assert profile.name == "supply_chain_procurement"
    assert profile.domain.name == "supply_chain_procurement"
    assert "analytics_tool" in profile.domain.categories
    assert "supplier risk analysts" in profile.domain.target_user_types
    assert "approval bottleneck resolution" in profile.domain.workflows
    assert any("contract audit trails" in item for item in profile.domain.hard_constraints)


def test_supply_chain_procurement_profile_sources_and_quality_weights() -> None:
    profile = load_profile("supply_chain_procurement")

    assert {source.adapter for source in profile.sources} == {"hackernews", "github", "reddit"}
    assert profile.evaluation.min_score == 56.0
    assert profile.domain_quality.enabled is True
    assert set(profile.domain_quality.scoring_dimensions) == {
        "supplier_risk",
        "approval_throughput",
        "savings_traceability",
    }
