"""
Typed Incident Contracts — the canonical schema layer of the orchestrator.

The contracts module is intentionally the *only* place in the orchestrator
that defines cross-boundary shapes. Every other module is forced to operate
against these strongly-typed envelopes. This is what we mean by
"orchestration determinism": agents cannot disagree about what an incident
*is* because the type system forbids the disagreement at the boundary.

Three layers of truth
---------------------
* ``RawTrigger``        — bytes-on-the-wire from any upstream source.
* ``NormalizedEvent``   — enriched, deduplicated, severity-scored envelope.
* ``RemediationPlan``   — supervisor-issued execution graph with compensating
                          actions for every effectful step.

Severity model
--------------
We use a five-tier scale aligned with industry incident classifications
(SEV0..SEV4) rather than a raw integer to keep routing decisions
unambiguous. The numeric weight is exposed for the priority scheduler.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations — closed sets that the router can pattern-match against.
# ---------------------------------------------------------------------------


class TriggerSource(str, enum.Enum):
    """Upstream systems we accept signals from. Closed set on purpose —
    unknown sources are quarantined at the ingestion layer rather than
    silently coerced, which preserves auditability."""

    CLOUDWATCH = "cloudwatch"
    PROMETHEUS = "prometheus"
    DATADOG = "datadog"
    GRAFANA = "grafana"
    PAGERDUTY = "pagerduty"
    GUARDDUTY = "guardduty"
    SECURITY_HUB = "security_hub"
    WAF = "waf"
    IDS = "ids"
    SNYK = "snyk"
    TRIVY = "trivy"
    GITHUB = "github"
    JIRA = "jira"
    SLACK = "slack"
    SYNTHETIC = "synthetic"
    MANUAL = "manual"


class IncidentClass(str, enum.Enum):
    """The deterministic incident taxonomy. The router maps every
    NormalizedEvent to *exactly one* primary class; multi-class events are
    forked at the supervisor, never at the router, so classification stays
    a pure function."""

    CPU_SPIKE = "cpu_spike"
    MEMORY_PRESSURE = "memory_pressure"
    DATABASE_SATURATION = "database_saturation"
    SERVICE_DOWNTIME = "service_downtime"
    ELEVATED_ERROR_RATE = "elevated_error_rate"
    FAILED_DEPLOYMENT = "failed_deployment"
    CVE_VULNERABILITY = "cve_vulnerability"
    SUSPICIOUS_IAM = "suspicious_iam_activity"
    UNAUTHORIZED_API_ACCESS = "unauthorized_api_access"
    WAF_ANOMALY = "waf_anomaly"
    IDS_ANOMALY = "ids_anomaly"
    TLS_EXPIRY = "tls_certificate_expiry"
    CLOUD_MISCONFIG = "cloud_misconfiguration"
    RANSOMWARE_INDICATOR = "ransomware_indicator"
    UNKNOWN = "unknown"


class SeverityTier(str, enum.Enum):
    """Five-tier severity scale. Maps to scheduler weights and SLA budgets."""

    SEV0 = "sev0"  # Catastrophic / multi-tenant outage / active intrusion
    SEV1 = "sev1"  # Major user-impacting outage
    SEV2 = "sev2"  # Partial degradation
    SEV3 = "sev3"  # Latent risk / capacity warning
    SEV4 = "sev4"  # Informational / hygiene

    @property
    def weight(self) -> int:
        """Scheduler weight: higher = more urgent. Used by the weighted-fair
        queue to bound starvation of low-severity work under sustained
        SEV0/SEV1 load."""
        return {
            SeverityTier.SEV0: 100,
            SeverityTier.SEV1: 60,
            SeverityTier.SEV2: 25,
            SeverityTier.SEV3: 8,
            SeverityTier.SEV4: 1,
        }[self]

    @property
    def sla_seconds(self) -> int:
        """Default time-to-acknowledge SLA in seconds. The recovery layer
        treats SLA breach as a first-class signal."""
        return {
            SeverityTier.SEV0: 60,
            SeverityTier.SEV1: 300,
            SeverityTier.SEV2: 1800,
            SeverityTier.SEV3: 14400,
            SeverityTier.SEV4: 86400,
        }[self]


class AgentStatus(str, enum.Enum):
    """Lifecycle states for a remediation agent registration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CIRCUIT_OPEN = "circuit_open"
    DRAINING = "draining"
    DISABLED = "disabled"


