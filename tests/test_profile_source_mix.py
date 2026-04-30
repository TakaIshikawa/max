"""Tests for profile source mix summaries."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from max.analysis.profile_source_mix import (
    build_profile_source_mix,
    build_profile_source_mix_for_profile,
)
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.sources.registry import AdapterMetadata


def _profile() -> PipelineProfile:
    return PipelineProfile(
        name="mix",
        domain=DomainContext(
            name="developer-tools",
            description="Developer tools",
            categories=["application"],
            target_user_types=["developers"],
        ),
        sources=[
            SourceConfig(adapter="hackernews", weight=1.5),
            SourceConfig(adapter="reddit", weight=0.5),
            SourceConfig(adapter="npm_registry", weight=1.0, params={"max_items": 10}),
            SourceConfig(adapter="cisa_kev", enabled=False, weight=2.0),
        ],
    )


def _metadata() -> dict[str, AdapterMetadata]:
    return {
        "hackernews": AdapterMetadata(
            name="hackernews",
            config_keys=["filter_keywords"],
            required_keys=[],
            description="Fetches forum stories.",
        ),
        "reddit": AdapterMetadata(
            name="reddit",
            config_keys=["subreddits"],
            required_keys=[],
            description="Fetches public subreddit posts.",
        ),
        "npm_registry": AdapterMetadata(
            name="npm_registry",
            config_keys=["queries", "max_items"],
            required_keys=[],
            description="Searches the npm registry.",
        ),
        "cisa_kev": AdapterMetadata(
            name="cisa_kev",
            config_keys=["keywords"],
            required_keys=[],
            description="Fetches CISA KEV security data.",
        ),
        "bluesky": AdapterMetadata(
            name="bluesky",
            config_keys=["queries"],
            required_keys=[],
            description="Fetches social posts.",
        ),
    }


def _adapter(name: str) -> SimpleNamespace:
    source_types = {
        "hackernews": "forum",
        "reddit": "forum",
        "npm_registry": "registry",
        "cisa_kev": "security",
        "bluesky": "forum",
    }
    return SimpleNamespace(source_type=source_types[name])


def test_profile_source_mix_counts_groups_percentages_and_flags_concentration() -> None:
    now = datetime(2026, 4, 30, tzinfo=timezone.utc)

    with (
        patch("max.analysis.profile_source_mix.get_adapter_metadata", return_value=_metadata()),
        patch("max.analysis.profile_source_mix.get_adapter", side_effect=_adapter),
    ):
        report = build_profile_source_mix_for_profile(
            _profile(),
            concentration_threshold=0.5,
            now=now,
        )

    payload = report.to_dict()
    assert payload["generated_at"] == "2026-04-30T00:00:00+00:00"
    assert payload["profile_name"] == "mix"
    assert payload["enabled_adapter_count"] == 3
    assert payload["disabled_adapter_count"] == 1
    assert payload["total_weight"] == 3.0
    assert payload["total_configured_limit"] == 10

    groups = {group["group"]: group for group in payload["groups"]}
    assert groups["forum/forum"] == {
        "group": "forum/forum",
        "source_type": "forum",
        "category": "forum",
        "adapter_count": 2,
        "adapter_percentage": 0.6667,
        "total_weight": 2.0,
        "weight_percentage": 0.6667,
        "total_configured_limit": 0,
        "configured_limit_percentage": 0.0,
        "adapters": ["hackernews", "reddit"],
        "over_concentrated": True,
    }
    assert groups["registry/registry"]["adapter_percentage"] == 0.3333
    assert groups["registry/registry"]["configured_limit_percentage"] == 1.0

    flags = {(flag["group"], flag["metric"]) for flag in payload["concentration_flags"]}
    assert ("forum/forum", "adapter_count") in flags
    assert ("forum/forum", "weight") in flags
    assert ("registry/registry", "configured_limit") in flags


def test_profile_source_mix_recommends_available_underrepresented_groups() -> None:
    with (
        patch("max.analysis.profile_source_mix.get_adapter_metadata", return_value=_metadata()),
        patch("max.analysis.profile_source_mix.get_adapter", side_effect=_adapter),
    ):
        report = build_profile_source_mix_for_profile(_profile(), concentration_threshold=0.8)

    recommendations = {rec.group: rec for rec in report.recommendations}
    assert recommendations["security/security_feed"].available_adapters == ["cisa_kev"]
    assert recommendations["forum/social"].available_adapters == ["bluesky"]


def test_build_profile_source_mix_loads_named_profile() -> None:
    profile = _profile()

    with (
        patch("max.analysis.profile_source_mix.profile_loader.load_profile", return_value=profile) as load,
        patch("max.analysis.profile_source_mix.get_adapter_metadata", return_value=_metadata()),
        patch("max.analysis.profile_source_mix.get_adapter", side_effect=_adapter),
    ):
        report = build_profile_source_mix("mix")

    load.assert_called_once_with("mix")
    assert report.profile_name == "mix"


def test_profile_source_mix_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="concentration_threshold"):
        build_profile_source_mix_for_profile(_profile(), concentration_threshold=0)
