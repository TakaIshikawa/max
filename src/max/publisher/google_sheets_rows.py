"""Google Sheets row publisher for generated TactSpec previews."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._summary_payloads import summary_markdown, summary_metadata, summary_title


DEFAULT_GOOGLE_SHEETS_API_URL = "https://sheets.googleapis.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
REDACTED = "[REDACTED]"


class GoogleSheetsRowPublishError(RuntimeError):
    """Raised when a Google Sheets row publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        access_token: str | None = None,
    ) -> None:
        super().__init__(_redact_text(message, access_token=access_token))
        self.status_code = status_code


@dataclass(frozen=True)
class GoogleSheetsRowPayload:
    """Google Sheets values:append request payload."""

    range: str
    values: list[list[Any]]
    major_dimension: str = "ROWS"

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON payload sent to the values:append endpoint."""
        return {
            "range": self.range,
            "majorDimension": self.major_dimension,
            "values": self.values,
        }


@dataclass(frozen=True)
class GoogleSheetsRowPublishResult:
    """Summary of a Google Sheets row publish or dry run."""

    status_code: int | None
    spreadsheet_id: str
    range: str
    updated_range: str | None
    updated_rows: int | None
    updated_cells: int | None
    dry_run: bool
    payload: dict[str, Any]
    endpoint: str
    headers: dict[str, str]


class GoogleSheetsRowPublisher:
    """Build and optionally append idea summary rows to Google Sheets."""

    def __init__(
        self,
        spreadsheet_id: str,
        range: str,
        *,
        access_token: str | None = None,
        api_url: str = DEFAULT_GOOGLE_SHEETS_API_URL,
        value_input_option: str = "RAW",
        insert_data_option: str = "INSERT_ROWS",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.spreadsheet_id = _required_text(
            spreadsheet_id,
            "Google Sheets spreadsheet_id is required",
            access_token=access_token,
        )
        self.range = _required_text(
            range,
            "Google Sheets range is required",
            access_token=access_token,
        )
        self.access_token = _optional_text(access_token)
        self.api_url = _required_text(
            api_url,
            "Google Sheets api_url is required",
            access_token=access_token,
        ).rstrip("/")
        self.value_input_option = _required_text(
            value_input_option,
            "Google Sheets value_input_option is required",
            access_token=access_token,
        )
        self.insert_data_option = _required_text(
            insert_data_option,
            "Google Sheets insert_data_option is required",
            access_token=access_token,
        )
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        spreadsheet_id: str | None = None,
        range: str | None = None,
        access_token: str | None = None,
        api_url: str | None = None,
        value_input_option: str = "RAW",
        insert_data_option: str = "INSERT_ROWS",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> GoogleSheetsRowPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        if not resolved_spreadsheet_id:
            raise GoogleSheetsRowPublishError(
                "Google Sheets spreadsheet_id is required; pass spreadsheet_id or set "
                "GOOGLE_SHEETS_SPREADSHEET_ID",
                access_token=access_token,
            )
        resolved_range = range or os.getenv("GOOGLE_SHEETS_RANGE")
        if not resolved_range:
            raise GoogleSheetsRowPublishError(
                "Google Sheets range is required; pass range or set GOOGLE_SHEETS_RANGE",
                access_token=access_token,
            )
        return cls(
            resolved_spreadsheet_id,
            resolved_range,
            access_token=access_token
            or os.getenv("GOOGLE_ACCESS_TOKEN")
            or os.getenv("GOOGLE_SHEETS_ACCESS_TOKEN"),
            api_url=api_url or os.getenv("GOOGLE_SHEETS_API_URL", DEFAULT_GOOGLE_SHEETS_API_URL),
            value_input_option=value_input_option,
            insert_data_option=insert_data_option,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def append_endpoint(self) -> str:
        """Return the Google Sheets values:append REST endpoint."""
        spreadsheet_id = quote(self.spreadsheet_id, safe="")
        range_part = quote(self.range, safe="")
        return f"{self.api_url}/v4/spreadsheets/{spreadsheet_id}/values/{range_part}:append"

    @property
    def has_auth(self) -> bool:
        """Return whether live Google Sheets publishing has credentials."""
        return bool(self.access_token)

    def build_row_payload(self, tact_spec: dict[str, Any]) -> GoogleSheetsRowPayload:
        """Convert a Max summary payload into a Google Sheets append payload."""
        metadata = summary_metadata(tact_spec, publisher="max.google_sheets_rows")
        row = [
            summary_title(tact_spec),
            summary_markdown(tact_spec),
            _text(metadata.get("source_type")),
            _text(metadata.get("source_id")),
            _text(metadata.get("idea_id")),
            _text(metadata.get("design_brief_id")),
            datetime.now(timezone.utc).isoformat(),
        ]
        return GoogleSheetsRowPayload(range=self.range, values=[row])

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True) -> GoogleSheetsRowPublishResult:
        """Build the row payload and optionally append it to Google Sheets."""
        payload = self.build_row_payload(tact_spec).to_dict()
        if dry_run:
            return GoogleSheetsRowPublishResult(
                status_code=None,
                spreadsheet_id=self.spreadsheet_id,
                range=self.range,
                updated_range=None,
                updated_rows=None,
                updated_cells=None,
                dry_run=True,
                payload=payload,
                endpoint=self.append_endpoint,
                headers=self._preview_headers(),
            )

        if not self.has_auth:
            raise GoogleSheetsRowPublishError(
                "GOOGLE_ACCESS_TOKEN or GOOGLE_SHEETS_ACCESS_TOKEN is required for live Google Sheets publishing; "
                "use dry_run to preview",
                access_token=self.access_token,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, payload)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GoogleSheetsRowPublishError(
                f"Google Sheets row publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, access_token=self.access_token)}",
                status_code=response.status_code,
                access_token=self.access_token,
            )

        body = _json_response(response)
        updates = body.get("updates") if isinstance(body.get("updates"), dict) else {}
        return GoogleSheetsRowPublishResult(
            status_code=response.status_code,
            spreadsheet_id=self.spreadsheet_id,
            range=self.range,
            updated_range=_optional_text(updates.get("updatedRange")),
            updated_rows=_optional_int(updates.get("updatedRows")),
            updated_cells=_optional_int(updates.get("updatedCells")),
            dry_run=False,
            payload=payload,
            endpoint=self.append_endpoint,
            headers=self._preview_headers(),
        )

    def _post_with_retries(self, client: httpx.Client, payload: dict[str, Any]) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(
                    self.append_endpoint,
                    params={
                        "valueInputOption": self.value_input_option,
                        "insertDataOption": self.insert_data_option,
                    },
                    json=payload,
                    headers={
                        **self._headers(),
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc), access_token=self.access_token)
                raise GoogleSheetsRowPublishError(
                    f"Google Sheets row publish failed for {self.append_endpoint}: {message}",
                    access_token=self.access_token,
                ) from exc

            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response

    def _preview_headers(self) -> dict[str, str]:
        return _preview_headers()

    def _headers(self) -> dict[str, str]:
        return _headers_for_token(self.access_token)


GoogleSheetsRowsPublisher = GoogleSheetsRowPublisher


def _preview_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {REDACTED}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "max-google-sheets-rows-publisher/1",
    }


def _headers_for_token(access_token: str | None) -> dict[str, str]:
    headers = _preview_headers()
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _recommendation_score(evaluation: dict[str, Any]) -> str:
    if not evaluation:
        return ""
    recommendation = _text(evaluation.get("recommendation"))
    score = evaluation.get("overall_score")
    if isinstance(score, int | float):
        score_text = f"{score:.1f}"
    else:
        score_text = _text(score)
    if recommendation and score_text:
        return f"{recommendation} ({score_text})"
    return recommendation or score_text


def _required_text(
    value: object,
    message: str,
    *,
    access_token: str | None = None,
) -> str:
    text = _text(value)
    if not text:
        raise GoogleSheetsRowPublishError(message, access_token=access_token)
    return text


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _response_body_preview(
    response: httpx.Response,
    *,
    access_token: str | None = None,
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), access_token=access_token)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise GoogleSheetsRowPublishError(
            "Google Sheets row publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise GoogleSheetsRowPublishError(
            "Google Sheets row publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return body


def _redact_text(text: str, *, access_token: str | None = None) -> str:
    redacted = text
    token = _optional_text(access_token)
    if token:
        redacted = redacted.replace(token, REDACTED)
    redacted = re.sub(
        r"(?i)(authorization:\s*bearer\s+)[^\s,;)}\]]+",
        rf"\1{REDACTED}",
        redacted,
    )
    redacted = re.sub(r"(?i)(bearer\s+)[^\s,;)}\]]+", rf"\1{REDACTED}", redacted)
    redacted = re.sub(r"(?i)(access[_-]?token[\"'\s:=]+)[^\"'\s,;)}\]]+", rf"\1{REDACTED}", redacted)
    return redacted
