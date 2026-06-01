from __future__ import annotations

import json

from max.api import profile_secret_reference_status_to_json


def test_profile_secret_reference_status_flags_missing_plaintext_and_stale_without_secret_values() -> None:
    report = json.loads(
        profile_secret_reference_status_to_json(
            {
                "stale_days": 30,
                "secrets": [
                    {"profile": "blocked", "secret_name": "TOKEN", "required": True, "resolved": False},
                    {"profile": "plain", "secret_name": "API", "env_var": "secret=raw", "plaintext": True},
                    {"profile": "stale", "secret_name": "KEY", "env_var": "KEY", "version_created_at": "2026-04-01T00:00:00Z"},
                    {"profile": "ok", "secret_name": "OK", "env_var": "OK", "version_created_at": "2026-05-30T00:00:00Z"},
                ],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["status"] == "critical"
    assert report["summary"]["blocked_count"] == 1
    assert report["summary"]["plaintext_count"] == 1
    assert report["summary"]["stale_count"] == 1
    assert report["secret_references"][1]["env_var"] == "[redacted]"


def test_profile_secret_reference_status_flattens_profile_secret_references() -> None:
    report = json.loads(
        profile_secret_reference_status_to_json(
            {
                "profiles": [
                    {
                        "profile": "prod",
                        "secret_references": [
                            {"secret_name": "TOKEN", "env_var": "TOKEN", "resolved": True}
                        ],
                    }
                ]
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["status"] == "healthy"
    assert report["secret_references"][0]["profile"] == "prod"
    assert report["summary"]["resolved_count"] == 1
