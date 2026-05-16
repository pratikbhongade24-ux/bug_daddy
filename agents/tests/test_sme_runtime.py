"""
Tests for ``SMEAgentRuntime`` composition.

The runtime's job is to (a) always produce the stub answer, (b) append
retrieval enrichment when available, and (c) record retrieval health in
diagnostics. The tests below pin each invariant directly so a future
refactor cannot silently drop the stub or swallow retrieval errors."""

from __future__ import annotations

from typing import Any

import pytest

from agentic_solution.agents import SMEAgentBundle
from agentic_solution.config import AppConfig
from agentic_solution.rag import RetrievalResult, SMERagClient, SMERagConfig
from agentic_solution.services.sme import _STUB_ANSWER, SMEAgentRuntime

# ---------------------------------------------------------------------------
# Doubles.
# ---------------------------------------------------------------------------


class _FakeRagClient:
    """Stand-in for ``SMERagClient`` with a configurable return + capture."""

    def __init__(self, *, result: RetrievalResult, raises: BaseException | None = None):
        self._result = result
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    def query(self, *, question, external_user_id, session_id, filters=None, conversation_id=None):
        self.calls.append({
            "question": question,
            "external_user_id": external_user_id,
            "session_id": session_id,
            "filters": filters,
            "conversation_id": conversation_id,
        })
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.fixture(autouse=True)
def _patch_agent_builder(monkeypatch):
    """SMEAgentRuntime is a slots dataclass and ``_build_agents`` is a real
    method — patch at the class level so monkeypatch doesn't try to assign
    onto a non-existent instance ``__dict__``."""
    bundle = SMEAgentBundle(expert=object())
    monkeypatch.setattr(SMEAgentRuntime, "_build_agents", lambda self: bundle)
    return bundle


def _runtime(*, dry_run: bool = False, client: _FakeRagClient | SMERagClient | None = None) -> SMEAgentRuntime:
    cfg = AppConfig(dry_run=dry_run)
    bundle = SMEAgentBundle(expert=object())  # not invoked in handle()
    rag = client if client is not None else SMERagClient(SMERagConfig())
    return SMEAgentRuntime(config=cfg, agents=bundle, rag_client=rag)


def _payload(**overrides):
    base = {
        "question": "Who owns the KYC service?",
        "requested_by": "incident_daddy",
        "context": {
            "prompt": "KYC failures spiking",
            "service_name": "kyc_service",
            "metadata": {"correlation_id": "corr-42"},
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Stub-is-floor invariant.
# ---------------------------------------------------------------------------


class TestStubFloor:
    def test_disabled_rag_still_returns_stub(self):
        """No SME_RAG env → client disabled → only stub answer flows through."""
        rt = _runtime()  # default SMERagClient with disabled config
        out = rt.handle(_payload())
        assert out["summary"] == _STUB_ANSWER
        assert out["diagnostics"]["rag"]["status"] == "disabled"

    def test_dry_run_appends_stub_to_dry_run_text(self):
        rt = _runtime(dry_run=True)
        out = rt.handle(_payload())
        assert _STUB_ANSWER in out["summary"]
        assert "Dry run only" in out["summary"]
        assert out["diagnostics"]["rag"]["status"] == "skipped_dry_run"

    def test_retrieval_failure_does_not_drop_stub(self):
        """Even an unexpected exception inside the client falls through to stub."""
        fake = _FakeRagClient(result=RetrievalResult(), raises=RuntimeError("explode"))
        rt = _runtime(client=fake)
        out = rt.handle(_payload())
        assert out["summary"] == _STUB_ANSWER
        assert out["diagnostics"]["rag"]["status"] == "unexpected_error"
        assert "explode" in out["diagnostics"]["rag"]["error"]

    def test_empty_retrieval_returns_stub_only(self):
        fake = _FakeRagClient(result=RetrievalResult(diagnostics={"status": "ok"}))
        rt = _runtime(client=fake)
        out = rt.handle(_payload())
        assert out["summary"] == _STUB_ANSWER  # no enrichment appended


# ---------------------------------------------------------------------------
# Additive enrichment.
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_rag_answer_appended_under_header(self):
        fake = _FakeRagClient(result=RetrievalResult(
            answer="KYC ownership lives in the platform team's runbook.",
            citations=[{"source_name": "kyc_service.md", "score": 0.91}],
            conversation_id=11,
            message_id=22,
            diagnostics={"status": "ok", "latency_ms": 120},
        ))
        rt = _runtime(client=fake)
        out = rt.handle(_payload())

        # Stub always leads.
        assert out["summary"].startswith(_STUB_ANSWER)
        # Enrichment appended under a clearly labelled header.
        assert "RAG context" in out["summary"]
        assert "KYC ownership lives" in out["summary"]
        # Citations lifted into references.
        types = [r["type"] for r in out["references"]]
        assert "rag_citation" in types
        assert "service_name" in types  # stub references preserved
        # Diagnostics carry retrieval health.
        assert out["diagnostics"]["rag"]["latency_ms"] == 120
        assert out["diagnostics"]["rag_conversation_id"] == 11

    def test_service_filter_round_trips_to_client(self):
        fake = _FakeRagClient(result=RetrievalResult())
        rt = _runtime(client=fake)
        rt.handle(_payload())
        assert fake.calls[0]["filters"] == {"service_name": "kyc_service"}

    def test_no_filter_when_service_unknown(self):
        fake = _FakeRagClient(result=RetrievalResult())
        rt = _runtime(client=fake)
        payload = _payload()
        payload["context"]["service_name"] = None
        rt.handle(payload)
        assert fake.calls[0]["filters"] is None

    def test_correlation_id_becomes_session(self):
        """Repeated SME queries about the same incident must share a session
        on the RAG side so the conversation history compounds."""
        fake = _FakeRagClient(result=RetrievalResult())
        rt = _runtime(client=fake)
        rt.handle(_payload())
        assert fake.calls[0]["session_id"] == "corr-42"

    def test_session_falls_back_to_requester(self):
        fake = _FakeRagClient(result=RetrievalResult())
        rt = _runtime(client=fake)
        payload = _payload()
        payload["context"]["metadata"] = {}
        rt.handle(payload)
        assert fake.calls[0]["session_id"] == "sme:incident_daddy"

    def test_external_user_id_is_requester(self):
        fake = _FakeRagClient(result=RetrievalResult())
        rt = _runtime(client=fake)
        rt.handle(_payload())
        assert fake.calls[0]["external_user_id"] == "incident_daddy"


# ---------------------------------------------------------------------------
# Diagnostics propagation.
# ---------------------------------------------------------------------------


class TestDiagnostics:
    @pytest.mark.parametrize("rag_status", ["ok", "error", "disabled", "skipped_dry_run"])
    def test_status_surfaces_in_response(self, rag_status):
        fake = _FakeRagClient(result=RetrievalResult(diagnostics={"status": rag_status}))
        rt = _runtime(client=fake)
        out = rt.handle(_payload())
        assert out["diagnostics"]["rag"]["status"] == rag_status

    def test_model_id_recorded(self):
        rt = _runtime()
        out = rt.handle(_payload())
        assert "model_id" in out["diagnostics"]
