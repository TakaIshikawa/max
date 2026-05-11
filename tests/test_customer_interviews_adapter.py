"""Tests for the customer interviews import adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from max.imports.customer_interviews_adapter import (
    CustomerInterviewsAdapter,
    parse_csv_interviews,
    parse_json_interviews,
)
from max.types.signal import SignalSourceType


CSV_DATA = """\
participant,title,segment,problem,current_solution,wtp,verbatim,confidence
Ada,VP Product,Enterprise,Manual onboarding takes too long,Spreadsheets,$500/mo,"We lose a week every rollout",0.8
Missing,,,,,,,
Ben,Founder,SMB,,Zapier,,The integrations are brittle,70%
"""


def test_parse_csv_interviews_accepts_aliases_and_skips_empty_rows() -> None:
    rows = parse_csv_interviews(CSV_DATA, interview_source="discovery")

    assert len(rows) == 2
    assert rows[0]["interviewee"] == "Ada"
    assert rows[0]["role"] == "VP Product"
    assert rows[0]["company_segment"] == "Enterprise"
    assert rows[0]["pain"] == "Manual onboarding takes too long"
    assert rows[1]["quote"] == "The integrations are brittle"


def test_parse_json_interviews_accepts_wrapped_data_and_invalid_input() -> None:
    rows = parse_json_interviews(
        """{"interviews":[{"customer":"Rae","persona":"Ops","challenge":"No audit trail"}]}"""
    )

    assert rows[0]["interviewee"] == "Rae"
    assert rows[0]["role"] == "Ops"
    assert rows[0]["pain"] == "No audit trail"
    assert parse_json_interviews("not json") == []


@pytest.mark.asyncio
async def test_fetch_from_inline_data_without_filesystem_access() -> None:
    adapter = CustomerInterviewsAdapter(
        config={
            "data": [
                {
                    "name": "Ada",
                    "role": "VP Product",
                    "segment": "Enterprise",
                    "pain_point": "Manual onboarding takes too long",
                    "workaround": "Spreadsheets",
                    "willingness_to_pay": "$500/mo",
                    "quote": "We lose a week every rollout",
                    "evidence_strength": "0.8",
                }
            ],
            "interview_source": "discovery",
            "default_domain": "example.com",
            "tags": ["pricing", "onboarding"],
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.SURVEY
    assert signal.source_adapter == "customer_interviews"
    assert "Manual onboarding" in signal.title
    assert "Pain: Manual onboarding takes too long" in signal.content
    assert "Workaround: Spreadsheets" in signal.content
    assert {"customer_interview", "discovery", "pricing", "onboarding"}.issubset(signal.tags)
    assert signal.credibility == 0.8
    assert signal.url == "example.com"
    assert signal.metadata["role"] == "VP Product"
    assert signal.metadata["company_segment"] == "Enterprise"
    assert signal.metadata["quote"] == "We lose a week every rollout"


@pytest.mark.asyncio
async def test_fetch_from_csv_file_and_respects_limit(tmp_path: Path) -> None:
    path = tmp_path / "interviews.csv"
    path.write_text(CSV_DATA, encoding="utf-8")
    adapter = CustomerInterviewsAdapter(config={"files": [str(path)], "interview_source": "calls"})

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["interview_source"] == "calls"


@pytest.mark.asyncio
async def test_fetch_handles_bad_files_and_zero_limit(tmp_path: Path) -> None:
    adapter = CustomerInterviewsAdapter(
        config={
            "files": [str(tmp_path / "missing.csv")],
            "data": [{"role": "No evidence"}],
        }
    )

    assert await adapter.fetch(limit=0) == []
    assert await adapter.fetch(limit=10) == []
