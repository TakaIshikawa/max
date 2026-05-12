"""Google Docs publisher for Max ideas and design briefs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_API_URL = "https://docs.googleapis.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GoogleDocsPublishError(RuntimeError):
    """Raised when a Google Docs publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None, secrets: list[str | None] | None = None) -> None:
        super().__init__(_redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class GoogleDocsPublishResult:
    """Summary of a Google Docs publish or dry run."""

    status_code: int | None
    document_id: str | None
    document_url: str | None
    dry_run: bool
    create_endpoint: str
    insert_endpoint: str | None
    create_payload: dict[str, Any]
    insert_payload: dict[str, Any]
    rendered_text: str


class GoogleDocsPublisher:
    """Create Google Docs documents from Max payloads."""

    def __init__(
        self,
        *,
        access_token: str | None = None,
        api_url: str | None = None,
        document_title: str | None = None,
        title_prefix: str | None = None,
        folder_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = _optional_text(access_token)
        self.api_url = _normalize_api_url(api_url or DEFAULT_API_URL)
        self.document_title = _optional_text(document_title)
        self.title_prefix = _optional_text(title_prefix)
        self.folder_id = _optional_text(folder_id)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        access_token: str | None = None,
        api_url: str | None = None,
        document_title: str | None = None,
        title_prefix: str | None = None,
        folder_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GoogleDocsPublisher:
        """Create a publisher using explicit values first, then environment variables."""
        return cls(
            access_token=access_token or os.getenv("GOOGLE_DOCS_ACCESS_TOKEN"),
            api_url=api_url or os.getenv("GOOGLE_DOCS_API_URL") or DEFAULT_API_URL,
            document_title=document_title or os.getenv("GOOGLE_DOCS_DOCUMENT_TITLE"),
            title_prefix=title_prefix or os.getenv("GOOGLE_DOCS_TITLE_PREFIX"),
            folder_id=folder_id or os.getenv("GOOGLE_DOCS_FOLDER_ID"),
            timeout=timeout,
            client=client,
        )

    @property
    def create_endpoint(self) -> str:
        return f"{self.api_url}/v1/documents"

    def insert_endpoint(self, document_id: str) -> str:
        return f"{self.api_url}/v1/documents/{document_id}:batchUpdate"

    def build_document_request(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
        title = self.document_title or _document_title(payload)
        if self.title_prefix:
            title = f"{self.title_prefix} {title}"
        create_payload: dict[str, Any] = {"title": title[:255]}
        if self.folder_id:
            create_payload["metadata"] = {"folder_id": self.folder_id}
        rendered_text = _render_payload(payload)
        insert_payload = {"requests": [{"insertText": {"location": {"index": 1}, "text": rendered_text}}]}
        return create_payload, insert_payload, rendered_text

    def publish(self, payload: dict[str, Any], *, dry_run: bool = True) -> GoogleDocsPublishResult:
        create_payload, insert_payload, rendered_text = self.build_document_request(payload)
        if dry_run:
            return GoogleDocsPublishResult(
                status_code=None,
                document_id=None,
                document_url=None,
                dry_run=True,
                create_endpoint=self.create_endpoint,
                insert_endpoint=None,
                create_payload=create_payload,
                insert_payload=insert_payload,
                rendered_text=rendered_text,
            )
        if not self.access_token:
            raise GoogleDocsPublishError(
                "GOOGLE_DOCS_ACCESS_TOKEN is required for live Google Docs publishing; use dry_run to preview",
                secrets=self._secrets,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            create_response = client.post(
                self.create_endpoint,
                json=create_payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            if not 200 <= create_response.status_code < 300:
                raise GoogleDocsPublishError(
                    f"Google Docs create failed with HTTP {create_response.status_code}: "
                    f"{_response_body_preview(create_response, secrets=self._secrets)}",
                    status_code=create_response.status_code,
                    secrets=self._secrets,
                )
            document_id = _document_id(_json_response(create_response, secrets=self._secrets))
            if not document_id:
                raise GoogleDocsPublishError("Google Docs create failed: response did not include documentId", secrets=self._secrets)
            insert_endpoint = self.insert_endpoint(document_id)
            insert_response = client.post(
                insert_endpoint,
                json=insert_payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            if not 200 <= insert_response.status_code < 300:
                raise GoogleDocsPublishError(
                    f"Google Docs insert failed with HTTP {insert_response.status_code}: "
                    f"{_response_body_preview(insert_response, secrets=self._secrets)}",
                    status_code=insert_response.status_code,
                    secrets=self._secrets,
                )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise GoogleDocsPublishError(
                f"Google Docs publish failed for {_redact_url(self.create_endpoint)}: {exc}",
                secrets=self._secrets,
            ) from exc
        finally:
            if close_client:
                client.close()

        return GoogleDocsPublishResult(
            status_code=insert_response.status_code,
            document_id=document_id,
            document_url=f"https://docs.google.com/document/d/{document_id}/edit",
            dry_run=False,
            create_endpoint=self.create_endpoint,
            insert_endpoint=insert_endpoint,
            create_payload=create_payload,
            insert_payload=insert_payload,
            rendered_text=rendered_text,
        )

    @property
    def _secrets(self) -> list[str | None]:
        return [self.access_token]

    def _headers(self) -> dict[str, str]:
        assert self.access_token is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "max-google-docs-publisher/1",
        }


def publish_google_doc(
    payload: dict[str, Any],
    *,
    access_token: str | None = None,
    api_url: str | None = None,
    document_title: str | None = None,
    title_prefix: str | None = None,
    folder_id: str | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> GoogleDocsPublishResult:
    """Create a Google Docs document from a Max payload."""
    return GoogleDocsPublisher.from_env(
        access_token=access_token,
        api_url=api_url,
        document_title=document_title,
        title_prefix=title_prefix,
        folder_id=folder_id,
        timeout=timeout,
        client=client,
    ).publish(payload, dry_run=dry_run)


def _document_title(payload: dict[str, Any]) -> str:
    if _is_design_brief_payload(payload):
        brief = _dict_value(payload, "design_brief")
        return f"Max Design Brief - {_text(brief.get('title'), brief.get('id'), 'Untitled')}"
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    return f"Max Idea - {_text(project.get('title'), source.get('idea_id'), 'Untitled')}"


def _render_payload(payload: dict[str, Any]) -> str:
    if _is_design_brief_payload(payload):
        return _render_design_brief(payload)
    return _render_idea(payload)


def _render_idea(payload: dict[str, Any]) -> str:
    source = _dict_value(payload, "source")
    project = _dict_value(payload, "project")
    problem = _dict_value(payload, "problem")
    solution = _dict_value(payload, "solution")
    execution = _dict_value(payload, "execution")
    evidence = _dict_value(payload, "evidence")
    evaluation = _dict_value(payload, "evaluation")
    return "\n".join(
        [
            _text(project.get("title"), source.get("idea_id"), "Untitled idea"),
            "",
            _text(project.get("summary"), "No summary provided."),
            "",
            f"Idea ID: {_text(source.get('idea_id'), 'Not specified')}",
            f"Score: {_score_text(evaluation.get('overall_score'))}",
            f"Recommendation: {_text(evaluation.get('recommendation'), 'Not specified')}",
            "",
            "Problem",
            _text(problem.get("statement"), "Not specified"),
            "",
            "Solution",
            _text(solution.get("approach"), "Not specified"),
            "",
            "MVP Scope",
            _bullet_text(execution.get("mvp_scope")),
            "",
            "Evidence",
            _text(evidence.get("rationale"), "Not specified"),
        ]
    )


def _render_design_brief(payload: dict[str, Any]) -> str:
    brief = _dict_value(payload, "design_brief")
    markdown = _text(brief.get("markdown"), payload.get("markdown"))
    lines = [
        _text(brief.get("title"), brief.get("id"), "Untitled design brief"),
        "",
        _text(brief.get("summary"), brief.get("merged_product_concept"), "No concept provided."),
        "",
        f"Brief ID: {_text(brief.get('id'), 'Not specified')}",
        f"Readiness score: {_score_text(brief.get('readiness_score'))}",
        f"Recommendation: {_text(brief.get('recommendation') or brief.get('status_recommendation'), 'Not specified')}",
        f"Source ideas: {_comma_list(_string_list(brief.get('source_idea_ids')))}",
        "",
        "Validation",
        _text(brief.get("validation_plan"), "Not specified"),
    ]
    if markdown:
        lines.extend(["", "Rendered markdown preview", markdown])
    return "\n".join(lines)


def _is_design_brief_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("design_brief"), dict)


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _string_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_text(item, "") for item in items if _text(item, "")]


def _comma_list(items: list[str]) -> str:
    return ", ".join(items) if items else "None"


def _bullet_text(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "- None"
    return "\n".join(f"- {_text(item)}" for item in items if _text(item)) or "- None"


def _text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _score_text(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.1f}"
    return _text(value, "Not specified")


def _normalize_api_url(value: str) -> str:
    raw = value.rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GoogleDocsPublishError("Google Docs api_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _document_id(body: dict[str, Any]) -> str | None:
    value = body.get("documentId") or body.get("document_id") or body.get("id")
    return str(value) if value is not None else None


def _json_response(response: httpx.Response, *, secrets: list[str | None]) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GoogleDocsPublishError("Google Docs response was not valid JSON", status_code=response.status_code, secrets=secrets) from exc
    return body if isinstance(body, dict) else {}


def _response_body_preview(response: httpx.Response, *, secrets: list[str | None], limit: int = 500) -> str:
    text = _redact_text(response.text.strip(), secrets=secrets)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _redact_text(text: str, *, secrets: list[str | None] | None = None) -> str:
    redacted = text
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return re.sub(r"(?i)\b(access_token|token|authorization)\b([=:]\s*)[^&\s,'\"}]+", r"\1\2<redacted>", _redact_url(redacted))


def _redact_url(text: str) -> str:
    words = text.split()
    return " ".join(_redact_url_word(word) for word in words)


def _redact_url_word(word: str) -> str:
    if "://" not in word:
        return word
    parts = urlsplit(word)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
