"""Stripe customer note publisher for Max buildable units."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, optional_text, redact_text, required_text, required_url, response_json, response_preview

DEFAULT_API_URL = "https://api.stripe.com"


class StripeCustomerNotePublishError(RuntimeError):
    """Raised when a Stripe customer note publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None, api_key: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[api_key]))
        self.status_code = status_code


@dataclass(frozen=True)
class StripeCustomerNotePayload:
    customer_id: str
    metadata: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"customer_id": self.customer_id, "metadata": self.metadata}

    def to_form_data(self) -> dict[str, str]:
        return {f"metadata[{key}]": value for key, value in self.metadata.items()}


@dataclass(frozen=True)
class StripeCustomerNotePublishResult:
    status_code: int | None
    customer_id: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class StripeCustomerNotePublisher:
    """Build and optionally attach Max context to a Stripe customer as metadata."""

    def __init__(
        self,
        *,
        customer_id: str | None = None,
        api_key: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.customer_id = optional_text(customer_id)
        self.api_key = optional_text(api_key)
        self.api_url = required_url(api_url, "Stripe api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        customer_id: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        client: httpx.Client | None = None,
    ) -> StripeCustomerNotePublisher:
        return cls(
            customer_id=customer_id or os.getenv("STRIPE_CUSTOMER_ID"),
            api_key=api_key or os.getenv("STRIPE_API_KEY"),
            api_url=api_url or os.getenv("STRIPE_API_URL", DEFAULT_API_URL),
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    def customer_endpoint(self, customer_id: str | None = None) -> str:
        resolved = required_text(optional_text(customer_id) or self.customer_id, "Stripe customer_id is required; pass customer_id or set STRIPE_CUSTOMER_ID")
        return f"{self.api_url}/v1/customers/{quote(resolved, safe='')}"

    def build_customer_note_payload(self, unit: dict[str, Any], *, customer_id: str | None = None) -> StripeCustomerNotePayload:
        try:
            resolved = required_text(optional_text(customer_id) or self.customer_id, "Stripe customer_id is required; pass customer_id or set STRIPE_CUSTOMER_ID")
        except ValueError as exc:
            raise StripeCustomerNotePublishError(str(exc), api_key=self.api_key) from exc
        fields = _unit_fields(unit)
        return StripeCustomerNotePayload(
            customer_id=resolved,
            metadata={
                "max_category": fields["category"],
                "max_idea_id": fields["idea_id"],
                "max_problem": fields["problem"],
                "max_score": fields["score"],
                "max_solution": fields["solution"],
                "max_status": fields["status"],
                "max_title": fields["title"],
            },
        )

    def publish(self, unit: dict[str, Any], *, dry_run: bool = True, customer_id: str | None = None) -> StripeCustomerNotePublishResult:
        payload = self.build_customer_note_payload(unit, customer_id=customer_id)
        endpoint = self.customer_endpoint(payload.customer_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return StripeCustomerNotePublishResult(None, payload.customer_id, True, endpoint, payload_dict)
        if not self.api_key:
            raise StripeCustomerNotePublishError("STRIPE_API_KEY is required for live Stripe customer note publishing; use dry_run to preview")

        response = self._post_with_retries(endpoint, payload.to_form_data())
        body = response_json(response, StripeCustomerNotePublishError, "Stripe customer note publish failed: response was not valid JSON")
        return StripeCustomerNotePublishResult(response.status_code, payload.customer_id, False, endpoint, payload_dict, body)

    def _post_with_retries(self, endpoint: str, data: dict[str, str]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            last_response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = client.post(endpoint, data=data, headers=self._headers(), timeout=self.timeout)
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt >= self.max_retries:
                        raise StripeCustomerNotePublishError(f"Stripe customer note publish failed for {endpoint}: {exc}", api_key=self.api_key) from exc
                    continue
                if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= self.max_retries:
                    last_response = response
                    break
                last_response = response
            assert last_response is not None
            if not 200 <= last_response.status_code < 300:
                raise StripeCustomerNotePublishError(
                    f"Stripe customer note publish failed with HTTP {last_response.status_code}: {response_preview(last_response, secrets=[self.api_key])}",
                    status_code=last_response.status_code,
                    api_key=self.api_key,
                )
            return last_response
        finally:
            if close_client:
                client.close()

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "max-stripe-customer-notes-publisher/1",
        }


StripeCustomerNotesPublisher = StripeCustomerNotePublisher

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _unit_fields(unit: dict[str, Any]) -> dict[str, str]:
    if not isinstance(unit, dict):
        raise StripeCustomerNotePublishError("Stripe customer note publishing requires a buildable-unit dict")
    source = _dict(unit, "source")
    project = _dict(unit, "project")
    problem = _dict(unit, "problem")
    solution = _dict(unit, "solution")
    evaluation = _dict(unit, "evaluation")
    quality = _dict(unit, "quality")
    return {
        "title": _text(project.get("title"), unit.get("title"), source.get("title"), "Untitled Max idea"),
        "status": _text(source.get("status"), unit.get("status"), "unknown"),
        "category": _text(source.get("category"), unit.get("category"), "uncategorized"),
        "problem": _text(problem.get("statement"), unit.get("problem"), project.get("summary"), "Not specified"),
        "solution": _text(solution.get("approach"), unit.get("solution"), "Not specified"),
        "score": _score(evaluation.get("overall_score"), quality.get("quality_score"), unit.get("score")),
        "idea_id": _text(source.get("idea_id"), unit.get("idea_id"), unit.get("id"), "unknown"),
    }


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _text(*values: object) -> str:
    for value in values:
        text = optional_text(value)
        if text:
            return text
    return ""


def _score(*values: object) -> str:
    for value in values:
        if isinstance(value, int | float):
            return f"{value:.1f}"
        text = optional_text(value)
        if text:
            return text
    return "Not specified"
