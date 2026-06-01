from __future__ import annotations

import json

from max.api import source_adapter_stale_credential_status_to_json


def test_source_adapter_stale_credential_status_flags_stale_and_missing_validation() -> None:
    report = json.loads(source_adapter_stale_credential_status_to_json({"as_of": "2026-06-01T00:00:00Z", "max_age_days": 30, "adapters": [{"adapter": "healthy", "rotated_at": "2026-05-20T00:00:00Z", "last_validated_at": "2026-05-31T00:00:00Z"}, {"adapter": "stale", "rotated_at": "2026-04-01T00:00:00Z", "last_validated_at": "2026-05-31T00:00:00Z"}, {"adapter": "missing", "rotated_at": "2026-05-20T00:00:00Z"}]}))
    assert report["overall_status"] == "critical"
    assert report["stale_credential_count"] == 1
    assert report["missing_validation_count"] == 1
    assert [row["adapter"] for row in report["missing_validation_blockers"]] == ["missing", "stale"]


def test_source_adapter_stale_credential_status_empty_is_healthy() -> None:
    report = json.loads(source_adapter_stale_credential_status_to_json({"adapters": []}))
    assert report["overall_status"] == "healthy"
    assert report["recommended_actions"] == ["continue monitoring"]
