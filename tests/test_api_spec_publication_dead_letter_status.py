from __future__ import annotations

import json

from max.api import spec_publication_dead_letter_status_to_json


def test_spec_publication_dead_letter_groups_and_normalizes_unknowns() -> None:
    report = json.loads(spec_publication_dead_letter_status_to_json({"specs": [{"spec_id": "s1", "destination": "jira", "failed_attempts": 3, "last_error": "Timeout: upstream", "retryable": True}, {"spec_id": "s2", "destination": "slack"}]}))

    assert report["retryable_count"] == 1
    assert report["terminal_count"] == 1
    assert {"error_family": "timeout", "count": 1} in report["error_families"]
    assert {"error_family": "unknown", "count": 1} in report["error_families"]
