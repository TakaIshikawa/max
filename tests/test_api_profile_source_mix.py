"""API tests for profile source mix summaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.server.app import create_app
from max.sources.registry import AdapterMetadata


def _client() -> TestClient:
    return TestClient(create_app())


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
            SourceConfig(adapter="hackernews", weight=2.0),
            SourceConfig(adapter="reddit", weight=1.0),
            SourceConfig(adapter="npm_registry", weight=1.0, params={"max_items": 20}),
            SourceConfig(adapter="cisa_kev", enabled=False),
        ],
    )


def _metadata() -> dict[str, AdapterMetadata]:
    return {
        "hackernews": AdapterMetadata("hackernews", ["filter_keywords"], [], "forum stories"),
        "reddit": AdapterMetadata("reddit", ["subreddits"], [], "subreddit posts"),
        "npm_registry": AdapterMetadata("npm_registry", ["queries"], [], "npm registry"),
        "cisa_kev": AdapterMetadata("cisa_kev", ["keywords"], [], "security feed"),
    }


def _adapter(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        source_type={
            "hackernews": "forum",
            "reddit": "forum",
            "npm_registry": "registry",
            "cisa_kev": "security",
        }[name]
    )


def test_get_profile_source_mix_returns_summary() -> None:
    with (
        patch("max.profiles.loader.load_profile", return_value=_profile()),
        patch("max.analysis.profile_source_mix.get_adapter_metadata", return_value=_metadata()),
        patch("max.analysis.profile_source_mix.get_adapter", side_effect=_adapter),
    ):
        response = _client().get("/api/v1/profiles/mix/source-mix?concentration_threshold=0.6")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_name"] == "mix"
    assert payload["domain"] == "developer-tools"
    assert payload["concentration_threshold"] == 0.6
    assert payload["enabled_adapter_count"] == 3
    assert payload["disabled_adapter_count"] == 1
    assert payload["total_weight"] == 4.0

    groups = {group["group"]: group for group in payload["groups"]}
    assert groups["forum/forum"]["adapters"] == ["hackernews", "reddit"]
    assert groups["forum/forum"]["adapter_percentage"] == 0.6667
    assert groups["forum/forum"]["over_concentrated"] is True
    assert groups["registry/registry"]["configured_limit_percentage"] == 1.0
    assert any(
        flag["group"] == "forum/forum" and flag["metric"] == "adapter_count"
        for flag in payload["concentration_flags"]
    )


def test_get_profile_source_mix_uses_default_threshold() -> None:
    with (
        patch("max.profiles.loader.load_profile", return_value=_profile()),
        patch("max.analysis.profile_source_mix.get_adapter_metadata", return_value=_metadata()),
        patch("max.analysis.profile_source_mix.get_adapter", side_effect=_adapter),
    ):
        response = _client().get("/api/v1/profiles/mix/source-mix")

    assert response.status_code == 200
    assert response.json()["concentration_threshold"] == 0.5


def test_get_profile_source_mix_unknown_profile_returns_404() -> None:
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        response = _client().get("/api/v1/profiles/missing/source-mix")

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found: missing"


def test_get_profile_source_mix_validates_threshold() -> None:
    response = _client().get("/api/v1/profiles/mix/source-mix?concentration_threshold=1.1")

    assert response.status_code == 422
