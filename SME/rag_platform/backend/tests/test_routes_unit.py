import pytest
from fastapi import HTTPException

from app.api.routes import _normalize_answer_text, _query_variants, messages, metrics


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def count(self):
        return len(self._rows)


class _FakeDb:
    def __init__(self, mapping):
        self.mapping = mapping

    def query(self, model):
        return _FakeQuery(self.mapping.get(model.__name__, []))


class _Obj:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_query_variants_removes_duplicate_whitespace_and_adds_term_variant():
    variants = _query_variants("  How   does onboarding service validate  documents? ")
    assert variants[0] == "How does onboarding service validate documents?"
    assert "onboarding service validate documents?" in variants
    assert len(variants) == 2


def test_normalize_answer_text_rewrites_localhost_urls_and_heading_spacing():
    out = _normalize_answer_text("##Overview\nUse localhost:8005 and http://localhost:3000 \r\n")
    assert out.startswith("## Overview")
    assert "Transaction Management Service" in out
    assert "BugDaddy Dashboard" in out


def test_messages_raises_404_when_conversation_not_found():
    db = _FakeDb({"Conversation": []})
    with pytest.raises(HTTPException) as exc:
        messages(conversation_id=1, external_user_id="u1", _="key", db=db)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Conversation not found"


def test_metrics_computes_message_latency_tokens_and_failures():
    message_rows = [
        _Obj(latency_ms=100, tokens_in=10, tokens_out=20),
        _Obj(latency_ms=200, tokens_in=5, tokens_out=15),
    ]
    failed_audits = [_Obj(status="failed"), _Obj(status="failed")]
    db = _FakeDb({"Message": message_rows, "AuditLog": failed_audits})

    out = metrics(_="key", db=db)

    assert out["messages"] == 2
    assert out["avg_latency_ms"] == 150
    assert out["token_usage_proxy"] == 50
    assert out["failures"] == 2
