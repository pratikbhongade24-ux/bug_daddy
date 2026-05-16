"""Schema-level invariants for the orchestrator contract layer."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from agentic_solution.orchestrator.contracts import (
    AgentCapability,
    AgentOutcome,
    IncidentClass,
    NormalizedEvent,
    RawTrigger,
    RemediationPlan,
    RemediationStep,
    SeverityTier,
    StepStatus,
    TriggerSource,
)


class TestSeverityTier:
    def test_weights_are_strictly_ordered(self):
        """Scheduler relies on weight ordering — a regression here silently
        breaks priority semantics, so it gets its own assertion."""
        weights = [t.weight for t in (
            SeverityTier.SEV0,
            SeverityTier.SEV1,
            SeverityTier.SEV2,
            SeverityTier.SEV3,
            SeverityTier.SEV4,
        )]
        assert weights == sorted(weights, reverse=True)

    def test_sla_seconds_are_strictly_ordered(self):
        slas = [t.sla_seconds for t in (
            SeverityTier.SEV0,
            SeverityTier.SEV1,
            SeverityTier.SEV2,
            SeverityTier.SEV3,
            SeverityTier.SEV4,
        )]
        assert slas == sorted(slas)


class TestRawTrigger:
    def test_payload_must_be_dict(self):
        with pytest.raises(ValidationError):
            RawTrigger(source=TriggerSource.MANUAL, payload="not-a-dict")

    def test_accepts_unknown_keys_via_extra_allow(self):
        """`extra=allow` is required so we can absorb future upstream fields
        without a schema migration."""
        t = RawTrigger(
            source=TriggerSource.MANUAL,
            payload={"x": 1},
            future_field="value",
        )
        assert t.future_field == "value"


class TestNormalizedEvent:
    def _build(self, **overrides):
        from datetime import datetime
        kwargs = dict(
            correlation_id="src:abc",
            fingerprint="deadbeefdeadbeef",
            source=TriggerSource.MANUAL,
            incident_class=IncidentClass.CPU_SPIKE,
            severity=SeverityTier.SEV2,
            received_at=datetime.now(UTC),
        )
        kwargs.update(overrides)
        return NormalizedEvent(**kwargs)

    def test_is_frozen(self):
        """Frozenness is the invariant the supervisor relies on to thread
        the *same* event through retries without mutation."""
        event = self._build()
        with pytest.raises(ValidationError):
            event.severity = SeverityTier.SEV0  # type: ignore[misc]


class TestAgentCapability:
    def test_concurrency_lower_bound(self):
        with pytest.raises(ValidationError):
            AgentCapability(
                name="x",
                description="x",
                handles=(IncidentClass.CPU_SPIKE,),
                concurrency=0,
            )

    def test_timeout_must_be_positive(self):
        with pytest.raises(ValidationError):
            AgentCapability(
                name="x",
                description="x",
                handles=(IncidentClass.CPU_SPIKE,),
                timeout_seconds=0,
            )

    def test_is_frozen(self):
        cap = AgentCapability(
            name="x",
            description="x",
            handles=(IncidentClass.CPU_SPIKE,),
        )
        with pytest.raises(ValidationError):
            cap.cost_weight = 99.0  # type: ignore[misc]


class TestRemediationPlanAndStep:
    def test_step_defaults_are_pending(self):
        step = RemediationStep(agent="a", intent="i")
        assert step.status == StepStatus.PENDING
        assert step.attempts == 0
        assert step.output is None

    def test_plan_serializes_round_trip(self):
        step = RemediationStep(agent="cpu", intent="scale_out")
        plan = RemediationPlan(
            correlation_id="abc",
            incident_class=IncidentClass.CPU_SPIKE,
            severity=SeverityTier.SEV1,
            steps=[step],
            primary_agent="cpu",
        )
        dumped = plan.model_dump(mode="json")
        rehydrated = RemediationPlan.model_validate(dumped)
        assert rehydrated.steps[0].agent == "cpu"
        assert rehydrated.severity is SeverityTier.SEV1


class TestAgentOutcome:
    def test_success_outcome_can_carry_compensation_handle(self):
        from datetime import datetime
        now = datetime.now(UTC)
        outcome = AgentOutcome(
            agent="a", step_id="s", success=True,
            started_at=now, finished_at=now,
            compensating_handle="handle::1",
        )
        assert outcome.compensating_handle == "handle::1"
