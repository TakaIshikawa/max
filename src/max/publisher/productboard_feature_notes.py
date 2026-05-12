"""Productboard feature note publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import (
    DEFAULT_TIMEOUT_SECONDS,
    optional_text,
    quote_path,
    redact_text,
    required_text,
    required_url,
    response_json,
    response_preview,
)
from max.publisher.stripe_customer_notes import _RETRYABLE_STATUS_CODES, _unit_fields

DEFAULT_API_URL = "https://api.productboard.com"


class ProductboardFeatureNotePublishError(RuntimeError):
    """Raised when a Productboard feature note publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        token: str | None = None,
    ) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class ProductboardFeatureNotePayload:
    feature_id: str
    body: str
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "body": self.body,
            "metadata": self.metadata,
        }

    def to_request_json(self) -> dict[str, Any]:
        return {"data": {"content": self.body}}


@dataclass(frozen=True)
class ProductboardFeatureNotePublishResult:
    status_code: int | None
    note_id: str | None
    feature_id: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class ProductboardFeatureNotePublisher:
    """Build and optionally post Max idea context as a Productboard feature note."""

    def __init__(
        self,
        *,
        feature_id: str | None = None,
        token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.feature_id = optional_text(feature_id)
        self.token = optional_text(token)
        self.api_url = required_url(
            api_url,
            "Productboard api_url must be an absolute http(s) URL",
        )
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        feature_id: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> ProductboardFeatureNotePublisher:
        return cls(
            feature_id=feature_id or os.getenv("PRODUCTBOARD_FEATURE_ID"),
            token=token
            or os.getenv("PRODUCTBOARD_ACCESS_TOKEN")
            or os.getenv("PRODUCTBOARD_API_TOKEN"),
            api_url=api_url or os.getenv("PRODUCTBOARD_API_URL", DEFAULT_API_URL),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    def feature_notes_endpoint(self, feature_id: str | None = None) -> str:
        resolved = required_text(
            optional_text(feature_id) or self.feature_id,
            "Productboard feature_id is required; pass feature_id or set PRODUCTBOARD_FEATURE_ID",
        )
        return f"{self.api_url}/features/{quote_path(resolved)}/notes"

    def build_feature_note_payload(
        self,
        unit: dict[str, Any],
        *,
        feature_id: str | None = None,
    ) -> ProductboardFeatureNotePayload:
        try:
            resolved = required_text(
                optional_text(feature_id) or self.feature_id,
                "Productboard feature_id is required; pass feature_id or set PRODUCTBOARD_FEATURE_ID",
            )
        except ValueError as exc:
            raise ProductboardFeatureNotePublishError(str(exc), token=self.token) from exc

        fields = _unit_fields(unit)
        validation_plan = _validation_plan(unit)
        metadata = {
            "publisher": "max.productboard_feature_notes",
            "idea_id": fields["idea_id"],
            "status": fields["status"],
            "category": fields["category"],
            "score": fields["score"],
        }
        return ProductboardFeatureNotePayload(
            feature_id=resolved,
            body=_note_body(fields, validation_plan),
            metadata=metadata,
        )

    def publish(
        self,
        unit: dict[str, Any],
        *,
        dry_run: bool = True,
        feature_id: str | None = None,
    ) -> ProductboardFeatureNotePublishResult:
        payload = self.build_feature_note_payload(unit, feature_id=feature_id)
        endpoint = self.feature_notes_endpoint(payload.feature_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return ProductboardFeatureNotePublishResult(
                None,
                None,
                payload.feature_id,
                True,
                endpoint,
                payload_dict,
            )
        if not self.token:
            raise ProductboardFeatureNotePublishError(
                "PRODUCTBOARD_ACCESS_TOKEN is required for live Productboard feature note publishing; use dry_run to preview"
            )

        response = self._post_with_retries(endpoint, payload.to_request_json())
        body = response_json(
            response,
            ProductboardFeatureNotePublishError,
            "Productboard feature note publish failed: response was not valid JSON",
        )
        return ProductboardFeatureNotePublishResult(
            response.status_code,
            _note_id(body),
            payload.feature_id,
            False,
            endpoint,
            payload_dict,
            body,
        )

    def _post_with_retries(self, endpoint: str, request_json: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(
                        endpoint,
                        json=request_json,
                        headers=self._headers(),
                        timeout=self.timeout,
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt >= self.max_retries:
                        raise ProductboardFeatureNotePublishError(
                            f"Productboard feature note publish failed for {endpoint}: {exc}",
                            token=self.token,
                        ) from exc
                    continue
                last_response = response
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    break
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise ProductboardFeatureNotePublishError(
                    f"Productboard feature note publish failed with HTTP {last_response.status_code}: "
                    f"{response_preview(last_response, secrets=[self.token])}",
                    status_code=last_response.status_code,
                    token=self.token,
                )
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "max-productboard-feature-notes-publisher/1",
        }


ProductboardFeatureNotesPublisher = ProductboardFeatureNotePublisher


def _validation_plan(unit: dict[str, Any]) -> str:
    execution = unit.get("execution") if isinstance(unit.get("execution"), dict) else {}
    return (
        optional_text(execution.get("validation_plan"))
        or optional_text(unit.get("validation_plan"))
        or "Not specified"
    )


def _note_body(fields: dict[str, str], validation_plan: str) -> str:
    return "\n".join(
        [
            fields["title"],
            f"Idea ID: {fields['idea_id']}",
            f"Status: {fields['status']}",
            f"Score: {fields['score']}",
            f"Problem: {fields['problem']}",
            f"Solution: {fields['solution']}",
            f"Validation plan: {validation_plan}",
        ]
    )


def _note_id(body: dict[str, Any]) -> str | None:
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    return optional_text(body.get("id")) or optional_text(data.get("id"))
