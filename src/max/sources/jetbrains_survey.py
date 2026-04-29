"""JetBrains Developer Ecosystem survey CSV adapter."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.sources.errors import SourceAuthError, SourceParseError, SourceTransientError
from max.types.signal import Signal, SignalSourceType

_DEFAULT_MAX_ROWS = 250
_MULTI_VALUE_SPLIT_RE = re.compile(r"\s*(?:;|\|)\s*")
_YEAR_RE = re.compile(r"(20\d{2})")

_QUESTION_KEYS = {
    "question",
    "questiontext",
    "questionlabel",
    "questionname",
    "questiontitle",
    "variable",
    "column",
    "surveyquestion",
    "surveyquestiontext",
}
_ANSWER_KEYS = {"answer", "response", "value", "option", "choice", "label"}
_PERCENT_KEYS = {"percent", "percentage", "pct", "share", "percentofrespondents"}
_SAMPLE_SIZE_KEYS = {"samplesize", "respondents", "responses", "n", "count", "total"}
_YEAR_KEYS = {"year", "surveyyear"}
_PAIN_TERMS = {
    "challenge",
    "concern",
    "difficult",
    "difficulty",
    "frustration",
    "lack",
    "missing",
    "pain",
    "problem",
    "struggle",
}


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _first_matching_header(headers: list[str], candidates: set[str]) -> str | None:
    by_normalized = {_normalized_key(header): header for header in headers}
    for candidate in candidates:
        if candidate in by_normalized:
            return by_normalized[candidate]
    return None


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, Iterable):
        return []
    return [stripped for item in value if (stripped := str(item).strip())]


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    parsed = _parse_float(value)
    return int(parsed) if parsed is not None else None


def _clean_answer(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_year(
    source_label: str,
    rows: list[dict[str, str]],
    year_header: str | None,
    configured_year: int | None,
) -> int | None:
    if configured_year is not None:
        return configured_year

    if year_header:
        for row in rows:
            year = _parse_int(row.get(year_header))
            if year is not None:
                return year

    match = _YEAR_RE.search(source_label)
    return int(match.group(1)) if match else None


def _question_matches(question: str, filters: list[str]) -> bool:
    if not filters:
        return True
    question_lower = question.lower()
    return any(term.lower() in question_lower for term in filters)


def _stable_id(year: int | None, question: str, answer: str) -> str:
    raw = f"jetbrains_survey:{year or 'unknown'}:{question}:{answer}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"jetbrains_survey:{digest}"


def _signal_role(question: str, answer: str) -> str:
    text = f"{question} {answer}".lower()
    if any(term in text for term in _PAIN_TERMS):
        return "problem"
    return "market"


def _credibility(percent: float, sample_size: int | None) -> float:
    if sample_size is not None:
        if sample_size >= 10_000:
            return 0.9
        if sample_size >= 1_000:
            return 0.82
        if sample_size >= 100:
            return 0.72
        return 0.6
    if percent >= 50:
        return 0.75
    if percent >= 20:
        return 0.68
    return 0.6


class JetBrainsSurveyAdapter(SourceAdapter):
    """Read JetBrains Developer Ecosystem survey CSV exports as quantified signals."""

    @property
    def name(self) -> str:
        return "jetbrains_survey"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SURVEY.value

    @property
    def survey_urls(self) -> list[str]:
        return _as_string_list(self._config.get("survey_urls"))

    @property
    def local_paths(self) -> list[str]:
        return _as_string_list(self._config.get("local_paths"))

    @property
    def question_filters(self) -> list[str]:
        return _as_string_list(self._config.get("question_filters"))

    @property
    def min_percent(self) -> float:
        return float(self._config.get("min_percent", 0) or 0)

    @property
    def max_rows(self) -> int:
        value = self._config.get("max_rows", _DEFAULT_MAX_ROWS)
        if not isinstance(value, int) or isinstance(value, bool):
            return _DEFAULT_MAX_ROWS
        return max(value, 1)

    @property
    def year(self) -> int | None:
        return _parse_int(self._config.get("year"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        row_limit = min(limit, self.max_rows)

        for local_path in self.local_paths:
            if len(signals) >= row_limit:
                break
            text = self._read_local_csv(local_path)
            signals.extend(self._signals_from_csv(text, source_label=local_path, source_url=local_path))

        if len(signals) < row_limit and self.survey_urls:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for survey_url in self.survey_urls:
                    if len(signals) >= row_limit:
                        break
                    text = await self._fetch_csv(survey_url, client)
                    signals.extend(
                        self._signals_from_csv(
                            text,
                            source_label=survey_url,
                            source_url=survey_url,
                        )
                    )

        deduped: dict[str, Signal] = {}
        for signal in signals:
            deduped.setdefault(signal.id, signal)
            if len(deduped) >= row_limit:
                break
        return list(deduped.values())

    def _read_local_csv(self, local_path: str) -> str:
        try:
            return Path(local_path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SourceParseError(
                f"Unable to read JetBrains survey CSV file: {local_path}",
                adapter_name=self.name,
            ) from exc

    async def _fetch_csv(self, survey_url: str, client: httpx.AsyncClient) -> str:
        try:
            response = await fetch_with_retry(survey_url, client, adapter_name=self.name)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                raise SourceAuthError(
                    f"JetBrains survey CSV URL returned HTTP {status_code}: {survey_url}",
                    adapter_name=self.name,
                ) from exc
            raise SourceTransientError(
                f"JetBrains survey CSV URL request failed: {survey_url}",
                adapter_name=self.name,
            ) from exc
        except Exception as exc:
            raise SourceTransientError(
                f"JetBrains survey CSV URL request failed: {survey_url}",
                adapter_name=self.name,
            ) from exc
        return response.text

    def _signals_from_csv(self, csv_text: str, *, source_label: str, source_url: str) -> list[Signal]:
        try:
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
        except csv.Error as exc:
            raise SourceParseError(
                f"Malformed JetBrains survey CSV: {source_label}",
                adapter_name=self.name,
            ) from exc

        headers = list(reader.fieldnames or [])
        if not headers or not rows:
            raise SourceParseError(
                f"JetBrains survey CSV is empty or missing a header row: {source_label}",
                adapter_name=self.name,
            )

        question_header = _first_matching_header(headers, _QUESTION_KEYS)
        answer_header = _first_matching_header(headers, _ANSWER_KEYS)
        percent_header = _first_matching_header(headers, _PERCENT_KEYS)
        sample_size_header = _first_matching_header(headers, _SAMPLE_SIZE_KEYS)
        year_header = _first_matching_header(headers, _YEAR_KEYS)
        year = _extract_year(source_label, rows, year_header, self.year)

        if question_header and answer_header and percent_header:
            return self._signals_from_aggregate_rows(
                rows,
                source_url=source_url,
                year=year,
                question_header=question_header,
                answer_header=answer_header,
                percent_header=percent_header,
                sample_size_header=sample_size_header,
            )

        return self._signals_from_respondent_rows(
            rows,
            headers=headers,
            source_url=source_url,
            year=year,
            ignored_headers={header for header in [year_header] if header},
        )

    def _signals_from_aggregate_rows(
        self,
        rows: list[dict[str, str]],
        *,
        source_url: str,
        year: int | None,
        question_header: str,
        answer_header: str,
        percent_header: str,
        sample_size_header: str | None,
    ) -> list[Signal]:
        signals: list[Signal] = []
        for row in rows:
            question = _clean_answer(row.get(question_header))
            answer = _clean_answer(row.get(answer_header))
            percent = _parse_float(row.get(percent_header))
            sample_size = _parse_int(row.get(sample_size_header)) if sample_size_header else None
            if not question or not answer or percent is None:
                continue
            if not _question_matches(question, self.question_filters):
                continue
            if percent < self.min_percent:
                continue
            signals.append(
                self._build_signal(
                    source_url=source_url,
                    year=year,
                    question=question,
                    answer=answer,
                    percent=percent,
                    sample_size=sample_size,
                )
            )

        if not signals and not self.question_filters:
            raise SourceParseError(
                "JetBrains survey CSV has aggregate columns but no usable question/answer/percent rows",
                adapter_name=self.name,
            )
        return signals

    def _signals_from_respondent_rows(
        self,
        rows: list[dict[str, str]],
        *,
        headers: list[str],
        source_url: str,
        year: int | None,
        ignored_headers: set[str],
    ) -> list[Signal]:
        question_headers = [
            header
            for header in headers
            if header not in ignored_headers and _question_matches(header, self.question_filters)
        ]
        if not question_headers and not self.question_filters:
            raise SourceParseError(
                "Unsupported JetBrains survey CSV: expected aggregate question/answer/percent "
                "columns or respondent-level question columns",
                adapter_name=self.name,
            )

        signals: list[Signal] = []
        for question in question_headers:
            answer_counts: Counter[str] = Counter()
            sample_size = 0
            for row in rows:
                raw_answer = _clean_answer(row.get(question))
                if not raw_answer or raw_answer.upper() in {"NA", "N/A"}:
                    continue
                answers = [answer for answer in _MULTI_VALUE_SPLIT_RE.split(raw_answer) if answer]
                if not answers:
                    continue
                sample_size += 1
                answer_counts.update(answers)

            if sample_size == 0:
                continue

            for answer, count in answer_counts.most_common():
                percent = round((count / sample_size) * 100, 2)
                if percent < self.min_percent:
                    continue
                signals.append(
                    self._build_signal(
                        source_url=source_url,
                        year=year,
                        question=question,
                        answer=answer,
                        percent=percent,
                        sample_size=sample_size,
                    )
                )

        return signals

    def _build_signal(
        self,
        *,
        source_url: str,
        year: int | None,
        question: str,
        answer: str,
        percent: float,
        sample_size: int | None,
    ) -> Signal:
        year_text = str(year) if year is not None else "JetBrains"
        title = f"JetBrains {year_text} survey: {question} - {answer} ({percent:g}%)"
        content = f"{question}: {answer} ({percent:g}%"
        if sample_size is not None:
            content += f", n={sample_size}"
        content += ")"
        parsed = urlparse(source_url)
        url = source_url if parsed.scheme else f"file://{Path(source_url).resolve()}"
        published_at = datetime(year, 1, 1, tzinfo=timezone.utc) if year is not None else None

        return Signal(
            id=_stable_id(year, question, answer),
            source_type=SignalSourceType.SURVEY,
            source_adapter=self.name,
            title=title,
            content=content,
            url=url,
            published_at=published_at,
            tags=["jetbrains", "developer-ecosystem", "survey"],
            credibility=_credibility(percent, sample_size),
            metadata={
                "question": question,
                "answer": answer,
                "percent": percent,
                "sample_size": sample_size,
                "year": year,
                "source_url": url,
                "signal_role": _signal_role(question, answer),
            },
        )
