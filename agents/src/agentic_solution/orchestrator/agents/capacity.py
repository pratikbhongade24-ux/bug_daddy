"""
Capacity-class remediation agents: CPU, memory, database saturation.

These agents are *operational* in nature — they remediate by shifting
capacity (autoscale up, drain hot pods, fail over a replica) rather than
by changing code. They are intentionally small: production deploys would
swap the simulated cloud calls for real boto3 / k8s clients without
touching the orchestrator contract.

Each agent declares a compensating intent so the supervisor can roll
back a wrong autoscale decision after the dust settles.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..contracts import (
    AgentCapability,
    AgentOutcome,
    IncidentClass,
    NormalizedEvent,
    RemediationStep,
    SeverityTier,
)
from .base import BaseRemediationAgent, ExecutionContext, make_outcome, register_agent, utcnow


def _started_now() -> datetime:
    return datetime.now(UTC)


@register_agent
class CpuPressureRemediator(BaseRemediationAgent):
    """Handles ``CPU_SPIKE`` events. Strategy:

    1. Confirm pressure via the carried metric.
    2. Issue an autoscale-out intent (target replica delta proportional
       to overload).
    3. If sustained, mark hottest pod for cordon/drain.

    The compensating intent scales back in when the original spike
    subsides — the recovery layer invokes it on plan failure to prevent
    leaving the fleet over-provisioned after a failed remediation."""

    capability = AgentCapability(
        name="cpu_pressure_remediator",
        version="1.2.0",
        description="Horizontal autoscale + hot-pod drain for CPU saturation.",
        handles=(IncidentClass.CPU_SPIKE,),
        min_severity=SeverityTier.SEV4,
        concurrency=8,
        timeout_seconds=20.0,
        max_retries=2,
        cost_weight=1.0,
        tags=("k8s", "autoscale"),
    )

    async def execute(
        self,
        step: RemediationStep,
        event: NormalizedEvent,
        ctx: ExecutionContext,
    ) -> AgentOutcome:
        started = _started_now()
        cpu = event.metrics.get("cpu_utilization") or event.metrics.get("cpu") or 0.0
        scale_delta = self._derive_scale_delta(cpu)
        ctx.logger.info(
            "agent.cpu.scale_decision",
            cpu=cpu,
            scale_delta=scale_delta,
            service=event.service,
        )
        # Simulated cloud control-plane call. Production swap point.
        handle = f"hpa::{event.service}::+{scale_delta}"
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "horizontal_scale_out",
                "service": event.service,
                "replica_delta": scale_delta,
                "observed_cpu": cpu,
            },
            compensating_handle=handle,
            metrics={"replicas_added": float(scale_delta)},
        )

    async def compensate(
        self,
        handle: str,
        event: NormalizedEvent,
        ctx: ExecutionContext,
    ) -> AgentOutcome:
        ctx.logger.info("agent.cpu.compensate", handle=handle)
        return make_outcome(
            agent=self.capability.name,
            step_id=handle,
            success=True,
            started_at=utcnow(),
            output={"action": "horizontal_scale_in", "handle": handle},
        )

    @staticmethod
    def _derive_scale_delta(cpu: float) -> int:
        if cpu >= 95:
            return 4
        if cpu >= 90:
            return 2
        return 1


@register_agent
class MemoryPressureRemediator(BaseRemediationAgent):
    """Handles ``MEMORY_PRESSURE`` events. Strategy:

    1. Trigger soft heap dump on the affected workload (forensic).
    2. Drain the pod with the highest RSS.
    3. If pattern matches a known leak signature, raise a Bug Daddy
       hand-off via the supervisor's downstream feedback hook (out of
       scope for this agent — the supervisor decides)."""

    capability = AgentCapability(
        name="memory_pressure_remediator",
        version="1.1.0",
        description="Heap-dump + pod-drain for memory saturation.",
        handles=(IncidentClass.MEMORY_PRESSURE,),
        min_severity=SeverityTier.SEV3,
        concurrency=4,
        timeout_seconds=25.0,
        cost_weight=1.2,
        tags=("k8s", "forensics"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _started_now()
        mem = event.metrics.get("memory_utilization") or event.metrics.get("memory") or 0.0
        ctx.logger.info("agent.memory.drain_decision", memory=mem, service=event.service)
        handle = f"pod-drain::{event.service}::heap-dump-stored"
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "drain_hot_pod",
                "service": event.service,
                "observed_memory": mem,
                "heap_dump": True,
            },
            compensating_handle=handle,
        )

    async def compensate(self, handle, event, ctx) -> AgentOutcome:
        return make_outcome(
            agent=self.capability.name,
            step_id=handle,
            success=True,
            started_at=utcnow(),
            output={"action": "uncordon_pod", "handle": handle},
        )


@register_agent
class DatabaseSaturationRemediator(BaseRemediationAgent):
    """Handles ``DATABASE_SATURATION``. Strategy:

    1. Identify the top-cost query from the carried metric snapshot.
    2. Kill long-running idle-in-transaction sessions.
    3. Optionally promote a read replica if the leader is the bottleneck.

    The supervisor will not auto-promote a replica at SEV0+ without
    operator approval — the capability declares that gate."""

    capability = AgentCapability(
        name="database_saturation_remediator",
        version="1.0.0",
        description="Top-query containment and replica promotion for RDS/Aurora saturation.",
        handles=(IncidentClass.DATABASE_SATURATION,),
        min_severity=SeverityTier.SEV2,
        requires_human_approval_at=SeverityTier.SEV0,
        concurrency=2,
        timeout_seconds=30.0,
        cost_weight=2.0,
        tags=("rds", "aurora"),
    )

    async def execute(self, step, event, ctx) -> AgentOutcome:
        started = _started_now()
        ctx.logger.info(
            "agent.db.containment",
            service=event.service,
            region=event.region,
        )
        handle = f"db-killset::{event.service}::session-cohort"
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=started,
            output={
                "action": "kill_long_running_sessions",
                "service": event.service,
                "promoted_replica": False,
            },
            compensating_handle=handle,
        )
