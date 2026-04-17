"""Comprehensive tests for prior art detection module at src/max/analysis/prior_art.py."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from max.analysis.prior_art import (
    PriorArtMatch,
    PriorArtResult,
    _extract_keywords,
    _idea_text,
    _match_text,
    _resolve_github_token,
    _resolve_product_hunt_token,
    _search_github,
    _search_npm,
    _search_product_hunt,
    _search_pypi,
    _search_source,
    build_search_queries,
    check_prior_art,
    check_prior_art_batch,
    determine_status,
    score_matches,
    select_sources,
)
from max.types.buildable_unit import BuildableUnit, IdeationMode


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def sample_unit() -> BuildableUnit:
    """Create a sample BuildableUnit for testing."""
    return BuildableUnit(
        id="bu-test001",
        title="MCP Test Framework",
        one_liner="Standardized testing for MCP servers",
        category="cli_tool",
        ideation_mode=IdeationMode.DIRECT,
        problem="No standard way to test MCP servers with protocol validation",
        solution="A CLI tool that validates MCP server implementations",
        target_users="both",
        value_proposition="Reduce bugs in MCP servers by 80%",
        inspiring_insights=["ins-test001"],
        evidence_signals=["sig-test001"],
        tech_approach="TypeScript CLI with protocol-level validation",
        suggested_stack={"language": "typescript", "runtime": "node"},
        composability_notes="Integrates with CI/CD pipelines",
        status="evaluated",
        domain="devtools",
        prior_art_status="unchecked",
    )


@pytest.fixture
def python_unit() -> BuildableUnit:
    """Create a Python-based BuildableUnit for testing source selection."""
    return BuildableUnit(
        id="bu-py001",
        title="FastAPI Data Validator",
        one_liner="Schema validation for FastAPI endpoints",
        category="library",
        ideation_mode=IdeationMode.DIRECT,
        problem="Complex validation logic in FastAPI endpoints",
        solution="Declarative schema validation library",
        value_proposition="Reduce validation code by 50%",
        tech_approach="Python library with type hints",
        suggested_stack={"language": "python", "framework": "fastapi"},
        status="evaluated",
        domain="backend",
    )


@pytest.fixture
def app_unit() -> BuildableUnit:
    """Create an application BuildableUnit for testing source selection."""
    return BuildableUnit(
        id="bu-app001",
        title="Code Review Assistant",
        one_liner="AI-powered code review suggestions",
        category="application",
        ideation_mode=IdeationMode.DIRECT,
        problem="Manual code reviews are time-consuming",
        solution="Automated review assistant with AI suggestions",
        value_proposition="Save 40% of code review time",
        tech_approach="Web application with LLM integration",
        suggested_stack={"frontend": "react", "backend": "python"},
        status="evaluated",
        domain="devtools",
    )


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """Create a mock httpx.AsyncClient for testing."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


# ── 1. Query Construction Tests ───────────────────────────────────


class TestExtractKeywords:
    def test_removes_stop_words(self):
        """Stop words should be filtered out."""
        text = "the quick brown fox and the lazy dog"
        keywords = _extract_keywords(text)
        assert "the" not in keywords
        assert "and" not in keywords
        assert "quick" in keywords
        assert "brown" in keywords

    def test_removes_short_words(self):
        """Words with length <= 2 should be filtered."""
        text = "a to in cat dog elephant"
        keywords = _extract_keywords(text)
        assert "a" not in keywords
        assert "to" not in keywords
        assert "in" not in keywords
        assert "cat" in keywords
        assert "dog" in keywords

    def test_limits_to_max_tokens(self):
        """Should limit output to max_tokens."""
        text = "alpha bravo charlie delta echo foxtrot golf hotel"
        keywords = _extract_keywords(text, max_tokens=3)
        assert len(keywords) == 3

    def test_deduplicates_preserving_order(self):
        """Duplicate keywords should be removed, preserving first occurrence."""
        text = "testing testing framework framework library testing"
        keywords = _extract_keywords(text)
        assert keywords.count("testing") == 1
        assert keywords.count("framework") == 1
        assert keywords.index("testing") < keywords.index("framework")

    def test_handles_hyphenated_words(self):
        """Hyphenated words should be extracted as single tokens."""
        text = "test-driven development for cli-tools"
        keywords = _extract_keywords(text)
        assert "test-driven" in keywords
        assert "cli-tools" in keywords

    def test_handles_empty_text(self):
        """Empty text should return empty list."""
        assert _extract_keywords("") == []

    def test_handles_only_stop_words(self):
        """Text with only stop words should return empty list."""
        assert _extract_keywords("the and or but") == []

    def test_case_normalization(self):
        """Should convert to lowercase."""
        text = "TypeScript React FastAPI"
        keywords = _extract_keywords(text)
        assert "typescript" in keywords
        assert "react" in keywords
        assert "fastapi" in keywords


