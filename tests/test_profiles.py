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
    assert len(profile.sources) == 11
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
    assert len(default.sources) == 11

    # Verify adapter names match
    adapter_names = [s.adapter for s in default.sources]
    assert "hackernews" in adapter_names
    assert "reddit" in adapter_names
    assert "github" in adapter_names
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
