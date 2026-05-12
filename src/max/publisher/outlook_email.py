"""Outlook/Microsoft Graph email publisher for Max ideas and design briefs."""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, dict_value, join_list, optional_text, redact_text, required_text, required_url, score_text, source_id, text_or_placeholder, title

DEFAULT_GRAPH_API_URL = "https://graph.microsoft.com/v1.0"


class OutlookEmailPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, token: str | None = None) -> None:
        super().__init__(redact_text(message, secrets=[token]))
        self.status_code = status_code


@dataclass(frozen=True)
class OutlookEmailPublishResult:
    status_code: int | None
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response_body: str = ""


class OutlookEmailPublisher:
    def __init__(
        self,
        *,
        access_token: str | None = None,
        sender_user_id: str | None = None,
        to: list[str] | str | None = None,
        cc: list[str] | str | None = None,
        bcc: list[str] | str | None = None,
        subject_prefix: str | None = None,
        importance: str = "normal",
        save_to_sent_items: bool = True,
        graph_api_url: str = DEFAULT_GRAPH_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = optional_text(access_token)
        self.sender_user_id = optional_text(sender_user_id)
        self.to = _recipients(to)
        self.cc = _recipients(cc)
        self.bcc = _recipients(bcc)
        self.subject_prefix = optional_text(subject_prefix)
        self.importance = optional_text(importance) or "normal"
        self.save_to_sent_items = save_to_sent_items
        self.graph_api_url = required_url(graph_api_url, "Microsoft Graph API URL must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> OutlookEmailPublisher:
        return cls(
            access_token=kwargs.pop("access_token", None) or os.getenv("OUTLOOK_ACCESS_TOKEN") or os.getenv("MICROSOFT_GRAPH_ACCESS_TOKEN"),
            sender_user_id=kwargs.pop("sender_user_id", None) or os.getenv("OUTLOOK_SENDER_USER_ID"),
            to=kwargs.pop("to", None) or os.getenv("OUTLOOK_TO"),
            cc=kwargs.pop("cc", None) or os.getenv("OUTLOOK_CC"),
            bcc=kwargs.pop("bcc", None) or os.getenv("OUTLOOK_BCC"),
            subject_prefix=kwargs.pop("subject_prefix", None) or os.getenv("OUTLOOK_SUBJECT_PREFIX"),
            importance=kwargs.pop("importance", None) or os.getenv("OUTLOOK_IMPORTANCE", "normal"),
            graph_api_url=kwargs.pop("graph_api_url", None) or os.getenv("MICROSOFT_GRAPH_API_URL", DEFAULT_GRAPH_API_URL),
            **kwargs,
        )

    @property
    def endpoint(self) -> str:
        if self.sender_user_id:
            return f"{self.graph_api_url}/users/{quote(self.sender_user_id, safe='')}/sendMail"
        return f"{self.graph_api_url}/me/sendMail"

    def build_email_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.to and not self.cc and not self.bcc:
            raise OutlookEmailPublishError("At least one Outlook recipient is required")
        rendered = _render_payload(payload, self.subject_prefix)
        message: dict[str, Any] = {
            "subject": rendered["subject"],
            "importance": self.importance,
            "body": {"contentType": "HTML", "content": rendered["html"]},
            "toRecipients": _graph_recipients(self.to),
        }
        if self.cc:
            message["ccRecipients"] = _graph_recipients(self.cc)
        if self.bcc:
            message["bccRecipients"] = _graph_recipients(self.bcc)
        return {"message": message, "saveToSentItems": self.save_to_sent_items, "plainTextBody": rendered["text"]}

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> OutlookEmailPublishResult:
        email_payload = self.build_email_payload(payload)
        if dry_run:
            return OutlookEmailPublishResult(None, True, self.endpoint, email_payload)
        if not self.access_token:
            raise OutlookEmailPublishError("OUTLOOK_ACCESS_TOKEN is required for live Outlook email publishing; use dry_run to preview")
        response = self._post(email_payload)
        return OutlookEmailPublishResult(response.status_code, False, self.endpoint, email_payload, response.text)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.endpoint, json={"message": payload["message"], "saveToSentItems": payload["saveToSentItems"]}, headers=self._headers(), timeout=self.timeout)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise OutlookEmailPublishError(f"Outlook email publish failed for {self.endpoint}: {exc}", token=self.access_token) from exc
        finally:
            if close_client:
                client.close()
        if response.status_code not in {202, 204}:
            raise OutlookEmailPublishError(f"Outlook email publish failed with HTTP {response.status_code}: {redact_text(response.text, secrets=[self.access_token])}", status_code=response.status_code, token=self.access_token)
        return response

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "User-Agent": "max-outlook-email-publisher/1"}


def publish_outlook_email(payload: dict[str, Any], **kwargs: Any) -> OutlookEmailPublishResult:
    publisher = OutlookEmailPublisher.from_env(**{key: value for key, value in kwargs.items() if key != "dry_run"})
    return publisher.publish(payload, dry_run=kwargs.get("dry_run", True))


def _render_payload(payload: dict[str, Any], subject_prefix: str | None) -> dict[str, str]:
    if "design_brief" in payload:
        brief = dict_value(payload, "design_brief")
        subject = optional_text(brief.get("title")) or optional_text(brief.get("id")) or "Max design brief"
        text = "\n".join([subject, f"Readiness score: {score_text(brief.get('readiness_score'))}", f"Recommendation: {text_or_placeholder(brief.get('recommendation'))}", f"Source ideas: {join_list(brief.get('source_idea_ids'))}", text_or_placeholder(brief.get("markdown") or brief.get("summary"))])
    else:
        project = dict_value(payload, "project")
        evaluation = dict_value(payload, "evaluation")
        source = dict_value(payload, "source")
        subject = title(payload, fallback="Max idea")
        text = "\n".join([subject, text_or_placeholder(project.get("summary")), f"Score: {score_text(evaluation.get('overall_score'))}", f"Recommendation: {text_or_placeholder(evaluation.get('recommendation'))}", f"Source ID: {text_or_placeholder(source_id(source))}"])
    full_subject = f"{subject_prefix} {subject}".strip() if subject_prefix else subject
    return {"subject": full_subject, "text": text, "html": "<br>".join(html.escape(line) for line in text.splitlines())}


def _recipients(value: list[str] | str | None) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _graph_recipients(values: list[str]) -> list[dict[str, dict[str, str]]]:
    return [{"emailAddress": {"address": value}} for value in values]
