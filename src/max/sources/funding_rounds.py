"""Funding rounds dataset adapter."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ROWS = 250
_SUPPORTED_FORMATS = {"csv", "json", "jsonl"}

_COMPANY_KEYS = ("company", "company_name", "name", "organization", "startup")
_AMOUNT_KEYS = ("amount_usd", "amount", "funding_amount", "raised_usd", "raise_amount")
_CURRENCY_KEYS = ("currency", "currency_code")
_ROUND_KEYS = ("round", "round_type", "funding_round", "stage")
_INVESTOR_KEYS = ("investors", "lead_investors", "investor_names", "backers")
_ANNOUNCED_KEYS = ("announced_date", "announced_on", "funding_date", "date")
_SECTOR_KEYS = ("sector", "industry", "category", "vertical")
_SOURCE_URL_KEYS = ("source_url", "url", "announcement_url", "article_url", "evidence_url")
_NOTES_KEYS = ("notes", "note", "description", "summary", "details")


class FundingRoundsAdapter(SourceAdapter):
    """Read structured funding round datasets as market validation signals."""

    @property
    def name(self) -> str:
        return "funding_rounds"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FUNDING.value

    @property
    def local_paths(self) -> list[str]:
        return _string_list(self._config.get("local_paths"))

    @property
    def dataset_urls(self) -> list[str]:
        return _string_list(self._config.get("dataset_urls"))

    @property
    def format(self) -> str | None:
        configured = self._config.get("format")
        if not isinstance(configured, str) or not configured.strip():
            return None
        normalized = configured.strip().lower()
        return normalized if normalized in _SUPPORTED_FORMATS else None

    @property
    def sectors(self) -> list[str]:
        return _string_list(self._config.get("sectors"))

    @property
    def min_amount_usd(self) -> float:
        amount = _parse_amount(self._config.get("min_amount_usd"))
        return amount or 0.0

    @property
    def max_rows(self) -> int:
        value = self._config.get("max_rows", _DEFAULT_MAX_ROWS)
        if isinstance(value, bool):
            return _DEFAULT_MAX_ROWS
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_ROWS

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        row_limit = min(limit, self.max_rows)
        signals: list[Signal] = []
        seen: set[str] = set()

        for local_path in self.local_paths:
            if len(signals) >= row_limit:
                break
            text = self._read_local_path(local_path)
            self._append_signals(
                signals,
                text,
                source_label=local_path,
                source_url=_file_url(local_path),
                limit=row_limit,
                seen=seen,
            )

        if len(signals) < row_limit and self.dataset_urls:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for dataset_url in self.dataset_urls:
                    if len(signals) >= row_limit:
                        break
                    text = await self._fetch_dataset_url(dataset_url, client)
                    if text is None:
                        continue
                    self._append_signals(
                        signals,
                        text,
                        source_label=dataset_url,
                        source_url=dataset_url,
                        limit=row_limit,
                        seen=seen,
                    )

        return signals[:row_limit]

    def _read_local_path(self, local_path: str) -> str:
        try:
            return Path(local_path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SourceParseError(
                f"Unable to read funding rounds dataset: {local_path}",
                adapter_name=self.name,
            ) from exc

    async def _fetch_dataset_url(self, dataset_url: str, client: httpx.AsyncClient) -> str | None:
        try:
            response = await fetch_with_retry(dataset_url, client, adapter_name=self.name)
        except AdapterFetchError as exc:
            logger.warning("%s: failed to fetch dataset URL %s: %s", self.name, dataset_url, exc)
            return None
        except Exception as exc:
            logger.warning("%s: failed to fetch dataset URL %s: %s", self.name, dataset_url, exc)
            return None
        return response.text

    def _append_signals(
        self,
        signals: list[Signal],
        text: str,
        *,
        source_label: str,
        source_url: str,
        limit: int,
        seen: set[str],
    ) -> None:
        for row_number, row in enumerate(
            _parse_rows(text, source_label=source_label, dataset_format=self.format),
            start=1,
        ):
            if len(signals) >= limit:
                break
            signal = _signal_from_row(
                row,
                adapter_name=self.name,
                source_url=source_url,
                row_number=row_number,
                sectors=self.sectors,
                min_amount_usd=self.min_amount_usd,
            )
            if signal is None or signal.id in seen:
                continue
            seen.add(signal.id)
            signals.append(signal)


def _parse_rows(text: str, *, source_label: str, dataset_format: str | None) -> list[dict[str, Any]]:
    resolved_format = dataset_format or _infer_format(source_label)
    if resolved_format == "csv":
        return _parse_csv(text, source_label)
    if resolved_format == "jsonl":
        return _parse_jsonl(text, source_label)
    if resolved_format == "json":
        return _extract_json_rows(_parse_json(text, source_label), source_label)
    raise SourceParseError(
        f"Unsupported funding rounds dataset format for: {source_label}",
        adapter_name="funding_rounds",
    )


def _parse_csv(text: str, source_label: str) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as exc:
        raise SourceParseError(
            f"Malformed funding rounds CSV: {source_label}",
            adapter_name="funding_rounds",
        ) from exc

    if not reader.fieldnames:
        raise SourceParseError(
            f"Funding rounds CSV is missing a header row: {source_label}",
            adapter_name="funding_rounds",
        )
    return [dict(row) for row in rows]


def _parse_json(text: str, source_label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParseError(
            f"Malformed funding rounds JSON: {source_label}",
            adapter_name="funding_rounds",
        ) from exc


def _parse_jsonl(text: str, source_label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SourceParseError(
                f"Malformed funding rounds JSONL row {line_number}: {source_label}",
                adapter_name="funding_rounds",
            ) from exc
        if not isinstance(item, dict):
            raise SourceParseError(
                f"Funding rounds JSONL row {line_number} is not an object: {source_label}",
                adapter_name="funding_rounds",
            )
        rows.append(item)
    return rows


def _extract_json_rows(data: Any, source_label: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = None
        for key in ("rows", "results", "items", "data", "funding_rounds", "rounds"):
            value = data.get(key)
            if isinstance(value, list):
                rows = value
                break
        if rows is None:
            rows = [data]
    else:
        raise SourceParseError(
            f"Funding rounds JSON must contain an object or array: {source_label}",
            adapter_name="funding_rounds",
        )

    if not all(isinstance(item, dict) for item in rows):
        raise SourceParseError(
            f"Funding rounds JSON rows must be objects: {source_label}",
            adapter_name="funding_rounds",
        )
    return list(rows)


def _signal_from_row(
    row: dict[str, Any],
    *,
    adapter_name: str,
    source_url: str,
    row_number: int,
    sectors: list[str],
    min_amount_usd: float,
) -> Signal | None:
    company = _first_text(row, _COMPANY_KEYS)
    amount_raw = _first_present(row, _AMOUNT_KEYS)
    amount_usd = _parse_amount(amount_raw)
    round_name = _first_text(row, _ROUND_KEYS)
    sector = _first_text(row, _SECTOR_KEYS)

    if not company or amount_usd is None or not round_name:
        raise SourceParseError(
            f"Malformed funding rounds row {row_number}: company, amount, and round are required",
            adapter_name=adapter_name,
        )

    if amount_usd < min_amount_usd:
        return None
    if sectors and (not sector or sector.lower() not in {item.lower() for item in sectors}):
        return None

    currency = _first_text(row, _CURRENCY_KEYS) or _infer_currency(amount_raw)
    investors = _parse_investors(_first_present(row, _INVESTOR_KEYS))
    announced_date_text = _first_text(row, _ANNOUNCED_KEYS)
    published_at = _parse_date(announced_date_text)
    funding_url = _first_text(row, _SOURCE_URL_KEYS)
    notes = _first_text(row, _NOTES_KEYS)
    signal_url = funding_url or source_url

    title = f"{company} raised {_format_money(amount_usd, currency)} {round_name}"
    content_parts = [
        f"Company: {company}",
        f"Amount: {_format_money(amount_usd, currency)}",
        f"Round: {round_name}",
    ]
    if investors:
        content_parts.append(f"Investors: {', '.join(investors)}")
    if sector:
        content_parts.append(f"Sector: {sector}")
    if announced_date_text:
        content_parts.append(f"Announced: {announced_date_text}")
    if notes:
        content_parts.append(f"Notes: {notes}")

    metadata = {
        "company": company,
        "amount": amount_raw,
        "amount_usd": amount_usd,
        "currency": currency,
        "round": round_name,
        "investors": investors,
        "announced_date": announced_date_text,
        "sector": sector,
        "source_url": funding_url,
        "notes": notes,
        "original_record": dict(row),
        "signal_role": "market",
    }

    return Signal(
        id=_stable_id(adapter_name, source_url, row),
        source_type=SignalSourceType.FUNDING,
        source_adapter=adapter_name,
        title=title[:240],
        content="\n".join(content_parts)[:1000],
        url=signal_url,
        published_at=published_at,
        tags=_build_tags(round_name, sector),
        credibility=_credibility(amount_usd),
        metadata=metadata,
    )


def _stable_id(adapter_name: str, source_url: str, row: dict[str, Any]) -> str:
    parts = [
        source_url,
        _first_text(row, _COMPANY_KEYS) or "",
        str(_first_present(row, _AMOUNT_KEYS) or ""),
        _first_text(row, _ROUND_KEYS) or "",
        _first_text(row, _ANNOUNCED_KEYS) or "",
        _first_text(row, _SOURCE_URL_KEYS) or "",
    ]
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{adapter_name}:{digest}"


def _infer_format(source_label: str) -> str:
    path = urlparse(source_label).path or source_label
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in _SUPPORTED_FORMATS:
        return suffix
    return "json"


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        normalized_key = _normalize_key(key)
        if normalized_key in normalized:
            return normalized[normalized_key]
    return None


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _first_present(row, keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_amount(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    normalized = text.lower().replace(",", "").replace("$", "").replace("usd", "").strip()
    multiplier = 1.0
    if normalized.endswith("million"):
        multiplier = 1_000_000.0
        normalized = normalized[:-7].strip()
    elif normalized.endswith("billion"):
        multiplier = 1_000_000_000.0
        normalized = normalized[:-7].strip()
    elif normalized.endswith("m"):
        multiplier = 1_000_000.0
        normalized = normalized[:-1].strip()
    elif normalized.endswith("b"):
        multiplier = 1_000_000_000.0
        normalized = normalized[:-1].strip()
    elif normalized.endswith("k"):
        multiplier = 1_000.0
        normalized = normalized[:-1].strip()

    try:
        return float(normalized) * multiplier
    except ValueError:
        return None


def _infer_currency(amount_raw: Any) -> str:
    if isinstance(amount_raw, str) and ("$" in amount_raw or "usd" in amount_raw.lower()):
        return "USD"
    return "USD"


def _parse_investors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return _dedupe([str(item).strip() for item in value if str(item).strip()])
    text = str(value).strip()
    if not text:
        return []
    separator = ";" if ";" in text else ","
    return _dedupe([item.strip() for item in text.split(separator) if item.strip()])


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_tags(round_name: str, sector: str | None) -> list[str]:
    tags = ["funding", "funding-round", _slug(round_name)]
    if sector:
        tags.append(_slug(sector))
    return _dedupe([tag for tag in tags if tag])


def _credibility(amount_usd: float) -> float:
    if amount_usd >= 100_000_000:
        return 0.85
    if amount_usd >= 25_000_000:
        return 0.78
    if amount_usd >= 5_000_000:
        return 0.7
    return 0.62


def _file_url(local_path: str) -> str:
    return f"file://{Path(local_path).resolve()}"


def _format_money(amount_usd: float, currency: str) -> str:
    currency_prefix = "$" if currency.upper() == "USD" else f"{currency.upper()} "
    if amount_usd >= 1_000_000_000:
        return f"{currency_prefix}{amount_usd / 1_000_000_000:g}B"
    if amount_usd >= 1_000_000:
        return f"{currency_prefix}{amount_usd / 1_000_000:g}M"
    if amount_usd >= 1_000:
        return f"{currency_prefix}{amount_usd / 1_000:g}K"
    return f"{currency_prefix}{amount_usd:g}"


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _slug(value: str) -> str:
    return "-".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = [value] if isinstance(value, str) else value
    try:
        return _dedupe([str(item).strip() for item in values if str(item).strip()])
    except TypeError:
        return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


FundingRoundAdapter = FundingRoundsAdapter
