"""Tests for pipeline profile loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from max.profiles.loader import (
    get_default_profile,
    list_profiles,
    load_profile,
)
from max.profiles.schema import (
    DEFAULT_DOMAIN_CONTEXT,
    DomainContext,
    EvaluationConfig,
    PipelineProfile,
    SourceConfig,
)


# --- Schema tests ---


def test_source_config_defaults():
    sc = SourceConfig(adapter="reddit")
    assert sc.enabled is True
    assert sc.weight == 1.0
    assert sc.params == {}


def test_domain_context_required_fields():
    dc = DomainContext(
        name="test",
        description="test domain",
        categories=["app", "tool"],
        target_user_types=["users"],
    )
    assert dc.name == "test"
    assert dc.extra_instructions == ""
    assert dc.target_segments == []
    assert dc.workflows == []
    assert dc.buyer_roles == []
    assert dc.hard_constraints == []
    assert dc.bad_idea_patterns == []
    assert dc.good_idea_criteria == []


def test_evaluation_config_defaults():
    ec = EvaluationConfig()
    assert ec.weight_profile == "default"
    assert ec.custom_weights is None
    assert ec.min_score == 50.0


def test_pipeline_profile_defaults():
    profile = PipelineProfile(
        name="test",
        domain=DomainContext(
            name="test",
            description="test",
            categories=["app"],
            target_user_types=["users"],
        ),
    )
    assert profile.sources == []
    assert profile.signal_limit == 30
    assert profile.ideation_mode == "direct"
    assert profile.output_dir == ".max-output"
    assert profile.quality_loop_enabled is False
    assert profile.draft_count == 8


def test_default_domain_context_values():
    dc = DEFAULT_DOMAIN_CONTEXT
    assert dc.name == "developer-tools"
    assert "developer tools" in dc.description
    assert "mcp_server" in dc.categories
    assert "cli_tool" in dc.categories
    assert "application" in dc.categories
    assert "humans" in dc.target_user_types
    assert "agents" in dc.target_user_types


# --- Loader tests ---


def test_load_devtools_profile():
    """devtools.yaml should load and validate."""
    profile = load_profile("devtools")
    assert profile.name == "devtools"
    assert profile.domain.name == "developer-tools"
    assert len(profile.sources) == 13
    assert profile.signal_limit == 30
    assert profile.evaluation.weight_profile == "default"


def test_load_healthcare_profile():
    """healthcare.yaml should load and validate."""
    profile = load_profile("healthcare")
    assert profile.name == "healthcare"
    assert profile.domain.name == "healthcare"
    assert "clinical_tool" in profile.domain.categories
    assert "clinicians" in profile.domain.target_user_types
    assert "HIPAA" in profile.domain.extra_instructions
    assert "small specialty clinics" in profile.domain.target_segments
    assert "prior authorization" in profile.domain.workflows
    assert profile.quality_loop_enabled is False
    assert profile.signal_limit == 25


def test_load_unknown_profile_raises():
    with pytest.raises(FileNotFoundError, match="not found"):
        load_profile("nonexistent_profile_xyz")


def test_get_default_profile_matches_devtools():
    """Default profile should match devtools.yaml content."""
    default = get_default_profile()
    assert default.name == "devtools"
    assert default.domain.name == "developer-tools"
    assert len(default.sources) == 13

    # Verify adapter names match
    adapter_names = [s.adapter for s in default.sources]
    assert "hackernews" in adapter_names
    assert "reddit" in adapter_names
    assert "github" in adapter_names
    assert "nuget" in adapter_names
    assert "npm_registry" in adapter_names


def test_list_profiles_finds_yaml_files():
    names = list_profiles()
    assert "devtools" in names
    assert "healthcare" in names


def test_profile_source_configs_have_params():
    """devtools profile adapters should have correct params."""
    profile = load_profile("devtools")
    sources_by_adapter = {s.adapter: s for s in profile.sources}

    reddit = sources_by_adapter["reddit"]
    assert "programming" in reddit.params["subreddits"]

    github = sources_by_adapter["github"]
    assert "mcp" in github.params["topics"]

    npm = sources_by_adapter["npm_registry"]
    assert "mcp server" in npm.params["queries"]

    nuget = sources_by_adapter["nuget"]
    assert "semantic kernel" in nuget.params["queries"]
    assert "Microsoft.SemanticKernel" in nuget.params["package_names"]


def test_profile_from_dict():
    """Should be able to construct profile from a dict (as YAML would produce)."""
    data = {
        "name": "test",
        "domain": {
            "name": "test-domain",
            "description": "A test domain",
            "categories": ["app", "tool"],
            "target_user_types": ["users", "admins"],
        },
        "sources": [
            {"adapter": "reddit", "params": {"subreddits": ["test"]}},
            {"adapter": "github", "enabled": False},
        ],
        "evaluation": {"min_score": 40.0},
        "signal_limit": 10,
    }
    profile = PipelineProfile(**data)
    assert profile.name == "test"
    assert len(profile.sources) == 2
    assert profile.sources[1].enabled is False
    assert profile.evaluation.min_score == 40.0
    assert profile.signal_limit == 10


def test_profile_yaml_round_trip(tmp_path: Path):
    """Write a profile to YAML and read it back."""
    profile_data = {
        "name": "roundtrip",
        "domain": {
            "name": "test",
            "description": "round trip test",
            "categories": ["app"],
            "target_user_types": ["users"],
        },
        "sources": [{"adapter": "hackernews"}],
        "signal_limit": 15,
    }
    yaml_path = tmp_path / "roundtrip.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(profile_data, f)

    with open(yaml_path) as f:
        loaded = yaml.safe_load(f)

    profile = PipelineProfile(**loaded)
    assert profile.name == "roundtrip"
    assert profile.signal_limit == 15
    assert len(profile.sources) == 1


@pytest.mark.parametrize("profile_name", list_profiles())
def test_all_profiles_load_successfully(profile_name: str):
    """Parametric test: all profile YAML files should load and validate successfully.

    This test discovers all *.yaml/*.yml files in the profiles/ directory and validates:
    1. YAML parses correctly
    2. Profile matches PipelineProfile schema (all required fields present)
    3. All referenced adapters exist in the registry
    4. All source configs have valid structure
    5. Domain context has required fields
    """
    # Load the profile - this will raise if validation fails
    profile = load_profile(profile_name)

    # Verify basic schema compliance
    assert isinstance(profile.name, str)
    assert len(profile.name) > 0

    # Verify domain context
    assert isinstance(profile.domain.name, str)
    assert isinstance(profile.domain.description, str)
    assert isinstance(profile.domain.categories, list)
    assert len(profile.domain.categories) > 0
    assert isinstance(profile.domain.target_user_types, list)
    assert len(profile.domain.target_user_types) > 0

    # Verify sources
    assert isinstance(profile.sources, list)
    for source in profile.sources:
        assert isinstance(source.adapter, str)
        assert isinstance(source.enabled, bool)
        assert isinstance(source.weight, (int, float))
        assert isinstance(source.params, dict)

    # Verify evaluation config
    assert isinstance(profile.evaluation.weight_profile, str)
    assert isinstance(profile.evaluation.min_score, (int, float))

    # Verify other fields
    assert isinstance(profile.output_dir, str)
    assert isinstance(profile.signal_limit, int)
    assert profile.signal_limit > 0
    assert isinstance(profile.ideation_mode, str)


# --- Tests for new domain profiles ---


def test_load_ai_infra_profile():
    """ai-infra.yaml should load and validate."""
    profile = load_profile("ai-infra")
    assert profile.name == "ai-infra"
    assert profile.domain.name == "ai-infrastructure"
    assert "inference_server" in profile.domain.categories
    assert "ml_engineers" in profile.domain.target_user_types
    assert "GPU utilization" in profile.domain.extra_instructions
    assert "mid-market AI product teams" in profile.domain.target_segments
    assert "model evaluation" in profile.domain.workflows
    assert profile.evaluation.min_score == 50.0


def test_load_hr_profile():
    """hr.yaml should load and validate."""
    profile = load_profile("hr")
    assert profile.name == "hr"
    assert profile.domain.name == "hr-people-ops"
    assert "recruiting_automation" in profile.domain.categories
    assert "hr_managers" in profile.domain.target_user_types
    assert "mid-market people teams" in profile.domain.target_segments
    assert "candidate screening" in profile.domain.workflows
    assert profile.evaluation.min_score == 45.0


def test_load_legaltech_profile():
    """legaltech.yaml should load and validate."""
    profile = load_profile("legaltech")
    assert profile.name == "legaltech"
    assert profile.domain.name == "legaltech"
    assert "contract_analysis" in profile.domain.categories
    assert "lawyers" in profile.domain.target_user_types
    assert "solo and small law firms" in profile.domain.target_segments
    assert "contract review" in profile.domain.workflows
    assert profile.evaluation.min_score == 45.0


def test_load_proptech_profile():
    """proptech.yaml should load and validate."""
    profile = load_profile("proptech")
    assert profile.name == "proptech"
    assert profile.domain.name == "proptech"
    assert "property_valuation" in profile.domain.categories
    assert "property_managers" in profile.domain.target_user_types
    assert "small property management firms" in profile.domain.target_segments
    assert "maintenance request triage" in profile.domain.workflows
    assert profile.evaluation.min_score == 45.0


def test_load_supply_chain_profile():
    """supply-chain.yaml should load and validate."""
    profile = load_profile("supply-chain")
    assert profile.name == "supply-chain"
    assert profile.domain.name == "supply-chain"
    assert "inventory_forecasting" in profile.domain.categories
    assert "supply_chain_managers" in profile.domain.target_user_types
    assert "mid-market manufacturers" in profile.domain.target_segments
    assert "supplier risk review" in profile.domain.workflows
    assert profile.evaluation.min_score == 45.0


def test_new_domain_profiles_have_required_source_adapters():
    """Test that new domain profiles reference only valid adapters."""
    from max.sources.registry import list_adapters

    valid_adapters = set(list_adapters())
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        for source in profile.sources:
            assert (
                source.adapter in valid_adapters
            ), f"Profile {profile_name} references unknown adapter: {source.adapter}"


def test_new_domain_profiles_have_source_configs():
    """Test that new domain profiles have at least one source adapter configured."""
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        assert len(profile.sources) > 0, f"Profile {profile_name} has no source adapters configured"


def test_new_domain_profiles_weights_are_valid():
    """Test that source adapter weights in new profiles are positive floats."""
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        for source in profile.sources:
            assert isinstance(source.weight, (int, float)), f"Invalid weight type in {profile_name}"
            assert source.weight >= 0, f"Negative weight in {profile_name}: {source.weight}"


def test_new_domain_profiles_have_buyer_roles():
    """Test that new domain profiles specify buyer roles."""
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        assert (
            len(profile.domain.buyer_roles) > 0
        ), f"Profile {profile_name} has no buyer_roles specified"


def test_new_domain_profiles_have_hard_constraints():
    """Test that new domain profiles specify hard constraints."""
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        assert (
            len(profile.domain.hard_constraints) > 0
        ), f"Profile {profile_name} has no hard_constraints specified"


def test_new_domain_profiles_have_bad_idea_patterns():
    """Test that new domain profiles specify bad idea patterns."""
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        assert (
            len(profile.domain.bad_idea_patterns) > 0
        ), f"Profile {profile_name} has no bad_idea_patterns specified"


def test_new_domain_profiles_have_good_idea_criteria():
    """Test that new domain profiles specify good idea criteria."""
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        assert (
            len(profile.domain.good_idea_criteria) > 0
        ), f"Profile {profile_name} has no good_idea_criteria specified"


def test_ai_infra_domain_quality_config():
    """Test that ai-infra profile has domain_quality configuration enabled."""
    profile = load_profile("ai-infra")

    # Verify domain_quality is enabled
    assert profile.domain_quality.enabled is True
    assert profile.domain_quality.min_score == 69.0

    # Verify required_fields
    assert "buyer" in profile.domain_quality.required_fields
    assert "specific_user" in profile.domain_quality.required_fields
    assert "workflow_context" in profile.domain_quality.required_fields
    assert "validation_plan" in profile.domain_quality.required_fields
    assert "tech_approach" in profile.domain_quality.required_fields

    # Verify scoring dimensions exist
    assert "workflow_specificity" in profile.domain_quality.scoring_dimensions
    assert "buyer_clarity" in profile.domain_quality.scoring_dimensions
    assert "evidence_support" in profile.domain_quality.scoring_dimensions
    assert "measurable_infra_impact" in profile.domain_quality.scoring_dimensions

    # Verify dimension weights
    assert profile.domain_quality.scoring_dimensions["workflow_specificity"].weight == 1.3
    assert profile.domain_quality.scoring_dimensions["buyer_clarity"].weight == 1.2
    assert profile.domain_quality.scoring_dimensions["evidence_support"].weight == 1.4
    assert profile.domain_quality.scoring_dimensions["measurable_infra_impact"].weight == 1.5

    # Verify hard rejections
    assert "missing_buyer" in profile.domain_quality.hard_rejections
    assert "missing_workflow" in profile.domain_quality.hard_rejections
    assert "no_measurable_metric" in profile.domain_quality.hard_rejections

    # Verify preferred patterns
    assert "inference cost or latency optimizer" in profile.domain_quality.preferred_patterns
    assert "eval-backed model router" in profile.domain_quality.preferred_patterns


def test_new_domain_profiles_adapter_params_are_valid():
    """Test that adapter parameters in new profiles are properly structured."""
    new_profiles = ["ai-infra", "hr", "legaltech", "proptech", "supply-chain"]

    for profile_name in new_profiles:
        profile = load_profile(profile_name)
        for source in profile.sources:
            # Verify params is a dict
            assert isinstance(source.params, dict), f"Invalid params in {profile_name} for {source.adapter}"

            # Verify enabled is a boolean
            assert isinstance(source.enabled, bool), f"Invalid enabled value in {profile_name} for {source.adapter}"


def test_new_domain_profiles_min_score_consistency():
    """Test that evaluation min_score matches expected values for new profiles."""
    expected_scores = {
        "ai-infra": 50.0,  # Uses default weight_profile
        "hr": 45.0,
        "legaltech": 45.0,
        "proptech": 45.0,
        "supply-chain": 45.0,
    }

    for profile_name, expected_score in expected_scores.items():
        profile = load_profile(profile_name)
        assert (
            profile.evaluation.min_score == expected_score
        ), f"Profile {profile_name} has unexpected min_score: {profile.evaluation.min_score} (expected {expected_score})"
