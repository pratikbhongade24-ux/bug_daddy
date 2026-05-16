"""
HTTP client for the SME RAG platform (``SME/rag_platform``).

Contract (from ``SME/rag_platform/backend/app/api/routes.py``):

  POST /api/v1/chat/stream
    Headers: x-api-key: <WIDGET_API_KEY>
    Body:    {
      "conversation_id": int | null,
      "external_user_id": str,
      "session_id": str,
      "question": str,
      "filters": { ... } | null
    }
    Response: Server-Sent Events stream:
      event: meta   data: {"conversation_id": <int>, "message_id": <int>}
      event: token  data: {"text": "<word> "}    (zero or more)
      event: done   data: {}

  GET /api/v1/messages/{conversation_id}?external_user_id=...
    Headers: x-api-key: <WIDGET_API_KEY>
    Response: JSON list of messages + citations

The client streams the chat answer, reassembles it from token events,
optionally fetches citations from the messages endpoint, and returns a
single ``RetrievalResult`` envelope.

The client is fully synchronous because the SME runtime that calls it
is itself synchronous (it lives behind a Strands agent). Putting an
async wrapper here would just complicate the call site without
unlocking any concurrency.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Config + result types.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SMERagConfig:
    """Connection parameters for the SME RAG platform.

    ``base_url`` should point at the API root (``/api/v1`` is appended
    by the client). ``api_key`` is the ``x-api-key`` value the platform
    requires on every endpoint. Disabled defaults so missing config
    results in a no-op client rather than a hard failure at import."""

    base_url: str = ""
    api_key: str = ""
    timeout_seconds: float = 10.0
    fetch_citations: bool = True
    enabled: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> SMERagConfig:
        import os
        e = env if env is not None else os.environ
        base = (e.get("SME_RAG_URL") or "").rstrip("/")
        key = e.get("SME_RAG_API_KEY") or ""
        timeout = float(e.get("SME_RAG_TIMEOUT_SECONDS") or 10.0)
        fetch_citations = (e.get("SME_RAG_FETCH_CITATIONS", "true").lower() != "false")
        enabled = bool(base) and bool(key)
        return cls(
            base_url=base,
            api_key=key,
            timeout_seconds=timeout,
            fetch_citations=fetch_citations,
            enabled=enabled,
        )


@dataclass
class RetrievalResult:
    """Outcome of a single SME RAG retrieval call.

    ``answer`` is the *additive* enrichment text — empty string when
    retrieval failed or the platform returned nothing. ``citations``
    carries the per-chunk provenance retrieved from the messages
    endpoint. ``diagnostics`` is always populated so callers can audit
    why retrieval did or didn't contribute."""

    answer: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    conversation_id: int | None = None
    message_id: int | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def has_content(self) -> bool:
        return bool(self.answer.strip())


class SMERetrievalError(RuntimeError):
    """Raised internally — never surfaces past ``SMERagClient.query``."""


# ---------------------------------------------------------------------------
# Client.
# ---------------------------------------------------------------------------