class TestBuildSearchQueries:
    def test_first_query_is_title(self, sample_unit):
        """First query should be the exact title."""
        queries = build_search_queries(sample_unit)
        assert queries[0] == "MCP Test Framework"

    def test_second_query_is_keywords(self, sample_unit):
        """Second query should be keywords from title + one_liner."""
        queries = build_search_queries(sample_unit)
        assert len(queries) == 2
        # Should combine title and one_liner
        assert "mcp" in queries[1].lower()
        assert "test" in queries[1].lower() or "testing" in queries[1].lower()

    def test_keyword_query_excludes_stop_words(self, sample_unit):
        """Keyword query should not contain stop words."""
        queries = build_search_queries(sample_unit)
        kw_query = queries[1].lower()
        stop_words = {"for", "the", "a", "an", "and", "or"}
        query_words = set(kw_query.split())
        assert not (query_words & stop_words), "Keyword query contains stop words"

    def test_handles_empty_one_liner(self):
        """Should handle units with empty one_liner."""
        unit = BuildableUnit(
            title="Test Title",
            one_liner="",
            category="library",
            problem="test",
            solution="test",
            value_proposition="test",
        )
        queries = build_search_queries(unit)
        assert len(queries) == 2
        assert queries[0] == "Test Title"


# ── 2. Source Selection Tests ─────────────────────────────────────


class TestSelectSources:
    def test_always_includes_github(self, sample_unit):
        """GitHub should always be included."""
        sources = select_sources(sample_unit)
        assert "github" in sources

    def test_cli_tool_includes_npm_and_pypi(self, sample_unit):
        """CLI tools should search npm and pypi."""
        sample_unit.category = "cli_tool"
        sources = select_sources(sample_unit)
        assert "npm" in sources
        assert "pypi" in sources

    def test_library_includes_npm_and_pypi(self, python_unit):
        """Libraries should search npm and pypi."""
        assert python_unit.category == "library"
        sources = select_sources(python_unit)
        assert "npm" in sources
        assert "pypi" in sources

    def test_mcp_server_includes_npm(self):
        """MCP servers should search npm."""
        unit = BuildableUnit(
            title="Test MCP",
            one_liner="test",
            category="mcp_server",
            problem="test",
            solution="test",
            value_proposition="test",
        )
        sources = select_sources(unit)
        assert "npm" in sources

    def test_application_includes_product_hunt(self, app_unit):
        """Applications should search Product Hunt."""
        assert app_unit.category == "application"
        sources = select_sources(app_unit)
        assert "product_hunt" in sources

    def test_feature_includes_product_hunt(self):
        """Features should search Product Hunt."""
        unit = BuildableUnit(
            title="Test Feature",
            one_liner="test",
            category="feature",
            problem="test",
            solution="test",
            value_proposition="test",
        )
        sources = select_sources(unit)
        assert "product_hunt" in sources

    def test_javascript_stack_adds_npm(self):
        """JavaScript indicators in stack should add npm."""
        unit = BuildableUnit(
            title="Test",
            one_liner="test",
            category="automation",
            problem="test",
            solution="test",
            value_proposition="test",
            suggested_stack={"language": "javascript"},
        )
        sources = select_sources(unit)
        assert "npm" in sources

    def test_typescript_stack_adds_npm(self, sample_unit):
        """TypeScript stack should add npm."""
        assert sample_unit.suggested_stack["language"] == "typescript"
        sources = select_sources(sample_unit)
        assert "npm" in sources

    def test_python_stack_adds_pypi(self, python_unit):
        """Python stack should add pypi."""
        assert python_unit.suggested_stack["language"] == "python"
        sources = select_sources(python_unit)
        assert "pypi" in sources

    def test_react_stack_adds_npm(self):
        """React in stack should add npm."""
        unit = BuildableUnit(
            title="Test",
            one_liner="test",
            category="automation",
            problem="test",
            solution="test",
            value_proposition="test",
            suggested_stack={"frontend": "react"},
        )
        sources = select_sources(unit)
        assert "npm" in sources

    def test_case_insensitive_stack_detection(self):
        """Stack detection should be case insensitive."""
        unit = BuildableUnit(
            title="Test",
            one_liner="test",
            category="automation",
            problem="test",
            solution="test",
            value_proposition="test",
            suggested_stack={"language": "TypeScript"},
        )
        sources = select_sources(unit)
        assert "npm" in sources


