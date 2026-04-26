"""Tests for funding rounds source adapter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.funding_rounds import FundingRoundsAdapter
from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry
from max.sources.errors import SourceParseError
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_csv_fixture_rows_produce_funding_signals(tmp_path) -> None:
    fixture = tmp_path / "funding.csv"
    fixture.write_text(
        "company,amount,currency,round,investors,announced_date,sector,source_url,notes\n"
        "Acme AI,$12.5M,USD,Series A,\"Alpha Ventures, Beta Capital\","
        "2026-01-15,AI Infrastructure,https://example.com/acme,Expansion funding\n",
        encoding="utf-8",
    )
    adapter = FundingRoundsAdapter(config={"local_paths": [str(fixture)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id.startswith("funding_rounds:")
    assert signal.source_type == SignalSourceType.FUNDING
    assert signal.source_adapter == "funding_rounds"
    assert signal.title == "Acme AI raised $12.5M Series A"
    assert signal.url == "https://example.com/acme"
    assert signal.published_at is not None
    assert signal.metadata["company"] == "Acme AI"
    assert signal.metadata["amount"] == "$12.5M"
    assert signal.metadata["amount_usd"] == 12_500_000
    assert signal.metadata["currency"] == "USD"
    assert signal.metadata["round"] == "Series A"
    assert signal.metadata["investors"] == ["Alpha Ventures", "Beta Capital"]
    assert signal.metadata["announced_date"] == "2026-01-15"
    assert signal.metadata["sector"] == "AI Infrastructure"
    assert signal.metadata["source_url"] == "https://example.com/acme"
    assert signal.metadata["notes"] == "Expansion funding"
    assert signal.metadata["original_record"]["company"] == "Acme AI"
    assert signal.signal_role == "market"
    assert "funding-round" in signal.tags


@pytest.mark.asyncio
async def test_json_fixture_rows_parse_aliases(tmp_path) -> None:
    fixture = tmp_path / "funding.json"
    fixture.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "company_name": "BuildOps",
                        "raised_usd": 8_000_000,
                        "funding_round": "Seed",
                        "lead_investors": ["Construct Capital", "Field Fund"],
                        "industry": "Construction",
                        "announcement_url": "https://example.com/buildops",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = FundingRoundsAdapter(config={"local_paths": [str(fixture)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.metadata["company"] == "BuildOps"
    assert signal.metadata["amount_usd"] == 8_000_000
    assert signal.metadata["round"] == "Seed"
    assert signal.metadata["investors"] == ["Construct Capital", "Field Fund"]
    assert signal.metadata["sector"] == "Construction"
    assert signal.url == "https://example.com/buildops"


@pytest.mark.asyncio
async def test_jsonl_fixture_rows_parse_semicolon_investors(tmp_path) -> None:
    fixture = tmp_path / "funding.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "name": "ClinicFlow",
                "amount": "3 million",
                "stage": "Pre-seed",
                "investors": "Health Angels; Care Fund",
                "vertical": "Healthcare",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = FundingRoundsAdapter(config={"local_paths": [str(fixture)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["amount_usd"] == 3_000_000
    assert signals[0].metadata["round"] == "Pre-seed"
    assert signals[0].metadata["investors"] == ["Health Angels", "Care Fund"]
    assert signals[0].metadata["sector"] == "Healthcare"


@pytest.mark.asyncio
async def test_filters_by_min_amount_and_sector(tmp_path) -> None:
    fixture = tmp_path / "funding.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "company": "KeepCo",
                    "amount_usd": 20_000_000,
                    "round": "Series B",
                    "sector": "Fintech",
                },
                {
                    "company": "SmallCo",
                    "amount_usd": 2_000_000,
                    "round": "Seed",
                    "sector": "Fintech",
                },
                {
                    "company": "OtherCo",
                    "amount_usd": 30_000_000,
                    "round": "Series B",
                    "sector": "Healthcare",
                },
            ]
        ),
        encoding="utf-8",
    )
    adapter = FundingRoundsAdapter(
        config={
            "local_paths": [str(fixture)],
            "min_amount_usd": 10_000_000,
            "sectors": ["fintech"],
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["company"] == "KeepCo"


@pytest.mark.asyncio
async def test_dataset_url_rows_are_fetched_and_parsed() -> None:
    adapter = FundingRoundsAdapter(
        config={"dataset_urls": ["https://example.com/funding.jsonl"], "format": "jsonl"}
    )
    response = MagicMock()
    response.text = json.dumps(
        {
            "company": "RemoteRound",
            "amount": "$5M",
            "round": "Seed",
            "sector": "Devtools",
            "source_url": "https://example.com/remote-round",
        }
    )

    with patch(
        "max.sources.funding_rounds.fetch_with_retry",
        new=AsyncMock(return_value=response),
    ) as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert mock_fetch.call_args.args[0] == "https://example.com/funding.jsonl"
    assert len(signals) == 1
    assert signals[0].metadata["company"] == "RemoteRound"
    assert signals[0].metadata["amount_usd"] == 5_000_000


@pytest.mark.asyncio
async def test_malformed_json_raises_source_parse_error_with_adapter_name(tmp_path) -> None:
    fixture = tmp_path / "bad.json"
    fixture.write_text("{not json", encoding="utf-8")
    adapter = FundingRoundsAdapter(config={"local_paths": [str(fixture)]})

    with pytest.raises(SourceParseError, match="Malformed funding rounds JSON") as exc:
        await adapter.fetch(limit=10)

    assert exc.value.adapter_name == "funding_rounds"


@pytest.mark.asyncio
async def test_missing_required_row_fields_raise_source_parse_error(tmp_path) -> None:
    fixture = tmp_path / "missing.csv"
    fixture.write_text("company,amount,sector\nNoRound,1000000,Devtools\n", encoding="utf-8")
    adapter = FundingRoundsAdapter(config={"local_paths": [str(fixture)]})

    with pytest.raises(SourceParseError, match="company, amount, and round are required") as exc:
        await adapter.fetch(limit=10)

    assert exc.value.adapter_name == "funding_rounds"


def test_funding_rounds_adapter_is_registered_with_metadata() -> None:
    try:
        with patch("max.config.MAX_ADAPTERS", "funding_rounds"), \
             patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
            reload_registry()
            adapter = get_adapter("funding_rounds")
            metadata = get_adapter_metadata()
    finally:
        reload_registry()

    assert adapter.name == "funding_rounds"
    assert metadata["funding_rounds"].config_keys == [
        "local_paths",
        "dataset_urls",
        "format",
        "sectors",
        "min_amount_usd",
        "max_rows",
    ]
    assert metadata["funding_rounds"].required_keys == []
    assert "funding round datasets" in metadata["funding_rounds"].description
