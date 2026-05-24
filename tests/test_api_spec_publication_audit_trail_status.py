from __future__ import annotations

import json

from max.api import spec_publication_audit_trail_status_to_json


def test_spec_publication_audit_trail_status_detects_complete_gapped_unpublished() -> None:
    parsed = json.loads(
        spec_publication_audit_trail_status_to_json(
            {
                "specs": [
                    {"id": "complete", "events": ["generated", "published"], "destinations": ["jira"]},
                    {"id": "gapped", "published": True, "destinations": ["linear"]},
                    {"id": "unpublished", "generated": True, "destinations": ["jira"]},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["specs"]] == ["unpublished", "gapped", "complete"]
    assert parsed["destination_totals"][0]["destination_id"] == "jira"
    assert parsed["summary"]["gapped_count"] == 1

