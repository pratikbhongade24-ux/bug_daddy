"""
Autonomous Remediation Orchestration Layer.

This package implements the *Router-Supervisor Mesh* that sits in front of the
existing `incident_daddy / bug_daddy / reviewer_daddy / sme_agent` runtimes.

Architectural pillars
---------------------
1. **Trigger Ingestion Layer** — `runtime.ingestion`
2. **Event Normalization & Enrichment** — `runtime.normalization`
3. **Typed Incident Contracts** — `contracts`
4. **Agent Registry & Capability Discovery** — `routing.registry`
5. **Intelligent Routing Engine** — `routing.router`
6. **Priority & Severity Scheduler** — `runtime.scheduler`
7. **Async Agent Execution Runtime** — `runtime.executor`
8. **Remediation Feedback Loop** — `runtime.feedback`
9. **Audit & Observability Layer** — `observability`
10. **Failure Recovery / Rollback Handling** — `runtime.recovery`

Design tenets
-------------
* **Deterministic state-driven routing** minimizes remediation drift during
  concurrent incident escalation. The router is a pure function of
  `(NormalizedEvent, RegistrySnapshot)`; no hidden global state is mutated.
* **Typed incident contracts** eliminate orchestration ambiguity and improve
  autonomous recovery reproducibility — every transition is schema-validated.
* **Decoupled ingestion** guarantees telemetry durability even during
  downstream execution degradation; the ingestion queue is the system of
  record, not the agents.
* **Supervisor-mediated execution** ensures controlled agent autonomy with
  auditable rollback guarantees. Every effectful step emits a compensating
  action that the recovery layer can replay in reverse order.
* **Priority-aware scheduling** with weighted fair queues reduces cascading
  infrastructure instability during multi-vector failure scenarios.
"""

from .contracts import (
    AgentCapability,
    AgentOutcome,
    AgentStatus,
    IncidentClass,
    NormalizedEvent,
    RawTrigger,
    RemediationPlan,
    RemediationStep,
    SeverityTier,
    StepStatus,
    TriggerSource,
)
from .orchestrator import RemediationOrchestrator, build_default_orchestrator

__all__ = [
    "AgentCapability",
    "AgentOutcome",
    "AgentStatus",
    "IncidentClass",
    "NormalizedEvent",
    "RawTrigger",
    "RemediationOrchestrator",
    "RemediationPlan",
    "RemediationStep",
    "SeverityTier",
    "StepStatus",
    "TriggerSource",
    "build_default_orchestrator",
]
