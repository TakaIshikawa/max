from __future__ import annotations

import json

from max.exports.publication_idempotency_collision_report import (
    build_publication_idempotency_collision_report,
    render_publication_idempotency_collision_report_json,
    render_publication_idempotency_collision_report_markdown,
)


def test_publication_idempotency_collision_report_groups_and_flags_collisions() -> None:
    report = build_publication_idempotency_collision_report(
        [
            {"destination": "slack", "idempotency_key": "unit-1", "external_id": "msg-1"},
            {"destination": "slack", "idempotency_key": "unit-1", "external_id": "msg-2"},
            {"destination": "slack", "idempotency_key": "unit-2", "external_id": "msg-3"},
            {"destination": "email", "idempotency_key": "unit-1", "external_id": "email-1"},
            {"destination": "email", "idempotency_key": "unit-1", "external_id": "email-1"},
        ]
    )

    assert report["summary"]["attempt_count"] == 5
    assert report["summary"]["idempotency_group_count"] == 3
    assert report["summary"]["collision_group_count"] == 1
    assert report["summary"]["duplicate_group_count"] == 1
    assert report["rows"][0]["destination"] == "slack"
    assert report["rows"][0]["idempotency_key"] == "unit-1"
    assert report["rows"][0]["collision_status"] == "collision"
    assert report["rows"][0]["external_ids"] == ["msg-1", "msg-2"]
    assert report["rows"][1]["duplicate_external_ids"] == ["email-1"]


def test_publication_idempotency_collision_renderers_include_summary_and_actions() -> None:
    report = build_publication_idempotency_collision_report(
        [
            {"destination": "api", "idempotency_key": "spec-42", "external_id": "pub-a"},
            {"destination": "api", "idempotency_key": "spec-42", "external_id": "pub-b"},
        ]
    )

    rendered = json.loads(render_publication_idempotency_collision_report_json(report))
    markdown = render_publication_idempotency_collision_report_markdown(report)

    assert rendered["summary"]["collision_group_count"] == 1
    assert rendered["collision_recommendations"][0]["recommended_action"].startswith("Quarantine")
    assert "## Summary" in markdown
    assert "Collision groups: 1" in markdown
    assert "Quarantine duplicate publications" in markdown
