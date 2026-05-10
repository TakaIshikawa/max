"""Tests for data sanitizer."""

from __future__ import annotations

import re

from max.validation.data_sanitizer import (
    DataSanitizer,
    SensitivePattern,
    sanitize,
)


def test_sanitize_api_keys() -> None:
    """Should redact API keys."""
    sanitizer = DataSanitizer()

    text = 'api_key = "sk_live_1234567890abcdefghij"'
    result = sanitizer.sanitize(text)

    assert "sk_live_1234567890abcdefghij" not in result
    assert "[REDACTED_API_KEY]" in result


def test_sanitize_bearer_tokens() -> None:
    """Should redact Bearer tokens."""
    sanitizer = DataSanitizer()

    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
    result = sanitizer.sanitize(text)

    assert "Bearer [REDACTED_TOKEN]" in result


def test_sanitize_aws_access_keys() -> None:
    """Should redact AWS access keys."""
    sanitizer = DataSanitizer()

    text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    result = sanitizer.sanitize(text)

    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "[REDACTED_AWS_KEY]" in result


def test_sanitize_github_tokens() -> None:
    """Should redact GitHub personal access tokens."""
    sanitizer = DataSanitizer()

    # GitHub tokens are ghp_ followed by exactly 36 alphanumeric chars
    text = "token: ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    result = sanitizer.sanitize(text)

    assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in result
    assert "[REDACTED_GITHUB_TOKEN]" in result


def test_sanitize_slack_tokens() -> None:
    """Should redact Slack tokens."""
    sanitizer = DataSanitizer()

    text = "SLACK_TOKEN=xoxb-FAKE-FAKE-FAKEFAKEFAKEFAKE"
    result = sanitizer.sanitize(text)

    assert "xoxb-FAKE-FAKE-FAKEFAKEFAKEFAKE" not in result
    assert "[REDACTED_SLACK_TOKEN]" in result


def test_sanitize_email_addresses() -> None:
    """Should redact email addresses."""
    sanitizer = DataSanitizer()

    text = "Contact user@example.com for more info"
    result = sanitizer.sanitize(text)

    assert "user@example.com" not in result
    assert "[REDACTED_EMAIL]" in result


def test_sanitize_phone_numbers() -> None:
    """Should redact phone numbers in various formats."""
    sanitizer = DataSanitizer()

    test_cases = [
        "Call 555-123-4567",
        "Phone: (555) 123-4567",
        "Contact 5551234567",
        "US: +1-555-123-4567",
    ]

    for text in test_cases:
        result = sanitizer.sanitize(text)
        assert "[REDACTED_PHONE]" in result


def test_sanitize_ssn() -> None:
    """Should redact Social Security Numbers."""
    sanitizer = DataSanitizer()

    text = "SSN: 123-45-6789"
    result = sanitizer.sanitize(text)

    assert "123-45-6789" not in result
    assert "[REDACTED_SSN]" in result


def test_sanitize_credit_card_numbers() -> None:
    """Should redact credit card numbers."""
    sanitizer = DataSanitizer()

    test_cases = [
        "Card: 4532-1234-5678-9010",
        "CC: 4532 1234 5678 9010",
    ]

    for text in test_cases:
        result = sanitizer.sanitize(text)
        assert "[REDACTED_CARD]" in result


def test_sanitize_private_keys() -> None:
    """Should redact private keys."""
    sanitizer = DataSanitizer()

    text = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890
