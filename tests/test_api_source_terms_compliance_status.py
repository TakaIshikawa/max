from __future__ import annotations

import json

from max.api import source_terms_compliance_status_to_json


def test_source_terms_compliance_status_flags_mismatch_unreviewed_and_blockers() -> None:
    parsed = json.loads(source_terms_compliance_status_to_json({"sources": [{"source": "ok", "adapter": "a", "terms_version": "v1", "accepted_version": "v1", "last_reviewed_at": "2026-05-01"}, {"source": "mismatch", "terms_version": "v2", "accepted_version": "v1", "last_reviewed_at": "2026-05-01"}, {"source": "blocked", "blockers": ["z", "a"]}]}))

    assert [row["source"] for row in parsed["sources"]] == ["blocked", "mismatch", "ok"]
    assert parsed["sources"][0]["blockers"] == ["a", "z"]
    assert parsed["summary"]["blocked_count"] == 1
    assert parsed["summary"]["review_required_count"] == 1
