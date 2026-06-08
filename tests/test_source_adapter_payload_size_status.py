from __future__ import annotations

import json

from max.api.source_adapter_payload_size_status import source_adapter_payload_size_status_to_json


def test_source_adapter_payload_size_status_healthy_and_idle() -> None:
    report = json.loads(source_adapter_payload_size_status_to_json({"adapters": [{"adapter": "rss", "source": "blog", "payload_bytes": 1024, "record_count": 2}, {"adapter": "empty", "source": "queue"}]}))

    assert report["adapters"][0]["status"] == "healthy"
    assert report["adapters"][0]["bytes_per_record"] == 512
    assert report["adapters"][1]["status"] == "idle"


def test_source_adapter_payload_size_status_warning_and_critical() -> None:
    report = json.loads(source_adapter_payload_size_status_to_json({"adapters": [{"adapter": "warn", "source": "a", "payload_bytes": 600000, "record_count": 10}, {"adapter": "crit", "source": "b", "payload_bytes": 2000000, "record_count": 10}]}))

    assert [row["status"] for row in report["adapters"]] == ["critical", "warning"]
    assert report["summary"]["status"] == "critical"


def test_source_adapter_payload_size_status_deterministic_ordering() -> None:
    report = json.loads(source_adapter_payload_size_status_to_json({"adapters": [{"adapter": "b", "source": "z", "payload_bytes": 600000}, {"adapter": "a", "source": "z", "payload_bytes": 600000}]}))

    assert [row["adapter"] for row in report["adapters"]] == ["a", "b"]
