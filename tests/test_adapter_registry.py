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


def test_ai_code_trust_reports_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "ai_code_trust_reports"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["ai_code_trust_reports"]
        adapter = get_adapter("ai_code_trust_reports")

    assert adapter.name == "ai_code_trust_reports"


def test_ai_code_trust_reports_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "ai_code_trust_reports"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"ai_code_trust_reports"}
    assert metadata["ai_code_trust_reports"].config_keys == [
        "report_urls",
        "local_paths",
        "sections",
        "keywords",
        "min_percent",
        "max_items",
    ]
    assert metadata["ai_code_trust_reports"].required_keys == []
    assert "AI coding trust" in metadata["ai_code_trust_reports"].description


def test_jetbrains_survey_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "jetbrains_survey"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["jetbrains_survey"]
        adapter = get_adapter("jetbrains_survey")

    assert adapter.name == "jetbrains_survey"


def test_jetbrains_survey_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "jetbrains_survey"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"jetbrains_survey"}
    assert metadata["jetbrains_survey"].config_keys == [
        "survey_urls",
        "local_paths",
        "question_filters",
        "min_percent",
        "max_rows",
        "year",
    ]
    assert metadata["jetbrains_survey"].required_keys == []
    assert "JetBrains Developer Ecosystem survey CSV exports" in metadata[
        "jetbrains_survey"
    ].description


def test_federal_register_healthcare_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "federal_register_healthcare"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["federal_register_healthcare"]
        adapter = get_adapter("federal_register_healthcare")

    assert adapter.name == "federal_register_healthcare"


def test_federal_register_healthcare_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "federal_register_healthcare"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"federal_register_healthcare"}
    assert metadata["federal_register_healthcare"].config_keys == [
        "agencies",
        "topics",
        "search_terms",
        "document_types",
        "max_age_days",
        "base_url",
    ]
    assert metadata["federal_register_healthcare"].required_keys == []
    assert "Federal Register healthcare rules" in metadata[
        "federal_register_healthcare"
    ].description


def test_glama_mcp_stats_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "glama_mcp_stats"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["glama_mcp_stats"]
        adapter = get_adapter("glama_mcp_stats")

    assert adapter.name == "glama_mcp_stats"


def test_glama_mcp_stats_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "glama_mcp_stats"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"glama_mcp_stats"}
    assert metadata["glama_mcp_stats"].config_keys == [
        "stats_urls",
        "local_paths",
        "categories",
        "min_server_count",
        "max_items",
    ]
    assert metadata["glama_mcp_stats"].required_keys == []
    assert "Glama-style MCP ecosystem aggregate" in metadata[
        "glama_mcp_stats"
    ].description


def test_vscode_marketplace_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "vscode_marketplace"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["vscode_marketplace"]
        adapter = get_adapter("vscode_marketplace")

    assert adapter.name == "vscode_marketplace"


def test_vscode_marketplace_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "vscode_marketplace"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"vscode_marketplace"}
    assert metadata["vscode_marketplace"].config_keys == [
        "queries",
        "extensions",
        "extension_identifiers",
        "max_items",
        "categories",
        "tags",
    ]
    assert metadata["vscode_marketplace"].required_keys == []
    assert "Visual Studio Code Marketplace" in metadata[
        "vscode_marketplace"
    ].description


def test_pypi_download_trends_adapter_is_registered() -> None:
    with patch("max.config.MAX_ADAPTERS", "pypi_download_trends"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["pypi_download_trends"]
        adapter = get_adapter("pypi_download_trends")

    assert adapter.name == "pypi_download_trends"


def test_pypi_download_trends_adapter_metadata_documents_config_keys() -> None:
    with patch("max.config.MAX_ADAPTERS", "pypi_download_trends"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {"pypi_download_trends"}
    assert metadata["pypi_download_trends"].config_keys == [
        "packages",
        "period",
        "max_items",
        "min_downloads",
    ]
    assert metadata["pypi_download_trends"].required_keys == []
    assert "PyPI package download trend" in metadata[
        "pypi_download_trends"
    ].description