class SMERagClient:
    """Thin synchronous client over the SME RAG platform.

    The client is intentionally dependency-free (stdlib ``urllib`` only)
    so the agent package picks up no new install-time deps. Production
    callers wanting connection pooling or async fan-out can subclass
    and override ``_post_stream`` / ``_get_json``."""

    def __init__(self, config: SMERagConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public surface.
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        question: str,
        external_user_id: str,
        session_id: str,
        filters: dict[str, Any] | None = None,
        conversation_id: int | None = None,
    ) -> RetrievalResult:
        """Retrieve an enrichment answer for ``question``.

        Never raises. Failure modes are converted to a ``RetrievalResult``
        with ``answer=""`` and a populated ``diagnostics.status``."""
        if not self.config.enabled:
            return RetrievalResult(
                diagnostics={"status": "disabled", "reason": "SME_RAG_URL / SME_RAG_API_KEY not set"},
            )

        started = time.monotonic()
        try:
            meta, answer = self._post_stream(
                question=question,
                external_user_id=external_user_id,
                session_id=session_id,
                filters=filters,
                conversation_id=conversation_id,
            )
        except SMERetrievalError as exc:
            return RetrievalResult(
                diagnostics={
                    "status": "error",
                    "error": str(exc),
                    "latency_ms": int((time.monotonic() - started) * 1000),
                },
            )

        citations: list[dict[str, Any]] = []
        cit_diag: dict[str, Any] = {}
        if self.config.fetch_citations and meta.get("conversation_id"):
            try:
                citations = self._fetch_citations(
                    conversation_id=int(meta["conversation_id"]),
                    external_user_id=external_user_id,
                    message_id=int(meta.get("message_id") or 0) or None,
                )
            except SMERetrievalError as exc:
                cit_diag = {"citations_error": str(exc)}

        return RetrievalResult(
            answer=answer.strip(),
            citations=citations,
            conversation_id=int(meta.get("conversation_id")) if meta.get("conversation_id") else None,
            message_id=int(meta.get("message_id")) if meta.get("message_id") else None,
            diagnostics={
                "status": "ok",
                "latency_ms": int((time.monotonic() - started) * 1000),
                "tokens_received": len(answer.split()),
                **cit_diag,
            },
        )

    # ------------------------------------------------------------------
    # Internals (override-friendly).
    # ------------------------------------------------------------------

    def _post_stream(
        self,
        *,
        question: str,
        external_user_id: str,
        session_id: str,
        filters: dict[str, Any] | None,
        conversation_id: int | None,
    ) -> tuple[dict[str, Any], str]:
        payload = {
            "conversation_id": conversation_id,
            "external_user_id": external_user_id,
            "session_id": session_id,
            "question": question,
            "filters": filters or None,
        }
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.config.base_url}/api/v1/chat/stream"
        request = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "x-api-key": self.config.api_key,
            },
        )

        meta: dict[str, Any] = {}
        tokens: list[str] = []
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                if response.status != 200:
                    raise SMERetrievalError(f"http_{response.status}")
                for event_name, event_data in _iter_sse(response):
                    if event_name == "meta":
                        meta = _safe_json(event_data) or {}
                    elif event_name == "token":
                        token = (_safe_json(event_data) or {}).get("text")
                        if isinstance(token, str):
                            tokens.append(token)
                    elif event_name == "done":
                        break
        except urllib.error.HTTPError as exc:
            raise SMERetrievalError(f"http_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SMERetrievalError(f"network:{exc.reason}") from exc
        except TimeoutError as exc:
            raise SMERetrievalError("timeout") from exc

        return meta, "".join(tokens)

    def _fetch_citations(
        self,
        *,
        conversation_id: int,
        external_user_id: str,
        message_id: int | None,
    ) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"external_user_id": external_user_id})
        url = f"{self.config.base_url}/api/v1/messages/{conversation_id}?{query}"
        request = urllib.request.Request(
            url=url,
            method="GET",
            headers={"Accept": "application/json", "x-api-key": self.config.api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                if response.status != 200:
                    raise SMERetrievalError(f"http_{response.status}")
                payload = _safe_json(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raise SMERetrievalError(f"http_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SMERetrievalError(f"network:{exc.reason}") from exc

        if not isinstance(payload, list):
            return []
        # Find the assistant message we care about and lift its citations.
        for msg in payload:
            if not isinstance(msg, dict):
                continue
            if message_id is not None and msg.get("id") != message_id:
                continue
            if msg.get("role") != "assistant":
                continue
            cits = msg.get("citations") or []
            return [c for c in cits if isinstance(c, dict)]
        return []


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _safe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _iter_sse(response) -> list[tuple[str, str]]:
    """Decode a Server-Sent Events stream into a list of (event, data) tuples.

    SSE events are separated by a blank line. Each event has one or more
    ``field: value`` lines. We only care about ``event:`` and ``data:``.

    Returns a list (not a generator) because the response is fully drained
    before the caller acts on it — the SME platform yields a small bounded
    number of events per query so memory is not a concern."""
    events: list[tuple[str, str]] = []
    current_event = "message"
    current_data: list[str] = []
    for raw_line in response:
        line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            if current_data:
                events.append((current_event, "\n".join(current_data)))
            current_event = "message"
            current_data = []
            continue
        if line.startswith(":"):  # SSE comment / keep-alive
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data.append(line[len("data:"):].lstrip())
    if current_data:
        events.append((current_event, "\n".join(current_data)))
    return events


# ---------------------------------------------------------------------------
# Convenience constructor.
# ---------------------------------------------------------------------------


def build_default_client(env: dict[str, str] | None = None) -> SMERagClient:
    """Construct a client from env vars. Always returns a usable instance —
    when env is incomplete, the returned client is disabled and ``query()``
    short-circuits with a diagnostics record."""
    return SMERagClient(config=SMERagConfig.from_env(env))
