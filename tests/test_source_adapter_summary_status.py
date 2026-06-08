from __future__ import annotations

import json

from max.api import source_adapter_summary_status_to_json as exported
from max.api.source_adapter_summary_status import source_adapter_summary_status_to_json


def test_source_adapter_summary_status_handles_empty_input() -> None:
    report = json.loads(source_adapter_summary_status_to_json([]))

    assert exported is source_adapter_summary_status_to_json
    assert report["summary"]["status"] == "idle"
    assert report["adapters"] == []


def test_source_adapter_summary_status_sorts_by_status_and_adapter() -> None:
    report = json.loads(source_adapter_summary_status_to_json([{"adapter": "b", "profile": "core", "fetched_count": 1}, {"adapter": "a", "profile": "core", "failed_count": 1}, {"adapter": "c", "profile": "core", "warning": True, "fetched_count": 1}]))

    assert [row["adapter"] for row in report["adapters"]] == ["a", "c", "b"]
    assert [row["status"] for row in report["adapters"]] == ["error", "warning", "healthy"]
    assert report["summary"]["status"] == "error"