-----END RSA PRIVATE KEY-----"""

    result = sanitizer.sanitize(text)

    assert "MIIEpAIBAAKCAQEA1234567890" not in result
    assert "[REDACTED_PRIVATE_KEY]" in result


def test_sanitize_password_fields() -> None:
    """Should redact password values in JSON-like strings."""
    sanitizer = DataSanitizer()

    text = '{"username": "admin", "password": "secret123"}'
    result = sanitizer.sanitize(text)

    assert "secret123" not in result
    assert "[REDACTED_PASSWORD]" in result


def test_sanitize_jwt_tokens() -> None:
    """Should redact JWT tokens."""
    sanitizer = DataSanitizer()

    text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    result = sanitizer.sanitize(text)

    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
    assert "[REDACTED_JWT]" in result


def test_sanitize_dict_preserves_structure() -> None:
    """Should sanitize dictionary values while preserving structure."""
    sanitizer = DataSanitizer()

    data = {
        "user": {
            "name": "Alice",
            "email": "alice@example.com",
            "api_key": "sk_test_FAKEKEYFAKEKEY000000000000",
        },
        "count": 42,
    }

    result = sanitizer.sanitize(data)

    assert isinstance(result, dict)
    assert result["user"]["name"] == "Alice"
    assert result["count"] == 42
    assert "alice@example.com" not in str(result)
    assert "[REDACTED_EMAIL]" in result["user"]["email"]
    assert "[REDACTED_API_KEY]" in result["user"]["api_key"]


def test_sanitize_nested_dict() -> None:
    """Should sanitize deeply nested dictionaries."""
    sanitizer = DataSanitizer()

    data = {
        "level1": {
            "level2": {
                "level3": {
                    "email": "test@example.com",
                }
            }
        }
    }

    result = sanitizer.sanitize(data)

    assert result["level1"]["level2"]["level3"]["email"] == "[REDACTED_EMAIL]"


def test_sanitize_list() -> None:
    """Should sanitize lists recursively."""
    sanitizer = DataSanitizer()

    data = [
        "Contact alice@example.com",
        {"email": "bob@example.com"},
        ["nested@example.com"],
        42,
    ]

    result = sanitizer.sanitize(data)

    assert isinstance(result, list)
    assert len(result) == 4
    assert "[REDACTED_EMAIL]" in result[0]
    assert result[1]["email"] == "[REDACTED_EMAIL]"
    assert result[2][0] == "[REDACTED_EMAIL]"
    assert result[3] == 42


def test_sanitize_primitives_unchanged() -> None:
    """Should pass through primitive types unchanged."""
    sanitizer = DataSanitizer()

    assert sanitizer.sanitize(42) == 42
    assert sanitizer.sanitize(3.14) == 3.14
    assert sanitizer.sanitize(True) is True
    assert sanitizer.sanitize(None) is None


def test_add_custom_pattern() -> None:
    """Should support adding custom patterns."""
    sanitizer = DataSanitizer(patterns=[])

    custom_pattern = SensitivePattern(
        name="custom_id",
        pattern=re.compile(r'\bCID-\d{6}\b'),
        redaction="[REDACTED_CUSTOM_ID]",
    )
    sanitizer.add_pattern(custom_pattern)

    text = "Customer ID: CID-123456"
    result = sanitizer.sanitize(text)

    assert "CID-123456" not in result
    assert "[REDACTED_CUSTOM_ID]" in result


def test_detect_sensitive_data() -> None:
    """Should detect types of sensitive data without sanitizing."""
    sanitizer = DataSanitizer()

    data = {
        "email": "user@example.com",
        "phone": "555-123-4567",
        "description": "Some normal text",
    }

    detected = sanitizer.detect_sensitive_data(data)

    assert "email" in detected
    assert "phone_us" in detected
    assert len(detected) == 2


def test_detect_sensitive_data_in_nested_structures() -> None:
    """Should detect sensitive data in nested structures."""
    sanitizer = DataSanitizer()

    data = {
        "public": "safe data",
        "nested": {
            "deeper": {
                "secret": "api_key = sk_test_FAKEKEYFAKEKEY000000000000",
            }
        },
    }

    detected = sanitizer.detect_sensitive_data(data)

    assert "api_key" in detected


def test_detect_sensitive_data_empty() -> None:
    """Should return empty list when no sensitive data detected."""
    sanitizer = DataSanitizer()

    data = {"name": "Alice", "age": 30, "city": "San Francisco"}

    detected = sanitizer.detect_sensitive_data(data)

    assert detected == []


def test_convenience_sanitize_function() -> None:
    """Should provide convenience function with default patterns."""
    text = "Email: user@example.com, API key: sk_test_FAKEKEYFAKEKEY000000000000"

    result = sanitize(text)

    assert "user@example.com" not in result
    assert "sk_test_FAKEKEYFAKEKEY000000000000" not in result
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_API_KEY]" in result


def test_sanitize_multiple_patterns_in_one_string() -> None:
    """Should handle multiple sensitive patterns in single string."""
    sanitizer = DataSanitizer()

    text = "Contact alice@example.com at 555-123-4567 with token sk_test_FAKEKEYFAKEKEY000000000000"
    result = sanitizer.sanitize(text)

    assert "alice@example.com" not in result
    assert "555-123-4567" not in result
    assert "sk_test_FAKEKEYFAKEKEY000000000000" not in result
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_PHONE]" in result
    assert "[REDACTED_API_KEY]" in result


def test_sanitize_dict_keys() -> None:
    """Should sanitize dictionary keys if they contain sensitive data."""
    sanitizer = DataSanitizer()

    data = {
        "user@example.com": "value1",
        "normal_key": "value2",
    }

    result = sanitizer.sanitize(data)

    # Email in key should be redacted
    assert "[REDACTED_EMAIL]" in result
    assert "user@example.com" not in result
    assert "normal_key" in result


def test_empty_string() -> None:
    """Should handle empty strings."""
    sanitizer = DataSanitizer()

    result = sanitizer.sanitize("")

    assert result == ""


def test_empty_dict() -> None:
    """Should handle empty dictionaries."""
    sanitizer = DataSanitizer()

    result = sanitizer.sanitize({})

    assert result == {}


def test_empty_list() -> None:
    """Should handle empty lists."""
    sanitizer = DataSanitizer()

    result = sanitizer.sanitize([])

    assert result == []


def test_mixed_safe_and_sensitive_data() -> None:
    """Should preserve safe data while redacting sensitive data."""
    sanitizer = DataSanitizer()

    data = {
        "public_info": "This is safe",
        "user_details": {
            "name": "Alice",
            "contact": "alice@example.com",
            "preferences": ["setting1", "setting2"],
        },
        "credentials": {
            "api_key": "sk_test_FAKEKEYFAKEKEY000000000000",
        },
    }

    result = sanitizer.sanitize(data)

    assert result["public_info"] == "This is safe"
    assert result["user_details"]["name"] == "Alice"
    assert result["user_details"]["preferences"] == ["setting1", "setting2"]
    assert "[REDACTED_EMAIL]" in result["user_details"]["contact"]
    assert "[REDACTED_API_KEY]" in result["credentials"]["api_key"]


def test_custom_pattern_list() -> None:
    """Should work with custom pattern list from initialization."""
    custom_patterns = [
        SensitivePattern(
            name="employee_id",
            pattern=re.compile(r'\bEMP\d{5}\b'),
            redaction="[REDACTED_EMP_ID]",
        )
    ]

    sanitizer = DataSanitizer(patterns=custom_patterns)

    text = "Employee EMP12345 has access"
    result = sanitizer.sanitize(text)

    assert "EMP12345" not in result
    assert "[REDACTED_EMP_ID]" in result
