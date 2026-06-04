from __future__ import annotations

import json

from max.api import profile_target_user_coverage_status_to_json


def test_complete_coverage_is_ok() -> None:
    report = json.loads(profile_target_user_coverage_status_to_json({"profiles": [{"profile": "p", "target_users": ["admin", "buyer"], "idea_target_users": ["buyer", "admin"]}]}))
    assert report["profile_rows"][0]["status"] == "ok"


def test_uncovered_personas_are_critical() -> None:
    report = json.loads(profile_target_user_coverage_status_to_json({"rows": [{"profile": "p", "target_users": ["admin", "buyer"], "idea_target_users": ["admin"]}]}))
    assert report["profile_rows"][0]["uncovered_target_users"] == ["buyer"]


def test_overconcentration_warns() -> None:
    report = json.loads(profile_target_user_coverage_status_to_json({"items": [{"profile": "p", "target_users": ["admin", "buyer"], "idea_target_users": ["admin", "admin", "admin", "buyer"]}]}))
    assert report["profile_rows"][0]["status"] == "warning"


def test_empty_target_user_config_is_insufficient_data() -> None:
    report = json.loads(profile_target_user_coverage_status_to_json({"profiles": [{"profile": "p"}]}))
    assert report["profile_rows"][0]["status"] == "insufficient_data"


def test_malformed_idea_persona_fields_do_not_cover_targets() -> None:
    report = json.loads(profile_target_user_coverage_status_to_json({"profiles": [{"profile": "p", "target_users": ["admin"], "idea_personas": {"bad": "shape"}}]}))
    assert report["profile_rows"][0]["coverage_ratio"] == 0.0
