from __future__ import annotations

from max.api import insight_evidence_chain_to_json


def test_api_exports_insight_evidence_chain_renderer() -> None:
    assert callable(insight_evidence_chain_to_json)
