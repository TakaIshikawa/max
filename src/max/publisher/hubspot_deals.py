"""HubSpot deal publisher for Max design briefs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from max.publisher.webhook import redact_url


DEFAULT_HUBSPOT_API_URL = "https://api.hubapi.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class HubSpotDealPublishError(RuntimeError):
    """Raised when a HubSpot deal publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        attempts: list[dict[str, Any]] | None = None,
        token: str | None = None,
    ) -> None:
        super().__init__(_redact_text(message, token))
        self.status_code = status_code
        self.attempts = attempts or []


@dataclass(frozen=True)
class HubSpotDealPayload:
    """HubSpot deal creation payload plus Max-specific metadata."""

    properties: dict[str, str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable deal payload preview."""
        return {
            "properties": self.properties,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class HubSpotDealPublishResult:
    """Summary of a HubSpot deal publish or dry run."""

    status_code: int | None
    deal_id: str | None
    deal_url: str | None
    dry_run: bool
    payload: dict[str, Any]
    attempts: list[dict[str, Any]]


class HubSpotDealPublisher:
    """Build and optionally create HubSpot deals from persisted design briefs."""

    def __init__(
        self,
        *,
        access_token: str | None = None,
        api_url: str = DEFAULT_HUBSPOT_API_URL,
        pipeline_id: str | None = None,
        deal_stage_id: str | None = None,
        portal_id: str | None = None,
        deal_owner_id: str | None = None,
        amount: str | int | float | None = None,
        close_date: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = _optional_text(access_token)
        self.api_url = _required_url(api_url)
        self.pipeline_id = _optional_text(pipeline_id)
        self.deal_stage_id = _optional_text(deal_stage_id)
        self.portal_id = _optional_text(portal_id)
        self.deal_owner_id = _optional_text(deal_owner_id)
        self.amount = _optional_amount(amount)
        self.close_date = _optional_text(close_date)
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        access_token: str | None = None,
        api_url: str | None = None,
        pipeline_id: str | None = None,
        deal_stage_id: str | None = None,
        portal_id: str | None = None,
        deal_owner_id: str | None = None,
        amount: str | int | float | None = None,
        close_date: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> HubSpotDealPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        return cls(
            access_token=access_token
            or os.getenv("HUBSPOT_ACCESS_TOKEN")
            or os.getenv("HUBSPOT_TOKEN"),
            api_url=api_url or os.getenv("HUBSPOT_API_URL", DEFAULT_HUBSPOT_API_URL),
            pipeline_id=pipeline_id or os.getenv("HUBSPOT_DEAL_PIPELINE_ID"),
            deal_stage_id=deal_stage_id
            or os.getenv("HUBSPOT_DEAL_STAGE_ID")
            or os.getenv("HUBSPOT_DEALSTAGE_ID"),
            portal_id=portal_id or os.getenv("HUBSPOT_PORTAL_ID"),
            deal_owner_id=deal_owner_id or os.getenv("HUBSPOT_DEAL_OWNER_ID"),
            amount=amount,
            close_date=close_date,
            timeout=timeout,
            max_retries=max_retries,
            client=client,
        )

    @property
    def deal_endpoint(self) -> str:
        """Return the HubSpot REST endpoint used for deal creation."""
        return f"{self.api_url}/crm/v3/objects/deals"

    @property
    def has_auth(self) -> bool:
        """Return whether live HubSpot deal publishing has credentials."""
        return bool(self.access_token)

    def build_design_brief_payload(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
        deal_name: str | None = None,
        amount: str | int | float | None = None,
        close_date: str | None = None,
    ) -> HubSpotDealPayload:
        """Convert a persisted design brief Markdown export into a HubSpot deal payload."""
        brief_id = str(design_brief.get("id") or "").strip()
        title = _deal_name(deal_name or design_brief.get("title") or brief_id)
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))
        readiness_score = _float_value(design_brief.get("readiness_score"))

        properties: dict[str, str] = {
            "dealname": title,
            "description": _deal_description(design_brief, markdown=markdown),
        }
        if self.pipeline_id:
            properties["pipeline"] = self.pipeline_id
        if self.deal_stage_id:
            properties["dealstage"] = self.deal_stage_id
        if self.deal_owner_id:
            properties["hubspot_owner_id"] = self.deal_owner_id
        resolved_amount = _optional_amount(amount) or self.amount
        if resolved_amount:
            properties["amount"] = resolved_amount
        resolved_close_date = _optional_text(close_date) or self.close_date
        if resolved_close_date:
            properties["closedate"] = resolved_close_date

        metadata = {
            "publisher": "max.hubspot_deals",
            "source_system": "max",
            "source_type": "design_brief",
            "design_brief_id": brief_id or None,
            "domain": design_brief.get("domain"),
            "theme": design_brief.get("theme"),
            "lead_idea_id": design_brief.get("lead_idea_id"),
            "source_idea_ids": source_idea_ids,
            "readiness_score": readiness_score,
            "pipeline_id": self.pipeline_id,
            "deal_stage_id": self.deal_stage_id,
            "portal_id": self.portal_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return HubSpotDealPayload(properties=properties, metadata=metadata)

    def publish_design_brief(
        self,
        design_brief: dict[str, Any],
        *,
        markdown: str,
        deal_name: str | None = None,
        amount: str | int | float | None = None,
        close_date: str | None = None,
        dry_run: bool = True,
    ) -> HubSpotDealPublishResult:
        """Build the design brief deal payload and optionally create it in HubSpot."""
        payload = self.build_design_brief_payload(
            design_brief,
            markdown=markdown,
            deal_name=deal_name,
            amount=amount,
            close_date=close_date,
        )
        return self.publish_payload(payload, dry_run=dry_run)

    def publish_payload(
        self,
        payload: HubSpotDealPayload | dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> HubSpotDealPublishResult:
        """Create a HubSpot deal from a prebuilt payload."""
        payload_dict = payload.to_dict() if isinstance(payload, HubSpotDealPayload) else dict(payload)
        if dry_run:
            return HubSpotDealPublishResult(
                status_code=None,
                deal_id=None,
                deal_url=None,
                dry_run=True,
                payload=payload_dict,
                attempts=[],
            )

        if not self.access_token:
            raise HubSpotDealPublishError(
                "HUBSPOT_ACCESS_TOKEN is required for live HubSpot deal publishing; "
                "use dry_run to preview",
                token=self.access_token,
            )

        attempts: list[dict[str, Any]] = []
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = self._post_with_retries(client, payload_dict, attempts)
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise HubSpotDealPublishError(
                f"HubSpot deal publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, token=self.access_token)}",
                status_code=response.status_code,
                attempts=attempts,
                token=self.access_token,
            )

        body = _json_response(response, token=self.access_token, attempts=attempts)
        deal_id = _optional_text(body.get("id"))
        if not deal_id:
            properties = body.get("properties") if isinstance(body.get("properties"), dict) else {}
            deal_id = _optional_text(properties.get("hs_object_id"))
        if not deal_id:
            raise HubSpotDealPublishError(
                "HubSpot deal publish failed: response did not include created deal id",
                status_code=response.status_code,
                attempts=attempts,
                token=self.access_token,
            )

        deal_url = _deal_url(body, deal_id=deal_id, portal_id=self.portal_id)
        return HubSpotDealPublishResult(
            status_code=response.status_code,
            deal_id=deal_id,
            deal_url=deal_url,
            dry_run=False,
            payload={
                **payload_dict,
                "metadata": {
                    **payload_dict.get("metadata", {}),
                    "hubspot_deal_id": deal_id,
                    "hubspot_deal_url": deal_url,
                },
            },
            attempts=attempts,
        )

    def _post_with_retries(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
        attempts: list[dict[str, Any]],
    ) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(
                    self.deal_endpoint,
                    json={"properties": payload["properties"]},
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                        "User-Agent": "max-hubspot-deals-publisher/1",
                    },
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                attempts.append(_attempt(self.deal_endpoint, error=str(exc), token=self.access_token))
                raise HubSpotDealPublishError(
                    f"HubSpot deal publish failed for {redact_url(self.deal_endpoint)}: {exc}",
                    attempts=attempts,
                    token=self.access_token,
                ) from exc

            attempts.append(_attempt(self.deal_endpoint, status_code=response.status_code))
            last_response = response
            if response.status_code not in TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                return response
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))

        return last_response


HubSpotDealsPublisher = HubSpotDealPublisher


def _deal_description(design_brief: dict[str, Any], *, markdown: str) -> str:
    source_idea_ids = ", ".join(_string_list(design_brief.get("source_idea_ids"))) or "None"
    lines = [
        str(design_brief.get("merged_product_concept") or design_brief.get("why_this_now") or "").strip(),
        "",
        f"Max design brief: {design_brief.get('id') or 'Not specified'}",
        f"Domain: {design_brief.get('domain') or 'Not specified'}",
        f"Theme: {design_brief.get('theme') or 'Not specified'}",
        f"Readiness score: {_float_value(design_brief.get('readiness_score')):.1f}",
        f"Lead idea: {design_brief.get('lead_idea_id') or 'Not specified'}",
        f"Source ideas: {source_idea_ids}",
        "",
        "Design brief markdown:",
        markdown.strip(),
    ]
    return "\n".join(lines).strip()[:65000]


def _deal_name(value: object) -> str:
    text = str(value).strip() if value else "Design Brief"
    return f"[Max] {text}" if not text.startswith("[Max]") else text


def _deal_url(body: dict[str, Any], *, deal_id: str, portal_id: str | None) -> str | None:
    for key in ("url", "deal_url", "hs_deal_url"):
        value = _optional_text(body.get(key))
        if value:
            return value
    if portal_id:
        return f"https://app.hubspot.com/contacts/{portal_id}/deal/{deal_id}"
    return None


def _json_response(
    response: httpx.Response,
    *,
    token: str | None,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise HubSpotDealPublishError(
            "HubSpot deal publish failed: response was not valid JSON",
            status_code=response.status_code,
            attempts=attempts,
            token=token,
        ) from exc
    return body if isinstance(body, dict) else {}


def _response_body_preview(
    response: httpx.Response,
    *,
    token: str | None,
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), token)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _attempt(
    url: str,
    *,
    status_code: int | None = None,
    error: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "method": "POST",
        "url": redact_url(url),
    }
    if status_code is not None:
        attempt["status_code"] = status_code
    if error:
        attempt["error"] = _redact_text(error, token)
    return attempt


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value else ""
    if not text:
        raise HubSpotDealPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _optional_amount(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return str(value)
    text = str(value).strip()
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "HubSpot api_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HubSpotDealPublishError("HubSpot api_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list | tuple | set):
        return []
    values: list[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text and text not in values:
            values.append(text)
    return values


def _float_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _redact_text(text: str, token: str | None = None) -> str:
    redacted = text
    if token:
        redacted = redacted.replace(token, "[redacted]")
    return redacted
