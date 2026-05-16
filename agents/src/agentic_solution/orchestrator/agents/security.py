"""
Security-class remediation agents.

These agents implement *containment-first* logic — the priority is to
stop the bleeding (revoke keys, block IPs, isolate hosts) before any
forensic or root-cause work begins. Several declare
``requires_human_approval_at`` so the supervisor obtains explicit
operator confirmation before high-blast-radius actions like ransomware
host quarantine.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..contracts import (
    AgentCapability,
    AgentOutcome,
    IncidentClass,
    SeverityTier,
)
from .base import BaseRemediationAgent, make_outcome, register_agent


def _now() -> datetime:
    return datetime.now(UTC)


@register_agent
class CveRemediator(BaseRemediationAgent):
    """Handles ``CVE_VULNERABILITY`` findings.

    SEV0/SEV1 CVEs trigger immediate workload pinning and a Bug Daddy
    hand-off to draft a patched dependency PR. Lower severities open an
    SBOM-tracked ticket without intervening at runtime."""

    capability = AgentCapability(
        name="cve_remediator",
        version="1.2.0",
        description="Workload pin + dependency patch coordination for CVE findings.",
        handles=(IncidentClass.CVE_VULNERABILITY,),
        min_severity=SeverityTier.SEV3,
        concurrency=4,
        timeout_seconds=20.0,
        cost_weight=1.0,
        tags=("sbom", "patch"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        cve = event.raw.get("cve_id") or event.raw.get("cve")
        ctx.logger.info("agent.cve.coordination", cve=cve, service=event.service)
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "pin_workload_and_open_patch_pr",
                "cve": cve,
                "service": event.service,
                "handoff_to_bug_daddy": True,
            },
            compensating_handle=f"sbom::pin::{event.service}::{cve}",
        )


@register_agent
class SuspiciousIamRemediator(BaseRemediationAgent):
    """Handles ``SUSPICIOUS_IAM``. Strategy:

    1. Disable the offending session token.
    2. Force MFA re-auth on the principal.
    3. Snapshot the recent CloudTrail decisions for forensics.

    SEV0 (active credential abuse) gates on human approval to prevent a
    self-inflicted lockout during an over-eager false positive."""

    capability = AgentCapability(
        name="suspicious_iam_remediator",
        version="1.0.0",
        description="Session revoke + forensic snapshot for IAM anomalies.",
        handles=(IncidentClass.SUSPICIOUS_IAM,),
        min_severity=SeverityTier.SEV2,
        requires_human_approval_at=SeverityTier.SEV0,
        concurrency=2,
        timeout_seconds=15.0,
        cost_weight=1.5,
        tags=("iam", "containment"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        principal = event.raw.get("principal") or event.raw.get("user_arn")
        ctx.logger.info("agent.iam.revoke", principal=principal)
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "revoke_session_and_force_mfa",
                "principal": principal,
            },
            compensating_handle=f"iam::session-restore::{principal}",
        )


@register_agent
class UnauthorizedApiRemediator(BaseRemediationAgent):
    """Handles ``UNAUTHORIZED_API_ACCESS``. Strategy:

    1. Block the offending IP/ASN at the WAF.
    2. Rotate the API key associated with the source.
    3. Notify the application owner."""

    capability = AgentCapability(
        name="unauthorized_api_remediator",
        version="1.0.0",
        description="WAF block + API key rotation for unauthorized access.",
        handles=(IncidentClass.UNAUTHORIZED_API_ACCESS,),
        min_severity=SeverityTier.SEV2,
        requires_human_approval_at=SeverityTier.SEV0,
        concurrency=4,
        timeout_seconds=15.0,
        cost_weight=1.2,
        tags=("waf", "credentials"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        src_ip = event.raw.get("source_ip") or event.raw.get("client_ip")
        ctx.logger.info("agent.api.block", source_ip=src_ip)
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "waf_block_and_rotate_key",
                "source_ip": src_ip,
            },
            compensating_handle=f"waf::unblock::{src_ip}",
        )


@register_agent
class WafAnomalyRemediator(BaseRemediationAgent):
    """Handles ``WAF_ANOMALY``. Strategy:

    1. Tighten the relevant rule group (rate-limit / managed rule).
    2. Emit a synthetic probe to verify upstream still healthy."""

    capability = AgentCapability(
        name="waf_anomaly_remediator",
        version="1.0.0",
        description="Rule-tightening + synthetic-probe verification on WAF anomalies.",
        handles=(IncidentClass.WAF_ANOMALY,),
        min_severity=SeverityTier.SEV3,
        concurrency=4,
        timeout_seconds=15.0,
        cost_weight=1.0,
        tags=("waf",),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={"action": "tighten_waf_rule_group", "service": event.service},
            compensating_handle=f"waf::loosen::{event.service}",
        )


@register_agent
class IdsAnomalyRemediator(BaseRemediationAgent):
    """Handles ``IDS_ANOMALY``. Strategy:

    1. Quarantine the offending host VPC SG.
    2. Capture packet sample to forensic bucket.
    3. Hand off to incident_daddy for human-loop coordination."""

    capability = AgentCapability(
        name="ids_anomaly_remediator",
        version="1.0.0",
        description="Host quarantine + packet capture on IDS anomalies.",
        handles=(IncidentClass.IDS_ANOMALY,),
        min_severity=SeverityTier.SEV2,
        requires_human_approval_at=SeverityTier.SEV0,
        concurrency=2,
        timeout_seconds=20.0,
        cost_weight=2.0,
        tags=("ids", "forensics"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        host = event.raw.get("host") or event.service
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={"action": "quarantine_host_and_capture", "host": host},
            compensating_handle=f"ids::release::{host}",
        )


@register_agent
class RansomwareRemediator(BaseRemediationAgent):
    """Handles ``RANSOMWARE_INDICATOR``. ALWAYS gates on operator approval —
    quarantining a fleet on a false-positive is itself an outage."""

    capability = AgentCapability(
        name="ransomware_remediator",
        version="1.0.0",
        description="Full fleet quarantine + snapshot-pin for ransomware indicators.",
        handles=(IncidentClass.RANSOMWARE_INDICATOR,),
        min_severity=SeverityTier.SEV1,
        requires_human_approval_at=SeverityTier.SEV1,
        concurrency=1,
        timeout_seconds=30.0,
        cost_weight=5.0,
        tags=("ransomware", "high_blast"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _now()
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "isolate_affected_hosts_and_pin_snapshots",
                "indicators": event.indicators,
            },
            compensating_handle=f"ransomware::release::{event.correlation_id}",
        )
