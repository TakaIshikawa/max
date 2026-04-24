"""Agent failure dataset adapter."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
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

_TASK_KEYS = ("task", "workflow", "scenario", "benchmark_task", "benchmark", "name")
_FAILURE_TYPE_KEYS = ("failure_type", "failureType", "type", "error_type", "category")
_SEVERITY_KEYS = ("severity", "severity_score", "impact", "risk_score")
_MODEL_KEYS = ("model", "agent_model", "llm", "model_name")
_FRAMEWORK_KEYS = ("framework", "agent_framework", "runtime", "tooling")
_REPRO_URL_KEYS = ("reproduction_url", "repro_url", "repro", "url", "issue_url", "source_url")
_SUCCESS_RATE_KEYS = ("success_rate", "successRate", "pass_rate", "passRate")
_FAILURE_RATE_KEYS = ("failure_rate", "failureRate", "fail_rate", "failRate")
_NOTES_KEYS = ("notes", "note", "description", "summary", "details")

_SEVERITY_LABELS = {
    "none": 0.0,
    "low": 1.0,
    "minor": 1.0,
    "medium": 2.0,
    "moderate": 2.0,
    "high": 3.0,
    "major": 3.0,
    "critical": 4.0,
    "severe": 4.0,
}


class AgentFailureDatasetAdapter(SourceAdapter):
    """Read benchmark or incident datasets about agent failures."""

    @property
    def name(self) -> str:
        return "agent_failure_dataset"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

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
    def failure_type_filters(self) -> list[str]:
        return _string_list(self._config.get("failure_type_filters"))

    @property
    def min_severity(self) -> float:
        return _parse_severity(self._config.get("min_severity")) or 0.0

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
                f"Unable to read agent failure dataset: {local_path}",
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
                failure_type_filters=self.failure_type_filters,
                min_severity=self.min_severity,
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
        return _extract_json_rows(_parse_json(text, source_label))
    raise SourceParseError(
        f"Unsupported agent failure dataset format for: {source_label}",
        adapter_name="agent_failure_dataset",
    )


def _parse_csv(text: str, source_label: str) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as exc:
        raise SourceParseError(
            f"Malformed agent failure CSV: {source_label}",
            adapter_name="agent_failure_dataset",
        ) from exc

    if not reader.fieldnames:
        raise SourceParseError(
            f"Agent failure CSV is missing a header row: {source_label}",
            adapter_name="agent_failure_dataset",
        )
    return [dict(row) for row in rows]


def _parse_json(text: str, source_label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParseError(
            f"Malformed agent failure JSON: {source_label}",
            adapter_name="agent_failure_dataset",
        ) from exc


def _parse_jsonl(text: str, source_label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(
                "agent_failure_dataset: skipping malformed JSONL row %s in %s",
                line_number,
                source_label,
            )
            continue
        if isinstance(item, dict):
            rows.append(item)
        else:
            logger.warning(
                "agent_failure_dataset: skipping non-object JSONL row %s in %s",
                line_number,
                source_label,
            )
    return rows


def _extract_json_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("rows", "results", "items", "data", "failures", "incidents"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [data]


def _signal_from_row(
    row: dict[str, Any],
    *,
    adapter_name: str,
    source_url: str,
    row_number: int,
    failure_type_filters: list[str],
    min_severity: float,
) -> Signal | None:
    task = _first_text(row, _TASK_KEYS)
    failure_type = _first_text(row, _FAILURE_TYPE_KEYS)
    severity_raw = _first_present(row, _SEVERITY_KEYS)
    severity = _parse_severity(severity_raw)
    if not task or not failure_type or severity is None:
        logger.warning(
            "%s: skipping malformed row %s from %s",
            adapter_name,
            row_number,
            source_url,
        )
        return None

    if failure_type_filters and failure_type.lower() not in {
        item.lower() for item in failure_type_filters
    }:
        return None
    if severity < min_severity:
        return None

    model = _first_text(row, _MODEL_KEYS)
    framework = _first_text(row, _FRAMEWORK_KEYS)
    reproduction_url = _first_text(row, _REPRO_URL_KEYS)
    success_rate = _parse_rate(_first_present(row, _SUCCESS_RATE_KEYS))
    failure_rate = _parse_rate(_first_present(row, _FAILURE_RATE_KEYS))
    notes = _first_text(row, _NOTES_KEYS)
    signal_url = reproduction_url or source_url

    title = f"Agent failure: {task} - {failure_type}"
    content_parts = [
        f"Task/workflow: {task}",
        f"Failure type: {failure_type}",
        f"Severity: {_format_number(severity)}",
    ]
    if model:
        content_parts.append(f"Model: {model}")
    if framework:
        content_parts.append(f"Framework: {framework}")
    if failure_rate is not None:
        content_parts.append(f"Failure rate: {_format_rate(failure_rate)}")
    if success_rate is not None:
        content_parts.append(f"Success rate: {_format_rate(success_rate)}")
    if notes:
        content_parts.append(f"Notes: {notes}")

    metadata = {
        "task": task,
        "workflow": task,
        "failure_type": failure_type,
        "severity": severity,
        "severity_label": str(severity_raw).strip() if severity_raw is not None else None,
        "model": model,
        "framework": framework,
        "reproduction_url": reproduction_url,
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "notes": notes,
        "signal_role": "problem",
    }

    return Signal(
        id=_stable_id(adapter_name, source_url, row),
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=title[:240],
        content="\n".join(content_parts)[:1000],
        url=signal_url,
        tags=_build_tags(failure_type, model, framework, severity),
        credibility=_credibility(severity),
        metadata=metadata,
    )


def _stable_id(adapter_name: str, source_url: str, row: dict[str, Any]) -> str:
    parts = [
        source_url,
        _first_text(row, _TASK_KEYS) or "",
        _first_text(row, _FAILURE_TYPE_KEYS) or "",
        str(_first_present(row, _SEVERITY_KEYS) or ""),
        _first_text(row, _MODEL_KEYS) or "",
        _first_text(row, _FRAMEWORK_KEYS) or "",
        _first_text(row, _REPRO_URL_KEYS) or "",
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


def _parse_severity(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text in _SEVERITY_LABELS:
        return _SEVERITY_LABELS[text]
    if text.endswith("/10"):
        text = text[:-3].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _parse_rate(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        parsed = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        percent = text.endswith("%")
        try:
            parsed = float(text[:-1].strip() if percent else text)
        except ValueError:
            return None
        if percent:
            parsed = parsed / 100
    if parsed > 1:
        parsed = parsed / 100
    return round(parsed, 4)


def _build_tags(failure_type: str, model: str | None, framework: str | None, severity: float) -> list[str]:
    tags = ["agent-failure", _slug(failure_type)]
    if model:
        tags.append(_slug(model))
    if framework:
        tags.append(_slug(framework))
    if severity >= 3:
        tags.append("high-severity")
    elif severity >= 2:
        tags.append("medium-severity")
    else:
        tags.append("low-severity")
    return _dedupe([tag for tag in tags if tag])


def _credibility(severity: float) -> float:
    return min(max(round(0.55 + severity * 0.08, 3), 0.55), 0.9)


def _file_url(local_path: str) -> str:
    return f"file://{Path(local_path).resolve()}"


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _format_rate(value: float) -> str:
    return f"{value * 100:g}%"


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


AgentFailureDataSetAdapter = AgentFailureDatasetAdapter
