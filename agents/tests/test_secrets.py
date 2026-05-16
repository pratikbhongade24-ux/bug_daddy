"""Secrets management tests.

Covers the three guarantees the module makes:
- typed retrieval with structured errors
- redaction by registered value
- redaction by sensitive key name
"""

from __future__ import annotations

import pytest

from agentic_solution.secrets import (
    REDACTED,
    MissingSecretError,
    Secrets,
    default_secrets,
    reset_default_secrets,
)


class TestRequire:
    def test_returns_present_values(self):
        s = Secrets(source={"A": "1", "B": "2"})
        assert s.require("A", "B") == {"A": "1", "B": "2"}

    def test_raises_with_every_missing_name(self):
        s = Secrets(source={"A": "1"})
        with pytest.raises(MissingSecretError) as exc:
            s.require("A", "B", "C")
        assert set(exc.value.missing) == {"B", "C"}

    def test_treats_empty_string_as_missing(self):
        """A blank env value is functionally absent — we want the same
        loud failure for ``X=`` as for ``X`` unset."""
        s = Secrets(source={"A": ""})
        with pytest.raises(MissingSecretError):
            s.require("A")

    def test_get_does_not_raise_for_missing(self):
        s = Secrets(source={})
        assert s.get("X") is None
        assert s.get("X", "default") == "default"


class TestRedaction:
    def test_redacts_string_matching_registered_value(self):
        s = Secrets(source={"TOKEN": "abc123"})
        s.require("TOKEN")
        out = s.redact({"safe": "hello", "leaked": "abc123"})
        assert out == {"safe": "hello", "leaked": REDACTED}

    def test_redacts_value_under_sensitive_key_name(self):
        """Catch the case where a secret leaks under a benign-looking
        value but a sensitive-looking *key* — e.g. ``{"api_key": "xyz"}``
        with ``xyz`` not yet registered."""
        s = Secrets()
        out = s.redact({"api_key": "freshly-rotated"})
        assert out == {"api_key": REDACTED}

    def test_redacts_nested_structures(self):
        s = Secrets(source={"P": "pw1234"})
        s.require("P")
        payload = {
            "outer": [
                {"creds": {"password": "irrelevant", "user": "ok"}},
                "pw1234",
                ("pw1234", "safe"),
            ]
        }
        out = s.redact(payload)
        assert out == {
            "outer": [
                {"creds": {"password": REDACTED, "user": "ok"}},
                REDACTED,
                (REDACTED, "safe"),
            ]
        }

    def test_redacts_keys_using_multiple_naming_conventions(self):
        s = Secrets()
        for key in (
            "TOKEN", "secret", "AWS_SECRET_ACCESS_KEY",
            "private-key", "AUTHORIZATION", "api-key",
        ):
            assert s.redact({key: "v"})[key] == REDACTED, key

    def test_does_not_redact_benign_payloads(self):
        s = Secrets()
        assert s.redact({"x": 1, "y": "hello", "list": [1, 2]}) == {
            "x": 1, "y": "hello", "list": [1, 2],
        }

    def test_register_value_marks_runtime_secret(self):
        """For secrets minted at runtime (signed tokens, presigned URLs)."""
        s = Secrets()
        s.register_value("Bearer eyJ...")
        out = s.redact({"x_request_id": "Bearer eyJ..."})
        assert out["x_request_id"] == REDACTED


class TestDefaultSingleton:
    def test_default_secrets_is_cached(self):
        reset_default_secrets()
        assert default_secrets() is default_secrets()

    def test_reset_clears_singleton(self):
        first = default_secrets()
        reset_default_secrets()
        second = default_secrets()
        assert first is not second
