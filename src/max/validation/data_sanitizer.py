"""Data sanitizer for detecting and redacting sensitive information.

Detects and redacts:
- API keys and tokens
- Email addresses
- Phone numbers
- Social Security Numbers (SSNs)
- Credit card numbers
- Passwords and secrets
- Private keys
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SensitivePattern:
    """Defines a pattern for detecting sensitive data."""

    name: str
    pattern: re.Pattern
    redaction: str


# Common patterns for sensitive data
# NOTE: Order matters - more specific patterns should come before more general ones
SENSITIVE_PATTERNS = [
    # Private keys (must be early to avoid partial matches)
    SensitivePattern(
        name="private_key",
        pattern=re.compile(
            r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC )?PRIVATE KEY-----',
        ),
        redaction="[REDACTED_PRIVATE_KEY]",
    ),
    # JWT tokens (before generic tokens)
    SensitivePattern(
        name="jwt",
        pattern=re.compile(
            r'\beyJ[a-zA-Z0-9_\-]*\.eyJ[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*\b',
        ),
        redaction="[REDACTED_JWT]",
    ),
    # GitHub Personal Access Tokens (before phone numbers)
    SensitivePattern(
        name="github_token",
        pattern=re.compile(r'\bghp_[a-zA-Z0-9]{36}\b'),
        redaction="[REDACTED_GITHUB_TOKEN]",
    ),
    # AWS Access Keys
    SensitivePattern(
        name="aws_access_key",
        pattern=re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
        redaction="[REDACTED_AWS_KEY]",
    ),
    # Slack tokens
    SensitivePattern(
        name="slack_token",
        pattern=re.compile(r'\bxox[baprs]-[a-zA-Z0-9\-]{10,}\b'),
        redaction="[REDACTED_SLACK_TOKEN]",
    ),
    # API Keys and Tokens (generic patterns)
    SensitivePattern(
        name="api_key",
        pattern=re.compile(
            r'(?:\b(?:api[_-]?key|apikey|access[_-]?token|secret[_-]?key)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?|\bsk_(?:live|test)_[a-zA-Z0-9]{20,}\b)',
            re.IGNORECASE,
        ),
        redaction="[REDACTED_API_KEY]",
    ),
    # Bearer tokens
    SensitivePattern(
        name="bearer_token",
        pattern=re.compile(r'\bBearer\s+([a-zA-Z0-9_\-\.]{20,})', re.IGNORECASE),
        redaction="Bearer [REDACTED_TOKEN]",
    ),
    # Credit card numbers (before phone numbers)
    SensitivePattern(
        name="credit_card",
        pattern=re.compile(
            r'\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b',
        ),
        redaction="[REDACTED_CARD]",
    ),
    # SSN (Social Security Number) (before phone numbers)
    SensitivePattern(
        name="ssn",
        pattern=re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        redaction="[REDACTED_SSN]",
    ),
    # Email addresses
    SensitivePattern(
        name="email",
        pattern=re.compile(
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
        ),
        redaction="[REDACTED_EMAIL]",
    ),
    # Phone numbers (US format - more restrictive, after specific patterns)
    SensitivePattern(
        name="phone_us",
        pattern=re.compile(
            r'\b(?:\+1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        ),
        redaction="[REDACTED_PHONE]",
    ),
    # Password fields in JSON/dict
    SensitivePattern(
        name="password_field",
        pattern=re.compile(
            r'(["\']password["\']\s*:\s*["\'])([^"\']+)(["\'])',
            re.IGNORECASE,
        ),
        redaction=r'\1[REDACTED_PASSWORD]\3',
    ),
]


class DataSanitizer:
    """Sanitizes data by detecting and redacting sensitive information.

    Supports:
    - String sanitization
    - Dictionary/JSON sanitization (preserves structure)
    - List sanitization
    - Custom pattern addition
    - Configurable patterns

    Example:
        sanitizer = DataSanitizer()
        clean_data = sanitizer.sanitize({
            "api_key": "sk_live_1234567890abcdef",
            "email": "user@example.com",
            "data": "Some text with phone 555-123-4567"
        })
        # Result: {"api_key": "[REDACTED_API_KEY]", "email": "[REDACTED_EMAIL]", ...}
    """

    def __init__(self, patterns: list[SensitivePattern] | None = None) -> None:
        """Initialize sanitizer with patterns.

        Args:
            patterns: List of sensitive patterns to use (defaults to SENSITIVE_PATTERNS)
        """
        self.patterns = patterns if patterns is not None else SENSITIVE_PATTERNS

    def add_pattern(self, pattern: SensitivePattern) -> None:
        """Add a custom sensitive data pattern.

        Args:
            pattern: Custom pattern to detect
        """
        self.patterns.append(pattern)

    def sanitize(self, data: Any) -> Any:
        """Sanitize data by redacting sensitive information.

        Args:
            data: Data to sanitize (str, dict, list, or primitive)

        Returns:
            Sanitized data with same structure as input
        """
        if isinstance(data, str):
            return self._sanitize_string(data)
        elif isinstance(data, dict):
            return self._sanitize_dict(data)
        elif isinstance(data, list):
            return self._sanitize_list(data)
        else:
            # Primitive types (int, float, bool, None) pass through
            return data

    def _sanitize_string(self, text: str) -> str:
        """Sanitize a string by applying all patterns.

        Args:
            text: String to sanitize

        Returns:
            Sanitized string with sensitive data redacted
        """
        result = text
        for pattern in self.patterns:
            result = pattern.pattern.sub(pattern.redaction, result)
        return result

    def _sanitize_dict(self, data: dict) -> dict:
        """Sanitize a dictionary recursively.

        Args:
            data: Dictionary to sanitize

        Returns:
            New dictionary with sanitized values
        """
        sanitized = {}
        for key, value in data.items():
            # Sanitize both key and value
            sanitized_key = self._sanitize_string(key) if isinstance(key, str) else key
            sanitized[sanitized_key] = self.sanitize(value)
        return sanitized

    def _sanitize_list(self, data: list) -> list:
        """Sanitize a list recursively.

        Args:
            data: List to sanitize

        Returns:
            New list with sanitized elements
        """
        return [self.sanitize(item) for item in data]

    def detect_sensitive_data(self, data: Any) -> list[str]:
        """Detect types of sensitive data present without sanitizing.

        Args:
            data: Data to check for sensitive information

        Returns:
            List of detected sensitive data type names
        """
        detected: set[str] = set()

        def _check_value(value: Any) -> None:
            if isinstance(value, str):
                for pattern in self.patterns:
                    if pattern.pattern.search(value):
                        detected.add(pattern.name)
            elif isinstance(value, dict):
                for v in value.values():
                    _check_value(v)
            elif isinstance(value, list):
                for item in value:
                    _check_value(item)

        _check_value(data)
        return sorted(detected)


def sanitize(data: Any) -> Any:
    """Convenience function to sanitize data with default patterns.

    Args:
        data: Data to sanitize

    Returns:
        Sanitized data
    """
    sanitizer = DataSanitizer()
    return sanitizer.sanitize(data)
