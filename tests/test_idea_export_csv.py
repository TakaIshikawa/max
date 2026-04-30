from __future__ import annotations

import csv
from io import StringIO

from max.analysis.export import IDEA_CSV_EXPORT_FIELDS, render_idea_export


def test_render_idea_export_csv_uses_stable_header_and_counts_evidence() -> None:
    csv_text = render_idea_export(
        [
            {
                "id": "bu-001",
                "title": "First idea",
                "domain": "devtools",
                "status": "evaluated",
                "category": "cli_tool",
                "recommendation": "yes",
                "evaluation_score": 88.0,
                "source_adapters": ["reddit", "hackernews", "reddit"],
                "evidence_signal_ids": ["sig-1", "sig-2"],
                "created_at": "2026-04-29T01:02:03+00:00",
                "updated_at": "2026-04-30T01:02:03+00:00",
            }
        ],
        fmt="csv",
    )

    reader = csv.DictReader(StringIO(csv_text))
    assert reader.fieldnames == list(IDEA_CSV_EXPORT_FIELDS)
    rows = list(reader)
    assert rows == [
        {
            "id": "bu-001",
            "title": "First idea",
            "domain": "devtools",
            "status": "evaluated",
            "category": "cli_tool",
            "recommendation": "yes",
            "overall_score": "88.0",
            "source_adapters": "hackernews, reddit, reddit",
            "evidence_signal_count": "2",
            "created_at": "2026-04-29T01:02:03+00:00",
            "updated_at": "2026-04-30T01:02:03+00:00",
        }
    ]


def test_render_idea_export_csv_escapes_text_and_preserves_row_order() -> None:
    csv_text = render_idea_export(
        [
            {
                "id": "bu-001",
                "title": "Comma, idea",
                "domain": "devtools",
                "status": "draft",
                "category": "application",
                "recommendation": "maybe",
                "overall_score": 70.5,
                "source_adapters": ["zeta", "alpha"],
                "evidence_signal_ids": ["sig-1"],
            },
            {
                "id": "bu-002",
                "title": "Multiline\nidea",
                "domain": "ops",
                "status": "evaluated",
                "category": "automation",
                "recommendation": "yes",
                "overall_score": 91.0,
                "source_adapters": ["beta"],
                "evidence_signal_ids": [],
            },
        ],
        fmt="csv",
    )

    assert '"Comma, idea"' in csv_text
    assert '"Multiline\nidea"' in csv_text

    rows = list(csv.DictReader(StringIO(csv_text)))
    assert [row["id"] for row in rows] == ["bu-001", "bu-002"]
    assert rows[0]["source_adapters"] == "alpha, zeta"
    assert rows[1]["title"] == "Multiline\nidea"