# ── 3. Token Resolution Tests ─────────────────────────────────────


class TestResolveGithubToken:
    def test_returns_env_var_if_present(self):
        """Should prefer GITHUB_TOKEN env var."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token-123"}):
            token = _resolve_github_token()
            assert token == "test-token-123"

    def test_tries_vault_if_no_env_var(self):
        """Should try vault if env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("max.analysis.prior_art.subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="vault-token-456\n",
                )
                token = _resolve_github_token()
                assert token == "vault-token-456"
                mock_run.assert_called_once_with(
                    ["vault", "get", "github/token"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

    def test_returns_none_if_vault_fails(self):
        """Should return None if vault command fails."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("max.analysis.prior_art.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1, stdout="")
                token = _resolve_github_token()
                assert token is None

    def test_returns_none_if_vault_throws(self):
        """Should return None if vault command throws exception."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("max.analysis.prior_art.subprocess.run") as mock_run:
                mock_run.side_effect = Exception("vault not found")
                token = _resolve_github_token()
                assert token is None

    def test_strips_whitespace_from_vault_output(self):
        """Should strip whitespace from vault output."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("max.analysis.prior_art.subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="  vault-token  \n",
                )
                token = _resolve_github_token()
                assert token == "vault-token"


class TestResolveProductHuntToken:
    def test_returns_env_var_if_present(self):
        """Should prefer PRODUCT_HUNT_TOKEN env var."""
        with patch.dict(os.environ, {"PRODUCT_HUNT_TOKEN": "ph-token-123"}):
            token = _resolve_product_hunt_token()
            assert token == "ph-token-123"

    def test_tries_vault_if_no_env_var(self):
        """Should try vault if env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("max.analysis.prior_art.subprocess.run") as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="ph-vault-token\n",
                )
                token = _resolve_product_hunt_token()
                assert token == "ph-vault-token"
                mock_run.assert_called_once_with(
                    ["vault", "get", "product_hunt/token"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

    def test_returns_none_if_vault_fails(self):
        """Should return None if vault command fails."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("max.analysis.prior_art.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1, stdout="")
                token = _resolve_product_hunt_token()
                assert token is None


# ── 4. Search Function Tests ──────────────────────────────────────


class TestSearchGithub:
    @pytest.mark.asyncio
    async def test_successful_search(self, mock_http_client):
        """Should parse GitHub API response correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "full_name": "test/repo1",
                    "html_url": "https://github.com/test/repo1",
                    "description": "Test repository 1",
                    "stargazers_count": 100,
                    "forks_count": 20,
                    "language": "TypeScript",
                    "updated_at": "2024-01-01T00:00:00Z",
                },
                {
                    "full_name": "test/repo2",
                    "html_url": "https://github.com/test/repo2",
                    "description": None,  # Test null description
                    "stargazers_count": 50,
                    "forks_count": 10,
                    "language": "Python",
                    "updated_at": "2024-01-02T00:00:00Z",
                },
            ]
        }
        mock_http_client.get.return_value = mock_response

        matches = await _search_github("test query", mock_http_client)

        assert len(matches) == 2
        assert matches[0].source == "github"
        assert matches[0].title == "test/repo1"
        assert matches[0].url == "https://github.com/test/repo1"
        assert matches[0].description == "Test repository 1"
        assert matches[0].match_signals["stars"] == 100
        assert matches[0].match_signals["language"] == "TypeScript"
        assert matches[0].search_query == "test query"

        # Check null description handling
        assert matches[1].description == ""

    @pytest.mark.asyncio
    async def test_handles_api_error(self, mock_http_client):
        """Should return empty list on API error."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_http_client.get.return_value = mock_response

        matches = await _search_github("test query", mock_http_client)

        assert matches == []

    @pytest.mark.asyncio
    async def test_handles_exception(self, mock_http_client):
        """Should return empty list on exception."""
        mock_http_client.get.side_effect = Exception("Network error")

        matches = await _search_github("test query", mock_http_client)

        assert matches == []

    @pytest.mark.asyncio
    async def test_limits_to_5_results(self, mock_http_client):
        """Should limit results to 5 items."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "full_name": f"test/repo{i}",
                    "html_url": f"https://github.com/test/repo{i}",
                    "description": f"Repo {i}",
                    "stargazers_count": i * 10,
                    "forks_count": i,
                    "language": "Python",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
                for i in range(10)
            ]
        }
        mock_http_client.get.return_value = mock_response

        matches = await _search_github("test", mock_http_client)

        assert len(matches) == 5

    @pytest.mark.asyncio
    async def test_uses_extra_headers(self, mock_http_client):
        """Should pass extra_headers to the request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_http_client.get.return_value = mock_response

        extra_headers = {"Authorization": "Bearer test-token"}
        await _search_github("test", mock_http_client, extra_headers=extra_headers)

        mock_http_client.get.assert_called_once()
        call_kwargs = mock_http_client.get.call_args[1]
        assert call_kwargs["headers"] == extra_headers


class TestSearchNpm:
    @pytest.mark.asyncio
    async def test_successful_search(self, mock_http_client):
        """Should parse npm registry response correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "objects": [
                {
                    "package": {
                        "name": "test-package",
                        "description": "A test package",
                        "version": "1.2.3",
                        "links": {"npm": "https://www.npmjs.com/package/test-package"},
                    },
                    "score": {
                        "detail": {
                            "quality": 0.95,
                            "popularity": 0.85,
                            "maintenance": 0.90,
                        }
                    },
                }
            ]
        }
        mock_http_client.get.return_value = mock_response

        matches = await _search_npm("test query", mock_http_client)

        assert len(matches) == 1
        assert matches[0].source == "npm"
        assert matches[0].title == "test-package"
        assert matches[0].url == "https://www.npmjs.com/package/test-package"
        assert matches[0].description == "A test package"
        assert matches[0].match_signals["version"] == "1.2.3"
        assert matches[0].match_signals["score_detail"]["quality"] == 0.95

    @pytest.mark.asyncio
    async def test_handles_missing_npm_link(self, mock_http_client):
        """Should construct npm URL if links.npm is missing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "objects": [
                {
                    "package": {
                        "name": "test-pkg",
                        "description": "Test",
                        "version": "1.0.0",
                        "links": {},
                    },
                    "score": {"detail": {}},
                }
            ]
        }
        mock_http_client.get.return_value = mock_response

        matches = await _search_npm("test", mock_http_client)

        assert matches[0].url == "https://www.npmjs.com/package/test-pkg"

    @pytest.mark.asyncio
    async def test_handles_api_error(self, mock_http_client):
        """Should return empty list on API error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_http_client.get.return_value = mock_response

        matches = await _search_npm("test", mock_http_client)

        assert matches == []


