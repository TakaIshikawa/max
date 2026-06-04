from __future__ import annotations

import json

from max.api import spec_generation_template_miss_status_to_json


def test_spec_generation_template_miss_status_handles_strings_lists_and_common_block() -> None:
    report = json.loads(spec_generation_template_miss_status_to_json({"specs": [{"spec_id": "ok", "generation_status": "complete"}, {"spec_id": "warn", "missing_variables": "owner", "retry_count": 3}, {"unit_id": "crit", "missing_blocks": ["risk", "owner"], "generation_status": "failed"}, {"spec_id": "crit2", "missing_blocks": "risk", "generation_status": "failed"}]}))

    assert [row["spec_id"] for row in report["spec_rows"]][:2] == ["crit", "crit2"]
    assert report["spec_rows"][0]["status"] == "critical"
    assert report["summary"]["most_common_missing_block"] == "risk"
