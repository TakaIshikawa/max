from __future__ import annotations

import json

from max.api import profile_yaml_anchor_status_to_json


def test_profile_yaml_anchor_counts_and_flattens_rows() -> None:
    parsed = json.loads(profile_yaml_anchor_status_to_json({"profiles": [
        {"profile": "ok", "anchors": ["base"], "aliases": ["base"]},
        {"profile": "dup", "duplicate_anchors": ["base"]},
        {"profile": "missing", "unresolved_aliases": ["shared"]},
        {"profile": "unused", "anchors": ["dead"], "aliases": []},
    ]}))
    assert parsed["schema_version"] == "max.api.profile_yaml_anchor_status.v1"
    assert parsed["summary"]["status"] == "critical"
    assert parsed["summary"]["unresolved_alias_count"] == 1
    assert parsed["summary"]["duplicate_anchor_count"] == 1
    assert parsed["summary"]["unused_anchor_count"] == 1
    assert [row["profile"] for row in parsed["profiles"][:2]] == ["dup", "missing"]
