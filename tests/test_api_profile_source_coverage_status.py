from __future__ import annotations

import json

from max.api.profile_source_coverage_status import profile_source_coverage_status_to_json


def test_profile_source_coverage_status_full_coverage() -> None:
    parsed = json.loads(profile_source_coverage_status_to_json({"required_sources": ["crm", "rss"], "sources": [{"source": "crm", "count": 5}, {"source": "rss", "count": 5}]}))

    assert parsed["summary"]["status"] == "healthy"


def test_profile_source_coverage_status_missing_source() -> None:
    parsed = json.loads(profile_source_coverage_status_to_json({"required_sources": ["crm", "rss"], "sources": [{"source": "crm", "count": 5}]}))

    assert parsed["summary"]["status"] == "missing_coverage"
    assert parsed["sources"][0]["source"] == "rss"


def test_profile_source_coverage_status_underrepresented_source() -> None:
    parsed = json.loads(profile_source_coverage_status_to_json({"minimum_share": 0.2, "required_sources": ["crm", "rss"], "sources": [{"source": "crm", "count": 9}, {"source": "rss", "count": 1}]}))

    assert parsed["summary"]["status"] == "low_coverage"


def test_profile_source_coverage_status_empty_profile() -> None:
    parsed = json.loads(profile_source_coverage_status_to_json({}))

    assert parsed["summary"]["status"] == "empty_profile"


def test_profile_source_coverage_status_deterministic_source_ordering() -> None:
    parsed = json.loads(profile_source_coverage_status_to_json({"required_sources": ["z", "a"], "sources": [{"source": "z", "count": 0}, {"source": "a", "count": 0}]}))

    assert [row["source"] for row in parsed["sources"]] == ["a", "z"]
