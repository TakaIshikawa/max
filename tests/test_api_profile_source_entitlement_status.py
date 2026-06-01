from __future__ import annotations

import json

from max.api import profile_source_entitlement_status_to_json


def test_profile_source_entitlements_aggregate_missing_and_restricted() -> None:
    parsed = json.loads(profile_source_entitlement_status_to_json({"available_entitlements": ["github", "slack"], "restricted_sources": ["slack"], "profiles": [
        {"profile": "all", "requested_sources": ["github"]},
        {"profile": "missing", "requested_sources": ["jira"]},
        {"profile": "restricted", "requested_sources": ["slack"]},
    ]}))
    assert parsed["summary"]["status"] == "critical"
    assert parsed["profiles"][0]["profile"] == "missing"
    assert parsed["profiles"][0]["missingEntitlements"] == ["jira"]
    assert any(row["restrictedSources"] == ["slack"] for row in parsed["profiles"])
