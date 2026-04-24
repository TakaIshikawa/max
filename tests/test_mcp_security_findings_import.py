"""Tests for importing MCP security scanner findings."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store


def _client(db_path: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _finding(**overrides):
    finding = {
        "scanner": "mcp-shield",
        "server_name": "filesystem-server",
        "package_name": "@modelcontextprotocol/server-filesystem",
        "package_version": "1.2.3",
        "severity": "high",
        "finding_type": "prompt_injection",
        "title": "Untrusted prompt reaches filesystem tool",
        "description": "The MCP server exposes file write operations without validating prompt origin.",
        "evidence_url": "https://scanner.example/findings/fs-1",
        "discovered_at": "2026-04-24T10:30:00Z",
        "remediation": "Require an explicit allowlist before tool execution.",
    }
    finding.update(overrides)
    return finding


def test_import_mcp_security_findings_reports_partial_failure_and_preserves_metadata(
    tmp_path,
) -> None:
    path = str(tmp_path / "mcp_security.db")
    Store(db_path=path, wal_mode=True).close()
    client = _client(path)

    response = client.post(
        "/api/v1/security/mcp-findings/import",
        json={
            "findings": [
                _finding(),
                _finding(
                    title="Second valid finding",
                    evidence_url="https://scanner.example/findings/fs-2",
                    severity="critical",
                    finding_type="unsafe_tool_permissions",
                ),
                _finding(description=""),
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["inserted_count"] == 2
    assert payload["duplicate_count"] == 0
    assert payload["error_count"] == 1
    assert payload["results"][0]["signal_id"].startswith("sig-")
    assert payload["results"][1]["signal_id"].startswith("sig-")
    assert "missing required field: description" in payload["results"][2]["error"]

    list_response = client.get(
        "/api/v1/signals?source_adapter=mcp_security_import&source_type=security"
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 2

    by_url = {item["url"]: item for item in items}
    item = by_url["https://scanner.example/findings/fs-1"]
    assert item["source_adapter"] == "mcp_security_import"
    assert item["source_type"] == "security"
    assert item["signal_role"] == "problem"
    assert {
        "security",
        "mcp",
        "high",
        "severity:high",
        "prompt-injection",
        "finding:prompt-injection",
    } <= set(item["tags"])
    assert item["metadata"] == {
        "scanner": "mcp-shield",
        "server_name": "filesystem-server",
        "package_name": "@modelcontextprotocol/server-filesystem",
        "package_version": "1.2.3",
        "severity": "high",
        "finding_type": "prompt_injection",
        "remediation": "Require an explicit allowlist before tool execution.",
        "evidence_url": "https://scanner.example/findings/fs-1",
        "discovered_at": "2026-04-24T10:30:00+00:00",
        "signal_role": "problem",
    }


def test_import_mcp_security_findings_reports_duplicates_from_store_insertion(
    tmp_path,
) -> None:
    path = str(tmp_path / "mcp_security_dupes.db")
    Store(db_path=path, wal_mode=True).close()
    client = _client(path)

    first = client.post(
        "/api/v1/security/mcp-findings/import",
        json={"findings": [_finding()]},
    )
    second = client.post(
        "/api/v1/security/mcp-findings/import",
        json={"findings": [_finding(title="Duplicate title")]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["results"][0]["signal_id"]
    second_payload = second.json()
    assert second_payload["inserted_count"] == 0
    assert second_payload["duplicate_count"] == 1
    assert second_payload["error_count"] == 0
    assert second_payload["results"][0]["duplicate_id"] == first_id

    list_response = client.get("/api/v1/signals?source_adapter=mcp_security_import")
    assert list_response.json()["pagination"]["total_count"] == 1