class TestSearchPypi:
    @pytest.mark.asyncio
    async def test_successful_search(self, mock_http_client):
        """Should parse PyPI search results and fetch metadata."""
        # The function makes several calls - let's track them
        call_log = []

        # Mock the search response with package names
        search_response = Mock()
        search_response.status_code = 200
        search_response.text = """
        <a class="package-snippet" href="/project/test-package/">
        <a class="package-snippet" href="/project/another-pkg/">
        """

        # Mock metadata responses
        meta1_response = Mock()
        meta1_response.status_code = 200
        meta1_response.json.return_value = {
            "info": {
                "name": "test-package",
                "summary": "A test package",
                "package_url": "https://pypi.org/project/test-package/",
                "version": "2.0.0",
                "author": "Test Author",
                "requires_python": ">=3.8",
            }
        }

        meta2_response = Mock()
        meta2_response.status_code = 200
        meta2_response.json.return_value = {
            "info": {
                "name": "another-pkg",
                "summary": "Another package",
                "package_url": "https://pypi.org/project/another-pkg/",
                "version": "1.0.0",
                "author": "Someone",
                "requires_python": ">=3.9",
            }
        }

        def get_side_effect(url, **kwargs):
            call_log.append(url)
            # The implementation tries /search/ with params, then /simple/, then /search/ again
            if "/pypi/test-package/json" in url:
                return meta1_response
            elif "/pypi/another-pkg/json" in url:
                return meta2_response
            elif "/search/" in url:
                # Return the search results page
                return search_response
            elif "/simple/" in url:
                # Simple API endpoint - must return 200 for the function to continue
                simple_mock = Mock()
                simple_mock.status_code = 200
                return simple_mock
            else:
                mock = Mock()
                mock.status_code = 404
                return mock

        mock_http_client.get.side_effect = get_side_effect

        matches = await _search_pypi("test query", mock_http_client)

        assert len(matches) == 2
        assert matches[0].source == "pypi"
        assert matches[0].title == "test-package"
        assert matches[0].match_signals["version"] == "2.0.0"
        assert matches[0].match_signals["author"] == "Test Author"

    @pytest.mark.asyncio
    async def test_handles_search_error(self, mock_http_client):
        """Should return empty list if search fails."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_http_client.get.return_value = mock_response

        matches = await _search_pypi("test", mock_http_client)

        assert matches == []

    @pytest.mark.asyncio
    async def test_handles_no_packages_found(self, mock_http_client):
        """Should return empty list if no packages match pattern."""
        search_response = Mock()
        search_response.status_code = 200
        search_response.text = "<html>No results</html>"
        mock_http_client.get.return_value = search_response

        matches = await _search_pypi("nonexistent", mock_http_client)

        assert matches == []


class TestSearchProductHunt:
    @pytest.mark.asyncio
    async def test_successful_search(self, mock_http_client):
        """Should parse Product Hunt GraphQL response correctly."""
        with patch("max.analysis.prior_art._resolve_product_hunt_token") as mock_token:
            mock_token.return_value = "test-ph-token"

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "posts": {
                        "edges": [
                            {
                                "node": {
                                    "id": "post1",
                                    "name": "Test Product",
                                    "tagline": "A test product",
                                    "url": "https://www.producthunt.com/posts/test",
                                    "votesCount": 150,
                                    "website": "https://testproduct.com",
                                }
                            }
                        ]
                    }
                }
            }
            mock_http_client.post.return_value = mock_response

            matches = await _search_product_hunt("test", mock_http_client)

            assert len(matches) == 1
            assert matches[0].source == "product_hunt"
            assert matches[0].title == "Test Product"
            assert matches[0].description == "A test product"
            assert matches[0].match_signals["votes"] == 150

    @pytest.mark.asyncio
    async def test_returns_empty_if_no_token(self, mock_http_client):
        """Should return empty list if no Product Hunt token available."""
        with patch("max.analysis.prior_art._resolve_product_hunt_token") as mock_token:
            mock_token.return_value = None

            matches = await _search_product_hunt("test", mock_http_client)

            assert matches == []
            mock_http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_api_error(self, mock_http_client):
        """Should return empty list on API error."""
        with patch("max.analysis.prior_art._resolve_product_hunt_token") as mock_token:
            mock_token.return_value = "test-token"

            mock_response = Mock()
            mock_response.status_code = 401
            mock_http_client.post.return_value = mock_response

            matches = await _search_product_hunt("test", mock_http_client)

            assert matches == []


# ── 5. Scoring Tests ──────────────────────────────────────────────


class TestIdeaText:
    def test_combines_title_oneliner_problem(self, sample_unit):
        """Should combine title, one_liner, and first 200 chars of problem."""
        text = _idea_text(sample_unit)
        assert "MCP Test Framework" in text
        assert "Standardized testing for MCP servers" in text
        assert "No standard way to test MCP servers" in text

    def test_truncates_problem_to_200_chars(self):
        """Should truncate problem to 200 characters."""
        unit = BuildableUnit(
            title="Test",
            one_liner="test",
            category="library",
            problem="x" * 500,
            solution="test",
            value_proposition="test",
        )
        text = _idea_text(unit)
        # Problem should be truncated to 200 chars
        assert text.count("x") == 200


class TestMatchText:
    def test_combines_title_and_description(self):
        """Should combine title and first 200 chars of description."""
        match = PriorArtMatch(
            source="github",
            title="test-repo",
            url="https://github.com/test/repo",
            description="A test repository for testing",
        )
        text = _match_text(match)
        assert "test-repo" in text
        assert "A test repository for testing" in text

    def test_truncates_description_to_200_chars(self):
        """Should truncate description to 200 characters."""
        match = PriorArtMatch(
            source="github",
            title="test",
            url="https://test.com",
            description="y" * 500,
        )
        text = _match_text(match)
        assert text.count("y") == 200


class TestScoreMatches:
    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_filters_below_threshold(self, mock_sim, mock_embed, sample_unit):
        """Should filter out matches with similarity below 0.65."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.50  # Below threshold

        matches = [
            PriorArtMatch(
                source="github",
                title="test",
                url="https://test.com",
                description="test",
            )
        ]

        scored = score_matches(sample_unit, matches)
        assert len(scored) == 0

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_keeps_above_threshold(self, mock_sim, mock_embed, sample_unit):
        """Should keep matches with similarity >= 0.65."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.80

        matches = [
            PriorArtMatch(
                source="github",
                title="test",
                url="https://test.com",
                description="test",
            )
        ]

        scored = score_matches(sample_unit, matches)
        assert len(scored) == 1
        assert scored[0].relevance_score == 0.80

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_sorts_by_relevance_descending(self, mock_sim, mock_embed, sample_unit):
        """Should sort matches by relevance score in descending order."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.side_effect = [0.70, 0.90, 0.75]

        matches = [
            PriorArtMatch(source="github", title="low", url="https://1.com", description="1"),
            PriorArtMatch(source="github", title="high", url="https://2.com", description="2"),
            PriorArtMatch(source="github", title="mid", url="https://3.com", description="3"),
        ]

        scored = score_matches(sample_unit, matches)
        assert scored[0].title == "high"
        assert scored[0].relevance_score == 0.90
        assert scored[1].title == "mid"
        assert scored[1].relevance_score == 0.75
        assert scored[2].title == "low"
        assert scored[2].relevance_score == 0.70

    def test_empty_matches(self, sample_unit):
        """Should handle empty match list."""
        scored = score_matches(sample_unit, [])
        assert scored == []

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_rounds_score_to_3_decimals(self, mock_sim, mock_embed, sample_unit):
        """Should round similarity score to 3 decimal places."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.876543

        matches = [
            PriorArtMatch(source="github", title="test", url="https://t.com", description="t")
        ]

        scored = score_matches(sample_unit, matches)
        assert scored[0].relevance_score == 0.877


class TestDetermineStatus:
    def test_no_matches_returns_clear(self):
        """Empty matches should return 'clear'."""
        assert determine_status([]) == "clear"

    def test_score_below_065_returns_clear(self):
        """Scores below 0.65 should return 'clear'."""
        matches = [
            PriorArtMatch(
                source="github",
                title="test",
                url="https://t.com",
                description="t",
                relevance_score=0.60,
            )
        ]
        assert determine_status(matches) == "clear"

    def test_score_065_to_084_returns_weak_match(self):
        """Scores 0.65-0.84 should return 'weak_match'."""
        matches = [
            PriorArtMatch(
                source="github",
                title="test",
                url="https://t.com",
                description="t",
                relevance_score=0.75,
            )
        ]
        assert determine_status(matches) == "weak_match"

    def test_score_085_and_above_returns_strong_match(self):
        """Scores >= 0.85 should return 'strong_match'."""
        matches = [
            PriorArtMatch(
                source="github",
                title="test",
                url="https://t.com",
                description="t",
                relevance_score=0.90,
            )
        ]
        assert determine_status(matches) == "strong_match"

    def test_uses_max_score_from_multiple_matches(self):
        """Should use maximum score when multiple matches present."""
        matches = [
            PriorArtMatch(
                source="github",
                title="low",
                url="https://1.com",
                description="1",
                relevance_score=0.70,
            ),
            PriorArtMatch(
                source="github",
                title="high",
                url="https://2.com",
                description="2",
                relevance_score=0.90,
            ),
        ]
        assert determine_status(matches) == "strong_match"

    def test_boundary_065(self):
        """Score exactly 0.65 should be 'weak_match'."""
        matches = [
            PriorArtMatch(
                source="github",
                title="test",
                url="https://t.com",
                description="t",
                relevance_score=0.65,
            )
        ]
        assert determine_status(matches) == "weak_match"

    def test_boundary_085(self):
        """Score exactly 0.85 should be 'strong_match'."""
        matches = [
            PriorArtMatch(
                source="github",
                title="test",
                url="https://t.com",
                description="t",
                relevance_score=0.85,
            )
        ]
        assert determine_status(matches) == "strong_match"


# ── 6. Orchestration Tests ────────────────────────────────────────


class TestSearchSource:
    @pytest.mark.asyncio
    async def test_searches_with_rate_limiting(self, mock_http_client):
        """Should execute searches with rate limiting."""
        semaphore = asyncio.Semaphore(2)

        async def mock_search_fn(query, client, **kwargs):
            return [
                PriorArtMatch(
                    source="github",
                    title=f"test-{query}",
                    url=f"https://t.com/{query}",
                    description="t",
                )
            ]

        # Patch the dictionary entry directly
        with patch.dict("max.analysis.prior_art._SEARCH_FNS", {"github": mock_search_fn}):
            matches = await _search_source(
                "github",
                ["query1", "query2"],
                mock_http_client,
                semaphore,
                0.0,  # No delay for testing
            )

            assert len(matches) == 2
            assert matches[0].url == "https://t.com/query1"
            assert matches[1].url == "https://t.com/query2"

    @pytest.mark.asyncio
    async def test_deduplicates_by_url(self, mock_http_client):
        """Should deduplicate matches by URL."""
        semaphore = asyncio.Semaphore(2)

        async def mock_search_side_effect(query, client, **kwargs):
            if query == "query1":
                return [
                    PriorArtMatch(
                        source="github",
                        title="test1",
                        url="https://same.com",
                        description="first",
                    )
                ]
            else:
                return [
                    PriorArtMatch(
                        source="github",
                        title="test2",
                        url="https://same.com",
                        description="second",
                    )
                ]

        with patch.dict("max.analysis.prior_art._SEARCH_FNS", {"github": mock_search_side_effect}):
            matches = await _search_source(
                "github",
                ["query1", "query2"],
                mock_http_client,
                semaphore,
                0.0,
            )

            # Should only keep first occurrence
            assert len(matches) == 1
            assert matches[0].title == "test1"

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_source(self, mock_http_client):
        """Should return empty list for unknown source."""
        semaphore = asyncio.Semaphore(1)

        matches = await _search_source(
            "unknown_source",
            ["query"],
            mock_http_client,
            semaphore,
            0.0,
        )

        assert matches == []

    @pytest.mark.asyncio
    async def test_passes_kwargs_to_search_function(self, mock_http_client):
        """Should pass additional kwargs to search function."""
        semaphore = asyncio.Semaphore(1)
        extra_headers = {"Authorization": "Bearer test"}

        call_args = []

        async def mock_search_fn(query, client, **kwargs):
            call_args.append((query, client, kwargs))
            return []

        with patch.dict("max.analysis.prior_art._SEARCH_FNS", {"github": mock_search_fn}):
            await _search_source(
                "github",
                ["query"],
                mock_http_client,
                semaphore,
                0.0,
                extra_headers=extra_headers,
            )

            assert len(call_args) == 1
            assert call_args[0][0] == "query"
            assert call_args[0][1] is mock_http_client
            assert call_args[0][2] == {"extra_headers": extra_headers}


class TestCheckPriorArtBatch:
    @pytest.mark.asyncio
    async def test_dry_run_returns_unchecked_status(self, sample_unit):
        """Dry run should return results with 'unchecked' status."""
        results = await check_prior_art_batch([sample_unit], dry_run=True)

        assert len(results) == 1
        assert results[0].buildable_unit_id == "bu-test001"
        assert results[0].status == "unchecked"
        assert results[0].matches == []

    @pytest.mark.asyncio
    async def test_searches_selected_sources(self, sample_unit):
        """Should search all selected sources."""
        with patch("max.analysis.prior_art._search_source") as mock_search:
            mock_search.return_value = []
            with patch("max.analysis.prior_art.score_matches") as mock_score:
                mock_score.return_value = []

                results = await check_prior_art_batch([sample_unit], dry_run=False)

                # sample_unit is cli_tool with typescript, should search github, npm, pypi
                assert mock_search.call_count == 3

    @pytest.mark.asyncio
    async def test_scores_and_filters_matches(self, sample_unit):
        """Should score matches and determine status."""
        with patch("max.analysis.prior_art._search_source") as mock_search:
            mock_search.return_value = [
                PriorArtMatch(
                    source="github",
                    title="similar-project",
                    url="https://github.com/test/similar",
                    description="Very similar project",
                    relevance_score=0.0,
                )
            ]
            with patch("max.analysis.prior_art.score_matches") as mock_score:
                mock_score.return_value = [
                    PriorArtMatch(
                        source="github",
                        title="similar-project",
                        url="https://github.com/test/similar",
                        description="Very similar project",
                        relevance_score=0.92,
                    )
                ]

                results = await check_prior_art_batch([sample_unit], dry_run=False)

                assert len(results) == 1
                assert results[0].status == "strong_match"
                assert len(results[0].matches) == 1
                assert results[0].matches[0].relevance_score == 0.92

    @pytest.mark.asyncio
    async def test_processes_multiple_units(self, sample_unit, python_unit):
        """Should process multiple units sequentially."""
        with patch("max.analysis.prior_art._search_source") as mock_search:
            mock_search.return_value = []
            with patch("max.analysis.prior_art.score_matches") as mock_score:
                mock_score.return_value = []

                results = await check_prior_art_batch([sample_unit, python_unit], dry_run=False)

                assert len(results) == 2
                assert results[0].buildable_unit_id == "bu-test001"
                assert results[1].buildable_unit_id == "bu-py001"


class TestCheckPriorArt:
    def test_sync_wrapper(self, sample_unit):
        """Sync wrapper should call async version."""
        with patch("max.analysis.prior_art.check_prior_art_batch") as mock_batch:
            mock_batch.return_value = [
                PriorArtResult(
                    buildable_unit_id="bu-test001",
                    matches=[],
                    status="clear",
                )
            ]

            results = check_prior_art([sample_unit], dry_run=True)

            assert len(results) == 1
            mock_batch.assert_called_once()


# ── 7. Edge Cases and Integration ─────────────────────────────────


class TestEdgeCases:
    def test_single_element_list(self, sample_unit):
        """Should handle single-element list."""
        with patch("max.analysis.prior_art.check_prior_art_batch") as mock_batch:
            mock_batch.return_value = [
                PriorArtResult(
                    buildable_unit_id="bu-test001",
                    matches=[],
                    status="clear",
                )
            ]

            results = check_prior_art([sample_unit])

            assert len(results) == 1

    def test_empty_input_list(self):
        """Should handle empty input list."""
        results = check_prior_art([])
        assert results == []

    def test_unit_with_minimal_fields(self):
        """Should handle unit with only required fields."""
        minimal_unit = BuildableUnit(
            title="Minimal",
            one_liner="test",
            category="library",
            problem="test",
            solution="test",
            value_proposition="test",
        )

        queries = build_search_queries(minimal_unit)
        assert len(queries) == 2

        sources = select_sources(minimal_unit)
        assert "github" in sources

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_identical_matches(self, mock_sim, mock_embed):
        """Should handle identical similarity scores."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.80

        unit = BuildableUnit(
            title="Test",
            one_liner="test",
            category="library",
            problem="test",
            solution="test",
            value_proposition="test",
        )

        matches = [
            PriorArtMatch(source="github", title="match1", url="https://1.com", description="1"),
            PriorArtMatch(source="github", title="match2", url="https://2.com", description="2"),
            PriorArtMatch(source="github", title="match3", url="https://3.com", description="3"),
        ]

        scored = score_matches(unit, matches)

        # All should have same score
        assert all(m.relevance_score == 0.80 for m in scored)
        assert len(scored) == 3

    def test_unit_with_empty_suggested_stack(self):
        """Should handle unit with empty suggested_stack."""
        unit = BuildableUnit(
            title="Test",
            one_liner="test",
            category="automation",
            problem="test",
            solution="test",
            value_proposition="test",
            suggested_stack={},
        )

        sources = select_sources(unit)
        # Should only include github (no language-specific sources)
        assert sources == ["github"]

    def test_long_problem_description(self):
        """Should handle very long problem descriptions."""
        long_problem = "x" * 10000
        unit = BuildableUnit(
            title="Test",
            one_liner="test",
            category="library",
            problem=long_problem,
            solution="test",
            value_proposition="test",
        )

        text = _idea_text(unit)
        # Problem should be truncated to 200 chars in the idea text
        assert len(text.split(maxsplit=2)[2]) <= 200 + 100  # Allow some buffer for title/one_liner
