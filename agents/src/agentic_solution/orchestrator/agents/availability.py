"""
Availability-class remediation agents.

Covers service downtime, elevated error rate, and failed deployment.
These agents either roll a deployment back or shift traffic away from a
broken target. They are the most common dispatch path in practice.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..contracts import (
    AgentCapability,
    AgentOutcome,
    IncidentClass,
    NormalizedEvent,
    RemediationStep,
    SeverityTier,
)
from .base import BaseRemediationAgent, ExecutionContext, make_outcome, register_agent, utcnow


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_agent
class ServiceDowntimeRemediator(BaseRemediationAgent):
    """Handles ``SERVICE_DOWNTIME``. Strategy:

    1. Pull recent deploy history.
    2. If a deploy happened within the blast window, initiate rollback.
    3. Otherwise, shift traffic to the healthy region via weighted DNS."""

    capability = AgentCapability(
        name="service_downtime_remediator",
        version="2.0.1",
        description="Deploy rollback + cross-region traffic shift for downtime.",
        handles=(IncidentClass.SERVICE_DOWNTIME,),
        min_severity=SeverityTier.SEV2,
        concurrency=4,
        timeout_seconds=45.0,
        max_retries=1,
        cost_weight=2.5,
        tags=("rollback", "traffic"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        action = "rollback_last_deploy" if self._recent_deploy(event) else "shift_traffic_region"
        ctx.logger.info("agent.downtime.decision", action=action, service=event.service)
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={"action": action, "service": event.service, "region": event.region},
            compensating_handle=f"availability::{action}::{event.service}",
        )

    async def compensate(self, handle, event, ctx) -> AgentOutcome:
        ctx.logger.info("agent.downtime.compensate", handle=handle)
        return make_outcome(
            agent=self.capability.name,
            step_id=handle,
            success=True,
            started_at=utcnow(),
            output={"action": "restore_pre_change_state", "handle": handle},
        )

    @staticmethod
    def _recent_deploy(event: NormalizedEvent) -> bool:
        return bool(
            event.tags.get("recent_deploy") == "true"
            or event.raw.get("recent_deploy")
        )


@register_agent
class ErrorRateRemediator(BaseRemediationAgent):
    """Handles ``ELEVATED_ERROR_RATE``. Strategy:

    1. Inspect the carried error-class breakdown.
    2. If concentrated on a single endpoint, throttle that endpoint at
       the ingress.
    3. Emit a Bug Daddy hand-off intent for code-level diagnosis."""

    capability = AgentCapability(
        name="error_rate_remediator",
        version="1.3.0",
        description="Endpoint throttle + Bug Daddy hand-off for error spikes.",
        handles=(IncidentClass.ELEVATED_ERROR_RATE,),
        min_severity=SeverityTier.SEV3,
        concurrency=8,
        timeout_seconds=20.0,
        cost_weight=1.5,
        tags=("ingress", "throttle"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        error_rate = event.metrics.get("error_rate", 0.0)
        ctx.logger.info(
            "agent.error_rate.containment",
            error_rate=error_rate,
            service=event.service,
        )
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "ingress_throttle_endpoint",
                "service": event.service,
                "error_rate": error_rate,
                "handoff_to_bug_daddy": True,
            },
            compensating_handle=f"ingress::throttle::{event.service}",
        )


@register_agent
class FailedDeploymentRemediator(BaseRemediationAgent):
    """Handles ``FAILED_DEPLOYMENT``. Strategy:

    1. Cancel the in-flight rollout.
    2. Restore the previous revision.
    3. Open an audit ticket capturing the failed step."""

    capability = AgentCapability(
        name="failed_deployment_remediator",
        version="1.1.0",
        description="Rollout cancellation + revision restore for failed deployments.",
        handles=(IncidentClass.FAILED_DEPLOYMENT,),
        min_severity=SeverityTier.SEV3,
        concurrency=2,
        timeout_seconds=40.0,
        cost_weight=1.8,
        tags=("argo", "rollback"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        ctx.logger.info("agent.failed_deploy.rollback", service=event.service)
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "cancel_and_restore_previous_revision",
                "service": event.service,
            },
            compensating_handle=f"rollout::{event.service}::pre-restore-state",
        )
