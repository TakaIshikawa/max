from __future__ import annotations

import json

from max.api import source_adapter_payload_size_summary_to_json as exported
from max.api.source_adapter_payload_size_summary import source_adapter_payload_size_summary_to_json


def test_source_adapter_payload_size_summary_handles_empty_input() -> None:
    report = json.loads(source_adapter_payload_size_summary_to_json([]))

    assert exported is source_adapter_payload_size_summary_to_json
    assert report["summary"]["status"] == "ok"
    assert report["summary"]["payload_count"] == 0
    assert report["adapters"] == []


def test_source_adapter_payload_size_summary_rolls_up_payloads() -> None:
    report = json.loads(source_adapter_payload_size_summary_to_json([{"adapter": "rss", "payload_bytes": 100, "record_count": 2}, {"adapter": "crm", "bytes": 50, "records": 1}, {"adapter": "rss", "payload_bytes": 150, "record_count": 3}]))

    assert report["adapters"] == ["crm", "rss"]
    assert report["summary"]["adapter_count"] == 2
    assert report["summary"]["payload_count"] == 3
    assert report["summary"]["total_bytes"] == 300
    assert report["summary"]["bytes_per_record"] == 50
