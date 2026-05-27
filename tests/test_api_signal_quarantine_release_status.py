from __future__ import annotations

import json

from max.api.signal_quarantine_release_status import signal_quarantine_release_status_to_json


def test_signal_quarantine_release_status_marks_eligible_and_summarizes() -> None:
    report = json.loads(signal_quarantine_release_status_to_json({"signals": [{"signal_id": "s2", "source": "github", "reason": "pii", "review_state": "pending", "blocking_checks": ["privacy"]}, {"signal_id": "s1", "source": "github", "reason": "pii", "review_state": "approved", "blocking_checks": []}, {"signal_id": "s3", "source": "jira", "reason": "spam", "review_state": "approved", "blocking_checks": ["quality"]}]}))

    assert [row["signal_id"] for row in report["rows"]] == ["s1", "s2", "s3"]
    assert report["rows"][0]["release_eligible"] is True
    assert report["summary"]["quarantined_count"] == 3
    assert report["summary"]["release_eligible_count"] == 1
    assert report["summary"]["blocked_count"] == 2
    assert report["summary"]["reasons"] == ["pii", "spam"]
