"""
Retrieval-Augmented Generation (RAG) integration for the SME agent.

The SME agent in ``agents/`` is the consumer side of the standalone
``SME/rag_platform`` service (FastAPI + pgvector + Bedrock embeddings,
deployed independently). This package contains the thin client that
calls that service from inside the agent runtime.

Design intent:

* **Additive, never substitutive.** The SME runtime always produces its
  stub answer first (repository + branch hint, inline KB context). The
  RAG client's output is *appended* on top so a retrieval failure
  degrades gracefully — the operator still sees a useful response.

* **Dependency-free.** Uses ``urllib`` from the stdlib so the agent
  package picks up no new install-time deps. The platform side already
  owns FastAPI, pgvector, and Bedrock.

* **Fail-loud diagnostics, fail-soft answers.** Every error path is
  captured in ``RetrievalResult.diagnostics`` (status, latency, error
  class) so post-mortems can attribute SME quality regressions to
  retrieval health, but the SME response never raises past its
  boundary.

* **Redaction-aware.** When the secrets module is registered, the
  client redacts its own diagnostic payload before returning it so
  API keys cannot leak into the audit journal.
"""

from .client import (
    RetrievalResult,
    SMERagClient,
    SMERagConfig,
    SMERetrievalError,
    build_default_client,
)

__all__ = [
    "RetrievalResult",
    "SMERagClient",
    "SMERagConfig",
    "SMERetrievalError",
    "build_default_client",
]
