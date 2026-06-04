from __future__ import annotations

import json

from max.api import embedding_similarity_outlier_status_to_json


def test_embedding_similarity_outlier_status_clamps_and_sorts() -> None:
    report = json.loads(embedding_similarity_outlier_status_to_json({"items": [{"item_id": "ok", "nearest_similarity": 0.5}, {"item_id": "dup", "nearest_similarity": 2}, {"item_id": "low", "nearest_similarity": -1, "created_at": "2026-01-01"}]}))

    assert [row["item_id"] for row in report["embedding_rows"]] == ["low", "dup", "ok"]
    assert report["embedding_rows"][0]["nearest_similarity"] == 0.0
    assert report["embedding_rows"][1]["nearest_similarity"] == 1.0
    assert report["summary"]["worst_item_id"] == "low"
