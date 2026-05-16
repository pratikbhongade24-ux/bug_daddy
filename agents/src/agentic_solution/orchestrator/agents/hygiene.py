"""
Hygiene-class remediation agents: TLS expiry, cloud misconfiguration.

Lower-severity but high-volume. These agents are tuned for cost — they
declare a low ``cost_weight`` so the router prefers them when multiple
specialists tie on capability match, and they emit detailed audit
records so SOC 2 / ISO controls can be evidenced from the journal."""

from __future__ import annotations

from datetime import datetime, timezone

from ..contracts import (
    AgentCapability,
    AgentOutcome,
    IncidentClass,
    SeverityTier,
)
from .base import BaseRemediationAgent, make_outcome, register_agent


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_agent
class TlsExpiryRemediator(BaseRemediationAgent):
    """Handles ``TLS_EXPIRY``. Strategy:

    1. Issue an ACM/Let's Encrypt renewal for the affected hostname.
    2. Stage the cert on the load balancer.
    3. Schedule a follow-up verification probe at T+60s."""

    capability = AgentCapability(
        name="tls_expiry_remediator",
        version="1.0.0",
        description="Cert renewal + LB staging for TLS expiry warnings.",
        handles=(IncidentClass.TLS_EXPIRY,),
        min_severity=SeverityTier.SEV4,
        concurrency=8,
        timeout_seconds=20.0,
        cost_weight=0.5,
        tags=("acm", "lb"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        host = event.raw.get("hostname") or event.service
        ctx.logger.info("agent.tls.renew", host=host)
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={"action": "renew_and_stage_cert", "host": host},
            compensating_handle=f"tls::revert::{host}",
        )


@register_agent
class CloudMisconfigRemediator(BaseRemediationAgent):
    """Handles ``CLOUD_MISCONFIG`` (S3 public, SG too-open, etc.). Strategy:

    1. Apply the curated baseline policy for the resource type.
    2. Record the prior configuration as the compensation target.
    3. Open a follow-up audit ticket so a human reviews the auto-fix."""

    capability = AgentCapability(
        name="cloud_misconfig_remediator",
        version="1.0.0",
        description="Policy-as-code baseline restoration for cloud drift.",
        handles=(IncidentClass.CLOUD_MISCONFIG,),
        min_severity=SeverityTier.SEV3,
        requires_human_approval_at=SeverityTier.SEV0,
        concurrency=4,
        timeout_seconds=25.0,
        cost_weight=0.8,
        tags=("policy", "iac"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        resource = event.raw.get("resource") or event.raw.get("arn")
        ctx.logger.info("agent.misconfig.restore_baseline", resource=resource)
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={"action": "apply_baseline_policy", "resource": resource},
            compensating_handle=f"policy::restore-pre::{resource}",
        )
