from __future__ import annotations

import json

from max.api import source_payload_size_status_to_json


def test_source_payload_size_status_flags_oversized_payloads() -> None:
    report = json.loads(source_payload_size_status_to_json({"sources": [{"source": "small", "adapter": "rss", "payload_bytes": 1024, "max_payload_bytes": 2048, "record_count": 2}, {"source": "large", "adapter": "api", "payload_bytes": 4096, "max_payload_bytes": 2048, "record_count": 4}]}))

    assert report["rows"][0]["source"] == "large"
    assert report["rows"][0]["payload_kib"] == 4.0
    assert report["rows"][0]["bytes_per_record"] == 1024.0
    assert report["rows"][0]["severity"] == "critical"
    assert report["summary"]["total_payload_bytes"] == 5120