class StepStatus(str, enum.Enum):
    """Lifecycle states for a single remediation step within a plan."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    COMPENSATED = "compensated"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


# ---------------------------------------------------------------------------
# Wire envelopes.
# ---------------------------------------------------------------------------


class RawTrigger(BaseModel):
    """Lowest-trust envelope — whatever the upstream emitted, as-is.

    The ingestion layer is responsible for two things: durably persisting
    this object before any processing, and producing a `NormalizedEvent`
    from it. Anything past ingestion sees only `NormalizedEvent`."""

    model_config = ConfigDict(extra="allow")

    source: TriggerSource
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]
    correlation_hint: str | None = Field(
        default=None,
        description=(
            "Optional upstream correlation token (e.g. CloudWatch alarm name, "
            "PagerDuty incident_key). Used to deduplicate signal storms at "
            "the ingestion gate before normalization."
        ),
    )

    @field_validator("payload")
    @classmethod
    def _payload_is_dict(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("payload must be a JSON object")
        return value


class NormalizedEvent(BaseModel):
    """The canonical envelope flowing through the rest of the system.

    Carries an immutable `event_id`, a deterministic `correlation_id` that
    survives deduplication, and a fingerprint that the deduplicator uses
    to fold redundant signals. Severity is a *scored* result of the
    normalization layer, not a passthrough of upstream severity text —
    upstream severities are too inconsistent to be used as truth."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = Field(
        ...,
        description=(
            "Stable across deduplicated and re-fired signals describing the "
            "same underlying incident. The supervisor groups all execution "
            "state under this key."
        ),
    )
    fingerprint: str = Field(
        ...,
        description=(
            "Content-derived hash used to fold duplicate signals within the "
            "deduplication window. Distinct from correlation_id so that a "
            "*recurring* incident can re-open under a new correlation."
        ),
    )
    source: TriggerSource
    incident_class: IncidentClass
    severity: SeverityTier
    received_at: datetime
    normalized_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service: str | None = None
    environment: Literal["prod", "staging", "dev", "unknown"] = "unknown"
    region: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    indicators: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    enrichment: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent contracts — what an agent declares and what it returns.
# ---------------------------------------------------------------------------


class AgentCapability(BaseModel):
    """Manifest of a remediation agent. Read by the registry at
    registration time and consumed by the router on every dispatch.

    The capability manifest is treated as immutable per agent version; if
    an agent's surface changes, it should re-register under a bumped
    version rather than mutating the existing entry. This keeps the
    routing decision reproducible from `(event, registry_snapshot)`."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str = "1.0.0"
    description: str
    handles: tuple[IncidentClass, ...]
    min_severity: SeverityTier = SeverityTier.SEV4
    requires_human_approval_at: SeverityTier | None = Field(
        default=None,
        description=(
            "If set, the supervisor must obtain explicit human approval "
            "before dispatching this agent at this severity or worse. "
            "Used for high-blast-radius actions like ransomware quarantine."
        ),
    )
    concurrency: int = Field(default=4, ge=1, le=64)
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    cost_weight: float = Field(
        default=1.0,
        ge=0.0,
        description=(
            "Relative cost (latency + spend + risk) of dispatching this "
            "agent. The router prefers lower-cost agents when multiple "
            "agents tie on capability match."
        ),
    )
    tags: tuple[str, ...] = ()


class RemediationStep(BaseModel):
    """A single supervised unit of work inside a remediation plan."""

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent: str
    intent: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 30.0
    max_retries: int = 2
    compensating_intent: str | None = Field(
        default=None,
        description=(
            "Name of the inverse intent this agent exposes for rollback. "
            "If null, the step is treated as non-effectful (no rollback "
            "needed). Recovery layer replays compensations in LIFO order."
        ),
    )
    depends_on: tuple[str, ...] = ()
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: dict[str, Any] | None = None
    error: str | None = None


class RemediationPlan(BaseModel):
    """Supervisor-issued execution graph for a single correlation_id."""

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str
    incident_class: IncidentClass
    severity: SeverityTier
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    steps: list[RemediationStep]
    primary_agent: str
    fallback_agents: tuple[str, ...] = ()
    requires_human_approval: bool = False
    notes: str | None = None


class AgentOutcome(BaseModel):
    """Return envelope from every agent invocation. Agents MUST NOT raise
    past the runtime boundary; uncaught exceptions are caught by the
    executor and converted to `AgentOutcome(success=False, ...)` so that
    the supervisor sees a uniform contract."""

    agent: str
    step_id: str
    success: bool
    started_at: datetime
    finished_at: datetime
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    compensating_handle: str | None = Field(
        default=None,
        description=(
            "Opaque token the agent returns so the recovery layer can "
            "later invoke the compensating intent without re-deriving "
            "side-effect state."
        ),
    )
    metrics: dict[str, float] = Field(default_factory=dict)
