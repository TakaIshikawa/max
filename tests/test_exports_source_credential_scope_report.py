from __future__ import annotations

from max.exports.source_credential_scope_report import generate_source_credential_scope_report, render_source_credential_scope_report_markdown


def test_source_credential_scope_missing_scopes_rank_above_excessive_scopes() -> None:
    report = generate_source_credential_scope_report(
        [{"source": "github", "environment": "prod", "scopes": ["read"]}, {"source": "slack", "environment": "dev", "scopes": ["chat", "admin"]}],
        {"github": ["read", "write"], "slack": ["chat"]},
        allowed_scopes_by_source={"github": ["read", "write"], "slack": ["chat"]},
    )

    assert [row["source"] for row in report["rows"]] == ["github", "slack"]
    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][1]["severity"] == "warn"
    assert "Grant missing required scopes" in render_source_credential_scope_report_markdown(report)
