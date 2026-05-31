from __future__ import annotations

import json

from max.api.source_adapter_payload_freshness_status import source_adapter_payload_freshness_status_to_json


AS_OF = "2026-05-31T12:00:00Z"


def test_source_adapter_payload_freshness_status_fresh() -> None:
    parsed = json.loads(source_adapter_payload_freshness_status_to_json({"adapters": [{"adapter": "rss", "last_successful_fetch_at": "2026-05-31T11:45:00Z"}]}, as_of=AS_OF))

    assert parsed["summary"]["status"] == "fresh"
    assert parsed["adapters"][0]["last_successful_fetch_at"] == "2026-05-31T11:45:00Z"


def test_source_adapter_payload_freshness_status_stale() -> None:
    parsed = json.loads(source_adapter_payload_freshness_status_to_json({"max_age_minutes": 30, "adapters": [{"adapter": "rss", "last_successful_fetch_at": "2026-05-31T10:00:00Z"}]}, as_of=AS_OF))

    assert parsed["summary"]["status"] == "stale"
    assert parsed["summary"]["stale_payload_count"] == 1


def test_source_adapter_payload_freshness_status_never_fetched() -> None:
    parsed = json.loads(source_adapter_payload_freshness_status_to_json({"adapters": [{"adapter": "crm"}]}, as_of=AS_OF))

    assert parsed["adapters"][0]["status"] == "never_fetched"


def test_source_adapter_payload_freshness_status_mixed_orders_worst_first() -> None:
    parsed = json.loads(source_adapter_payload_freshness_status_to_json({"adapters": [{"adapter": "z", "last_successful_fetch_at": "2026-05-31T11:55:00Z"}, {"adapter": "a"}]}, as_of=AS_OF))

    assert parsed["summary"]["status"] == "never_fetched"
    assert [row["adapter"] for row in parsed["adapters"]] == ["a", "z"]
