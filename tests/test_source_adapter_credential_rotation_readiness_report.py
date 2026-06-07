from __future__ import annotations

from max.exports import generate_source_adapter_credential_rotation_readiness_report


def test_source_adapter_credential_rotation_readiness_sorts_and_flags_statuses() -> None:
    report = generate_source_adapter_credential_rotation_readiness_report(
        [
            {"adapter": "github", "credential_type": "oauth", "owner": "DevEx", "rotated_at": "2026-06-01", "rotation_interval_days": 60},
            {"adapter": "reddit", "credential_type": "api_key", "owner": "Growth", "next_rotation_due_at": "2026-06-10", "rotation_interval_days": 30},
            {"adapter": "hn", "credential_type": "token", "rotated_at": "2026-01-01", "rotation_interval_days": 30},
        ],
        as_of="2026-06-07",
        due_soon_days=7,
    )

    assert [row["status"] for row in report["rows"]] == ["blocked", "due_soon", "ready"]
    assert report["rows"][0]["adapter"] == "hn"
    assert report["rows"][1]["days_until_due"] == 3
    assert report["summary"]["credential_count"] == 3


def test_source_adapter_credential_rotation_readiness_empty() -> None:
    assert generate_source_adapter_credential_rotation_readiness_report([])["rows"] == []
