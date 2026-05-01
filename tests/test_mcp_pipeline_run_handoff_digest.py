"""Tests for pipeline run handoff digests exposed through MCP."""

from __future__ import annotations

from max.analysis.pipeline_run_handoff_digest import (
    PipelineRunHandoffDigestNotFound,
    SCHEMA_VERSION,
)
from max.server import mcp_tools
from max.server.mcp_tools import get_pipeline_run_handoff_digest, set_store_factory


class FakeStore:
    def __init__(self, label: str = "fake-store") -> None:
        self.label = label

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


def _digest(run_id: str = "run-handoff-mcp") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.pipeline_run_handoff_digest",
        "run": {"id": run_id, "status": "completed"},
        "summary": {"idea_count": 2, "next_action_count": 1},
        "warnings": [],
        "next_actions": ["Review the top recommendation."],
    }


def test_get_pipeline_run_handoff_digest_returns_payload(monkeypatch) -> None:
    fake_store = FakeStore()
    set_store_factory(lambda: fake_store)
    calls = []

    def fake_build(store, *, run_id):
        calls.append((store, run_id))
        return _digest(run_id)

    monkeypatch.setattr(mcp_tools, "build_pipeline_run_handoff_digest", fake_build)

    try:
        result = get_pipeline_run_handoff_digest("run-handoff-mcp")
    finally:
        set_store_factory(mcp_tools._default_store_factory)

    assert calls == [(fake_store, "run-handoff-mcp")]
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.pipeline_run_handoff_digest"
    assert result["run"]["id"] == "run-handoff-mcp"
    assert result["summary"]["idea_count"] == 2


def test_get_pipeline_run_handoff_digest_returns_markdown(monkeypatch) -> None:
    fake_store = FakeStore()
    digest = _digest()
    set_store_factory(lambda: fake_store)

    monkeypatch.setattr(
        mcp_tools,
        "build_pipeline_run_handoff_digest",
        lambda store, *, run_id: digest,
    )
    monkeypatch.setattr(
        mcp_tools,
        "render_pipeline_run_handoff_digest",
        lambda payload, *, fmt: "# Pipeline Run Handoff Digest: run-handoff-mcp\n",
    )

    try:
        result = get_pipeline_run_handoff_digest(
            "run-handoff-mcp",
            format="markdown",
        )
    finally:
        set_store_factory(mcp_tools._default_store_factory)

    assert result == {
        "id": "run-handoff-mcp",
        "format": "markdown",
        "markdown": "# Pipeline Run Handoff Digest: run-handoff-mcp\n",
    }


def test_get_pipeline_run_handoff_digest_missing_run_returns_mcp_error(monkeypatch) -> None:
    set_store_factory(lambda: FakeStore())

    def fake_build(store, *, run_id):
        raise PipelineRunHandoffDigestNotFound(run_id)

    monkeypatch.setattr(mcp_tools, "build_pipeline_run_handoff_digest", fake_build)

    try:
        result = get_pipeline_run_handoff_digest("run-missing")
    finally:
        set_store_factory(mcp_tools._default_store_factory)

    assert result == {
        "error": "Pipeline run ID not found",
        "code": 404,
        "details": {
            "resource_type": "pipeline_run",
            "resource_id": "run-missing",
        },
    }


def test_get_pipeline_run_handoff_digest_invalid_format() -> None:
    result = get_pipeline_run_handoff_digest("run-handoff-mcp", format="yaml")

    assert result["error"] == "Unsupported pipeline run handoff digest format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_get_pipeline_run_handoff_digest_generation_failure(monkeypatch) -> None:
    set_store_factory(lambda: FakeStore())

    def fake_build(store, *, run_id):
        raise RuntimeError("digest unavailable")

    monkeypatch.setattr(mcp_tools, "build_pipeline_run_handoff_digest", fake_build)

    try:
        result = get_pipeline_run_handoff_digest("run-handoff-mcp")
    finally:
        set_store_factory(mcp_tools._default_store_factory)

    assert result["error"] == "Failed to generate pipeline run handoff digest"
    assert result["code"] == 502
    assert result["details"]["service"] == "pipeline_run_handoff_digest"
    assert result["details"]["reason"] == "digest unavailable"


def test_create_mcp_server_registers_pipeline_run_handoff_digest_tool(monkeypatch) -> None:
    class FakeMCP:
        latest = None

        def __init__(self, name):
            self.name = name
            self.tools = []
            self.resources = {}
            FakeMCP.latest = self

        def tool(self, fn):
            self.tools.append(fn.__name__)
            return fn

        def resource(self, uri):
            def decorator(fn):
                self.resources[uri] = fn.__name__
                return fn

            return decorator

    monkeypatch.setattr(mcp_tools, "FastMCP", FakeMCP)

    mcp_tools.create_mcp_server()

    assert "get_pipeline_run_handoff_digest" in FakeMCP.latest.tools
