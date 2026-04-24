"""Focused registry metadata tests for newly documented adapters."""

from __future__ import annotations

from unittest.mock import patch

from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry


def test_go_packages_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "go_packages"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["go_packages"]
        adapter = get_adapter("go_packages")

    assert adapter.name == "go_packages"


def test_go_packages_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "go_packages"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"go_packages"}
    assert metadata["go_packages"].config_keys == [
        "queries",
        "max_results",
        "min_imported_by",
        "include_stdlib",
    ]
    assert metadata["go_packages"].required_keys == []
    assert "pkg.go.dev" in metadata["go_packages"].description


def test_kubernetes_keps_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "kubernetes_keps"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["kubernetes_keps"]
        adapter = get_adapter("kubernetes_keps")

    assert adapter.name == "kubernetes_keps"


def test_kubernetes_keps_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "kubernetes_keps"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"kubernetes_keps"}
    assert metadata["kubernetes_keps"].config_keys == [
        "areas",
        "stages",
        "max_results",
        "github_token",
        "token",
        "token_env",
        "include_archived",
    ]
    assert metadata["kubernetes_keps"].required_keys == []
    assert "Kubernetes Enhancement Proposal" in metadata["kubernetes_keps"].description


def test_homebrew_formulae_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "homebrew_formulae"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["homebrew_formulae"]
        adapter = get_adapter("homebrew_formulae")

    assert adapter.name == "homebrew_formulae"


def test_homebrew_formulae_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "homebrew_formulae"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"homebrew_formulae"}
    assert metadata["homebrew_formulae"].config_keys == [
        "formulae_url",
        "casks_url",
        "include_casks",
        "queries",
        "categories",
        "min_install_count",
    ]
    assert metadata["homebrew_formulae"].required_keys == []
    assert "Homebrew formula and cask" in metadata["homebrew_formulae"].description


def test_apis_guru_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "apis_guru"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["apis_guru"]
        adapter = get_adapter("apis_guru")

    assert adapter.name == "apis_guru"


def test_apis_guru_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "apis_guru"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"apis_guru"}
    assert metadata["apis_guru"].config_keys == [
        "base_url",
        "queries",
        "providers",
        "preferred_versions_only",
        "categories",
    ]
    assert metadata["apis_guru"].required_keys == []
    assert "APIs.guru OpenAPI Directory" in metadata["apis_guru"].description


def test_github_octoverse_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "github_octoverse"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["github_octoverse"]
        adapter = get_adapter("github_octoverse")

    assert adapter.name == "github_octoverse"


def test_github_octoverse_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "github_octoverse"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"github_octoverse"}
    assert metadata["github_octoverse"].config_keys == [
        "report_urls",
        "local_paths",
        "sections",
        "keywords",
        "max_items",
    ]
    assert metadata["github_octoverse"].required_keys == []
    assert "Octoverse-style Markdown and JSON reports" in metadata["github_octoverse"].description
