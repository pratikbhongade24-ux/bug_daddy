"""
Tests for the SME RAG HTTP client.

Three slices are covered:

1. **Config** — env-driven construction, enabled flag semantics.
2. **Happy path** — SSE drained, meta + tokens reassembled, citations
   fetched, ``RetrievalResult.has_content`` true.
3. **Failure modes** — HTTP errors, timeouts, network errors, citation
   fetch failures: every one returns a structured ``RetrievalResult``
   rather than raising.

The client is tested by replacing ``urllib.request.urlopen`` with a
context-manager fake that yields a fixed byte sequence. No network
traffic, no FastAPI fixture, no flakiness.
"""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from agentic_solution.rag import (
    RetrievalResult,
    SMERagClient,
    SMERagConfig,
    build_default_client,
)

# ---------------------------------------------------------------------------
# urlopen fake.
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for the ``http.client.HTTPResponse`` returned by
    ``urlopen``. Supports both line-iteration (used by the SSE reader) and
    ``.read()`` (used by the citations fetch)."""

    def __init__(self, *, status: int = 200, body: bytes = b"", lines: list[bytes] | None = None):
        self.status = status
        self._body = body
        self._lines = lines or []

    def __iter__(self):
        return iter(self._lines) if self._lines else iter(io.BytesIO(self._body))

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _sse(events: list[tuple[str, dict[str, Any]]]) -> list[bytes]:
    """Encode a list of (event_name, data_obj) tuples into SSE bytes."""
    lines: list[bytes] = []
    for name, data in events:
        lines.append(f"event: {name}\n".encode())
        lines.append(f"data: {json.dumps(data)}\n".encode())
        lines.append(b"\n")
    return lines


# ---------------------------------------------------------------------------
# Config.
# ---------------------------------------------------------------------------


class TestSMERagConfig:
    def test_disabled_when_url_missing(self):
        cfg = SMERagConfig.from_env({"SME_RAG_API_KEY": "k"})
        assert cfg.enabled is False

    def test_disabled_when_key_missing(self):
        cfg = SMERagConfig.from_env({"SME_RAG_URL": "http://x"})
        assert cfg.enabled is False

    def test_enabled_with_both_set(self):
        cfg = SMERagConfig.from_env({"SME_RAG_URL": "http://x", "SME_RAG_API_KEY": "k"})
        assert cfg.enabled is True
        assert cfg.base_url == "http://x"
        assert cfg.api_key == "k"

    def test_trailing_slash_stripped(self):
        cfg = SMERagConfig.from_env({"SME_RAG_URL": "http://x/", "SME_RAG_API_KEY": "k"})
        assert cfg.base_url == "http://x"

    def test_fetch_citations_default_true(self):
        cfg = SMERagConfig.from_env({"SME_RAG_URL": "http://x", "SME_RAG_API_KEY": "k"})
        assert cfg.fetch_citations is True

    def test_fetch_citations_opt_out(self):
        cfg = SMERagConfig.from_env({
            "SME_RAG_URL": "http://x",
            "SME_RAG_API_KEY": "k",
            "SME_RAG_FETCH_CITATIONS": "false",
        })
        assert cfg.fetch_citations is False

    def test_timeout_parsed(self):
        cfg = SMERagConfig.from_env({
            "SME_RAG_URL": "http://x",
            "SME_RAG_API_KEY": "k",
            "SME_RAG_TIMEOUT_SECONDS": "3.5",
        })
        assert cfg.timeout_seconds == 3.5


# ---------------------------------------------------------------------------
# Disabled client short-circuit.
# ---------------------------------------------------------------------------


class TestDisabledClient:
    def test_disabled_client_short_circuits(self):
        client = SMERagClient(SMERagConfig())
        result = client.query(
            question="anything",
            external_user_id="u",
            session_id="s",
        )
        assert isinstance(result, RetrievalResult)
        assert result.answer == ""
        assert result.diagnostics["status"] == "disabled"

    def test_build_default_client_uses_env(self, monkeypatch):
        monkeypatch.setenv("SME_RAG_URL", "http://x")
        monkeypatch.setenv("SME_RAG_API_KEY", "k")
        client = build_default_client()
        assert client.config.enabled is True


# ---------------------------------------------------------------------------
# Happy path.
# ---------------------------------------------------------------------------


@pytest.fixture
def enabled_client():
    return SMERagClient(SMERagConfig(
        base_url="http://rag.local",
        api_key="key",
        timeout_seconds=5.0,
        fetch_citations=True,
        enabled=True,
    ))


class TestQuerySuccess:
    def test_drains_sse_and_assembles_answer(self, enabled_client, monkeypatch):
        chat_response = _FakeResponse(lines=_sse([
            ("meta", {"conversation_id": 7, "message_id": 42}),
            ("token", {"text": "KYC "}),
            ("token", {"text": "service "}),
            ("token", {"text": "owns "}),
            ("token", {"text": "PAN "}),
            ("token", {"text": "verification."}),
            ("done", {}),
        ]))
        messages_body = json.dumps([
            {
                "id": 42,
                "role": "assistant",
                "citations": [
                    {"source_name": "kyc_service.md", "score": 0.91, "content": "PAN..."},
                    {"source_name": "runbook.md", "score": 0.74, "content": "verify..."},
                ],
            }
        ]).encode("utf-8")

        calls: list[Any] = []

        def fake_urlopen(request, timeout):
            calls.append((request.full_url, request.get_method()))
            if "/chat/stream" in request.full_url:
                return chat_response
            return _FakeResponse(status=200, body=messages_body)

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        result = enabled_client.query(
            question="who owns kyc?",
            external_user_id="incident_daddy",
            session_id="corr-1",
        )

        assert result.has_content
        assert "KYC service owns PAN verification." == result.answer
        assert result.conversation_id == 7
        assert result.message_id == 42
        assert len(result.citations) == 2
        assert result.diagnostics["status"] == "ok"
        # Both endpoints called.
        assert any("/chat/stream" in url for url, _ in calls)
        assert any("/messages/7" in url for url, _ in calls)

    def test_authorization_header_sent(self, enabled_client, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_urlopen(request, timeout):
            captured["api_key"] = request.headers.get("X-api-key")
            return _FakeResponse(lines=_sse([
                ("meta", {"conversation_id": 1, "message_id": 1}),
                ("done", {}),
            ]))

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        enabled_client.query(question="q", external_user_id="u", session_id="s")
        assert captured["api_key"] == "key"

    def test_filters_round_trip(self, enabled_client, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_urlopen(request, timeout):
            if request.get_method() == "POST":
                captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse(lines=_sse([
                ("meta", {"conversation_id": 1, "message_id": 1}),
                ("done", {}),
            ]))

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        enabled_client.query(
            question="q",
            external_user_id="u",
            session_id="s",
            filters={"service_name": "kyc_service"},
        )
        assert captured["body"]["filters"] == {"service_name": "kyc_service"}

    def test_skip_citations_when_disabled(self, monkeypatch):
        client = SMERagClient(SMERagConfig(
            base_url="http://r.local",
            api_key="k",
            fetch_citations=False,
            enabled=True,
        ))
        urls: list[str] = []

        def fake_urlopen(request, timeout):
            urls.append(request.full_url)
            return _FakeResponse(lines=_sse([
                ("meta", {"conversation_id": 1, "message_id": 1}),
                ("token", {"text": "ok"}),
                ("done", {}),
            ]))

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        result = client.query(question="q", external_user_id="u", session_id="s")
        assert result.citations == []
        assert all("/messages/" not in u for u in urls)


# ---------------------------------------------------------------------------
# Failure modes — every one must produce a soft fallback.
# ---------------------------------------------------------------------------


class TestQueryFailureModes:
    def test_http_error_records_status_and_returns_empty_answer(self, enabled_client, monkeypatch):
        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 503, "service unavailable", hdrs={}, fp=None
            )

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        result = enabled_client.query(question="q", external_user_id="u", session_id="s")
        assert result.answer == ""
        assert result.diagnostics["status"] == "error"
        assert "http_503" in result.diagnostics["error"]

    def test_network_error_returns_soft_failure(self, enabled_client, monkeypatch):
        def fake_urlopen(request, timeout):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        result = enabled_client.query(question="q", external_user_id="u", session_id="s")
        assert result.answer == ""
        assert result.diagnostics["status"] == "error"
        assert "network" in result.diagnostics["error"]

    def test_timeout_returns_soft_failure(self, enabled_client, monkeypatch):
        def fake_urlopen(request, timeout):
            raise TimeoutError("read timed out")

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        result = enabled_client.query(question="q", external_user_id="u", session_id="s")
        assert result.diagnostics["error"] == "timeout"

    def test_citation_fetch_failure_does_not_drop_answer(self, enabled_client, monkeypatch):
        """Chat succeeded; citations endpoint failed — we still return the
        answer with a recorded citation error, never empty."""
        chat_response = _FakeResponse(lines=_sse([
            ("meta", {"conversation_id": 3, "message_id": 9}),
            ("token", {"text": "answer"}),
            ("done", {}),
        ]))

        def fake_urlopen(request, timeout):
            if "/chat/stream" in request.full_url:
                return chat_response
            raise urllib.error.HTTPError(
                request.full_url, 500, "internal", hdrs={}, fp=None
            )

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        result = enabled_client.query(question="q", external_user_id="u", session_id="s")
        assert result.has_content
        assert result.answer == "answer"
        assert "citations_error" in result.diagnostics
        assert result.citations == []

    def test_malformed_sse_returns_empty_string_without_raising(self, enabled_client, monkeypatch):
        """Garbage in the data field of an event must be tolerated."""
        bad_lines = [
            b"event: meta\n",
            b"data: not-json{\n",
            b"\n",
            b"event: done\n",
            b"data: {}\n",
            b"\n",
        ]

        def fake_urlopen(request, timeout):
            return _FakeResponse(lines=bad_lines)

        monkeypatch.setattr("agentic_solution.rag.client.urllib.request.urlopen", fake_urlopen)

        result = enabled_client.query(question="q", external_user_id="u", session_id="s")
        assert result.answer == ""
        # status remains "ok" because the HTTP call succeeded; tokens just had nothing usable.
        assert result.diagnostics["status"] == "ok"
        assert result.diagnostics["tokens_received"] == 0
