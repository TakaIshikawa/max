"""Tests for publisher modules: file_writer and tact_api."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml

from max.publisher.file_writer import _slugify, write_tact_spec
from max.publisher.tact_api import DEFAULT_TACT_URL, push_to_tact
from max.types.tact_spec import (
    TactArchitecture,
    TactProduct,
    TactRequirement,
    TactSpec,
    TactTechStack,
)


# ---------------------------------------------------------------------------
# file_writer: write_tact_spec
# ---------------------------------------------------------------------------


def test_write_tact_spec_creates_files(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)

    assert (output_dir / "product.yaml").exists()
    assert (output_dir / "architecture.yaml").exists()
    assert (output_dir / "requirements").is_dir()

    req_files = list((output_dir / "requirements").glob("REQ-*.yaml"))
    assert len(req_files) == 1


def test_product_yaml_uses_camel_case(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)

    with open(output_dir / "product.yaml") as f:
        data = yaml.safe_load(f)

    assert "techStack" in data
    assert data["name"] == "mcp-test-framework"
    assert data["goals"][0]["successCriteria"] == "100% of MCP protocol methods covered"


def test_requirement_yaml_has_acceptance_criteria(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)

    req_files = list((output_dir / "requirements").glob("REQ-*.yaml"))
    with open(req_files[0]) as f:
        data = yaml.safe_load(f)

    assert "acceptanceCriteria" in data
    assert len(data["acceptanceCriteria"]) == 3
    assert data["priority"] == "critical"


def test_architecture_yaml_content(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)

    with open(output_dir / "architecture.yaml") as f:
        data = yaml.safe_load(f)

    assert data["invariants"] == ["All tests must be deterministic"]
    assert data["conventions"] == ["kebab-case file names"]


def test_multiple_requirements(tmp_path: Path) -> None:
    spec = TactSpec(
        buildable_unit_id="bu-multi",
        product=TactProduct(
            name="multi-req-product",
            vision="Testing multiple requirements",
            tech_stack=TactTechStack(languages=["Python"]),
        ),
        architecture=TactArchitecture(invariants=["deterministic"]),
        requirements=[
            TactRequirement(
                title="Auth system",
                description="Build auth",
                acceptance_criteria=["login works"],
            ),
            TactRequirement(
                title="Database layer",
                priority="high",
                description="Build DB layer",
                acceptance_criteria=["CRUD works"],
            ),
            TactRequirement(
                title="REST API endpoints",
                priority="critical",
                description="Build REST API",
                acceptance_criteria=["GET /health returns 200"],
            ),
        ],
    )

    output_dir = tmp_path / ".tact"
    write_tact_spec(spec, output_dir)

    req_dir = output_dir / "requirements"
    req_files = sorted(req_dir.glob("REQ-*.yaml"))
    assert len(req_files) == 3

    # Verify naming: REQ-001-auth-system.yaml, REQ-002-database-layer.yaml, ...
    assert req_files[0].name == "REQ-001-auth-system.yaml"
    assert req_files[1].name == "REQ-002-database-layer.yaml"
    assert req_files[2].name == "REQ-003-rest-api-endpoints.yaml"

    # Verify content of each requirement
    with open(req_files[0]) as f:
        data = yaml.safe_load(f)
    assert data["title"] == "Auth system"
    assert data["priority"] == "medium"  # default

    with open(req_files[2]) as f:
        data = yaml.safe_load(f)
    assert data["title"] == "REST API endpoints"
    assert data["priority"] == "critical"


def test_write_returns_output_dir(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    output_dir = tmp_path / ".tact"
    result = write_tact_spec(sample_tact_spec, output_dir)
    assert result == output_dir


def test_idempotent_write(tmp_path: Path, sample_tact_spec: TactSpec) -> None:
    """Calling write_tact_spec twice to the same dir should succeed (exist_ok=True)."""
    output_dir = tmp_path / ".tact"
    write_tact_spec(sample_tact_spec, output_dir)
    write_tact_spec(sample_tact_spec, output_dir)

    assert (output_dir / "product.yaml").exists()
    req_files = list((output_dir / "requirements").glob("REQ-*.yaml"))
    assert len(req_files) == 1


# ---------------------------------------------------------------------------
# file_writer: _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Hello World") == "hello-world"

    def test_special_characters(self) -> None:
        assert _slugify("Auth: JWT & OAuth2!") == "auth-jwt-oauth2"

    def test_consecutive_specials_collapse(self) -> None:
        assert _slugify("foo---bar   baz") == "foo-bar-baz"

    def test_leading_trailing_stripped(self) -> None:
        assert _slugify("  --hello-- ") == "hello"

    def test_max_length_truncation(self) -> None:
        long_text = "a" * 100
        result = _slugify(long_text)
        assert len(result) <= 40
        assert result == "a" * 40

    def test_max_length_does_not_leave_trailing_dash(self) -> None:
        # "abcdefghij-" at boundary should strip the trailing dash
        result = _slugify("abcdefghij klmnopqrst", max_length=11)
        assert not result.endswith("-")
        assert result == "abcdefghij"

    def test_custom_max_length(self) -> None:
        result = _slugify("hello world", max_length=5)
        assert result == "hello"

    def test_empty_string(self) -> None:
        assert _slugify("") == ""

    def test_only_special_chars(self) -> None:
        assert _slugify("!!!@@@###") == ""


# ---------------------------------------------------------------------------
# tact_api: push_to_tact
# ---------------------------------------------------------------------------


def _make_response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("GET", "http://test"))


def _ok_response() -> httpx.Response:
    return _make_response(200)


def _error_response(status: int = 500) -> httpx.Response:
    return _make_response(status)


@pytest.mark.asyncio
async def test_push_to_tact_success(sample_tact_spec: TactSpec) -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.put = AsyncMock(return_value=_ok_response())
    mock_client.post = AsyncMock(return_value=_ok_response())
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("max.publisher.tact_api.httpx.AsyncClient", return_value=mock_client):
        results = await push_to_tact(sample_tact_spec)

    assert results["product"] is True
    assert results["architecture"] is True
    assert results["requirements"] is True
    assert results["requirements_count"] == 1

    # Verify correct endpoints were called
    put_calls = mock_client.put.call_args_list
    assert len(put_calls) == 2
    assert put_calls[0].args[0] == f"{DEFAULT_TACT_URL}/product"
    assert put_calls[1].args[0] == f"{DEFAULT_TACT_URL}/architecture"

    post_calls = mock_client.post.call_args_list
    assert len(post_calls) == 1
    assert post_calls[0].args[0] == f"{DEFAULT_TACT_URL}/requirements"


@pytest.mark.asyncio
async def test_push_to_tact_custom_url(sample_tact_spec: TactSpec) -> None:
    custom_url = "http://tact.example.com/api/v2"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.put = AsyncMock(return_value=_ok_response())
    mock_client.post = AsyncMock(return_value=_ok_response())
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("max.publisher.tact_api.httpx.AsyncClient", return_value=mock_client):
        results = await push_to_tact(sample_tact_spec, tact_url=custom_url)

    assert results["product"] is True
    put_url = mock_client.put.call_args_list[0].args[0]
    assert put_url == f"{custom_url}/product"


@pytest.mark.asyncio
async def test_push_to_tact_connection_error(sample_tact_spec: TactSpec) -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.put = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("max.publisher.tact_api.httpx.AsyncClient", return_value=mock_client):
        results = await push_to_tact(sample_tact_spec)

    assert results["product"] is False
    assert results["architecture"] is False
    assert results["requirements"] is False
    assert results["requirements_count"] == 0


@pytest.mark.asyncio
async def test_push_to_tact_non_200_response(sample_tact_spec: TactSpec) -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.put = AsyncMock(return_value=_error_response(500))
    mock_client.post = AsyncMock(return_value=_error_response(422))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("max.publisher.tact_api.httpx.AsyncClient", return_value=mock_client):
        results = await push_to_tact(sample_tact_spec)

    # raise_for_status() raises on 5xx/4xx, caught by except Exception
    assert results["product"] is False
    assert results["architecture"] is False
    assert results["requirements"] is False


@pytest.mark.asyncio
async def test_push_to_tact_partial_failure(sample_tact_spec: TactSpec) -> None:
    """Product succeeds but architecture fails — verify independent handling."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.put = AsyncMock(
        side_effect=[_ok_response(), _error_response(503)],
    )
    mock_client.post = AsyncMock(return_value=_ok_response())
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("max.publisher.tact_api.httpx.AsyncClient", return_value=mock_client):
        results = await push_to_tact(sample_tact_spec)

    assert results["product"] is True
    assert results["architecture"] is False
    assert results["requirements"] is True
