# Autonomous Remediation Orchestration Layer

> A **Router–Supervisor Mesh** for autonomous incident & vulnerability remediation.
> Deterministic routing, typed incident contracts, supervised agent execution,
> compensating rollback, and priority-aware scheduling — engineered for
> reproducibility under multi-vector failure.

This package (`agentic_solution.orchestrator`) is the orchestration plane that
sits in front of the existing `incident_daddy / bug_daddy / reviewer_daddy /
sme_agent` runtimes. Where those runtimes own *reasoning*, the orchestrator
owns *control*: which agent runs, when, with what budget, under what
breaker, with what rollback.

---

## Why this design

| Pillar | Property | Where it lives |
|---|---|---|
| **Deterministic routing** | Same `(event, snapshot)` → same decision. No hidden state. | `routing/router.py` |
| **Typed contracts** | Cross-boundary shapes are Pydantic-validated; agents cannot disagree about what an incident is. | `contracts.py` |
| **Decoupled ingestion** | Triggers are journaled before normalization; telemetry survives downstream degradation. | `runtime/ingestion.py` |
| **Priority + fairness** | Weighted-fair priority queue prevents both inversion and starvation. | `runtime/scheduler.py` |
| **Supervised autonomy** | Every effectful step is paired with a compensating intent. Agents execute one bounded intent at a time. | `runtime/supervisor.py`, `runtime/recovery.py` |
| **Circuit-broken dispatch** | Per-agent three-state breaker; router reads breaker state from the same snapshot it routes against. | `runtime/circuit_breaker.py`, `routing/registry.py` |
| **Plugin agents** | `@register_agent` decorator + capability manifest. Adding a new incident class is a new file. | `agents/base.py`, `agents/bootstrap.py` |
| **Audit-first observability** | One JSON record per layer crossing, keyed on `correlation_id`. | `observability/` |

---

## Architecture (10 layers)

```
                  ┌──────────────────────────────────────────────┐
   upstreams ───► │ 1. Trigger Ingestion Layer (durable journal) │
 (CloudWatch,     └──────────────────────────────────────────────┘
  GuardDuty,                       │
  Snyk, IDS,                       ▼
  PagerDuty,      ┌──────────────────────────────────────────────┐
  Prometheus…)    │ 2. Event Normalization & Enrichment          │
                  │    (rule-driven, no LLM in routing path)     │
                  └──────────────────────────────────────────────┘
                                   │
                                   ▼
                  ┌──────────────────────────────────────────────┐
                  │ 3. Typed Incident Contracts (NormalizedEvent)│
                  └──────────────────────────────────────────────┘
                                   │
                                   ▼
                  ┌──────────────────────────────────────────────┐
                  │ 6. Priority & Severity Scheduler             │
                  │    (weighted-fair, anti-starvation slots)    │
                  └──────────────────────────────────────────────┘
                                   │
                                   ▼
                  ┌──────────────────────────────────────────────┐
                  │ 7. Remediation Supervisor (state machine)    │
                  └──────────────────────────────────────────────┘
                         │              │              │
                         ▼              ▼              ▼
                  ┌────────────┐ ┌───────────┐ ┌──────────────┐
                  │ 4. Agent   │ │ 5. Router │ │ 7b. Executor │
                  │ Registry & │ │ Engine    │ │ (timeouts,   │
                  │ Capability │ │ (pure fn) │ │  retries,    │
                  │ Discovery  │ │           │ │  breakers)   │
                  └────────────┘ └───────────┘ └──────────────┘
                                                     │
                                                     ▼
                                          ┌──────────────────┐
                                          │ 8. Feedback Loop │
                                          │ (compensations)  │
                                          └──────────────────┘
                                                     │
                                                     ▼
                                          ┌──────────────────┐
                                          │ 10. Recovery /   │
                                          │     Rollback     │
                                          └──────────────────┘

                                          ┌──────────────────┐
                                          │ 9. Audit Journal │
                                          │ (append-only,    │
                                          │  per-corr trace) │
                                          └──────────────────┘
```

---

## Key terms

- **Correlation ID** — stable identifier for one incident across deduplicated and re-fired signals. Threads through every log line, every audit record, every agent call.
- **Fingerprint** — content-derived hash for signal-storm collapse. Distinct from correlation_id so a *recurring* incident re-opens under a new correlation.
- **Capability manifest** — what an agent declares: incident classes handled, severity floor, concurrency, timeout, retries, cost weight, human-approval gates.
- **Compensating intent** — the inverse action paired with every effectful step. Replayed LIFO by the recovery coordinator on terminal failure.
- **Fairness slot** — the scheduler's anti-starvation guarantee. Each severity tier has a minimum service share per cycle, so SEV4 hygiene work drains even under sustained SEV0 load.
- **Routing decision** — pure function of `(NormalizedEvent, RegistrySnapshot)`. Reproducible from the audit journal alone.

---

## File layout

```
orchestrator/
├── __init__.py
├── contracts.py                 # typed envelopes + enums
├── orchestrator.py              # facade: ties everything together
├── demo.py                      # end-to-end demo runner
├── README.md                    # ← this file
│
├── agents/
│   ├── base.py                  # BaseRemediationAgent + @register_agent
│   ├── bootstrap.py             # default-agent bootstrap
│   ├── capacity.py              # cpu / memory / db saturation
│   ├── availability.py          # downtime / error-rate / failed deploy
│   ├── security.py              # cve / iam / unauth / waf / ids / ransomware
│   └── hygiene.py               # tls expiry / cloud misconfig
│
├── routing/
│   ├── registry.py              # AgentRegistry + snapshot semantics
│   └── router.py                # pure routing engine
│
├── runtime/
│   ├── ingestion.py             # admission control + journal write
│   ├── normalization.py         # raw -> NormalizedEvent
│   ├── scheduler.py             # weighted-fair priority queue
│   ├── circuit_breaker.py       # 3-state breaker (closed/open/half-open)
│   ├── executor.py              # bounded agent dispatch
│   ├── supervisor.py            # state-machine kernel
│   └── recovery.py              # LIFO compensation walker
│
├── observability/
│   ├── logging.py               # structured JSON logger w/ context bind
│   ├── audit.py                 # append-only audit journal
│   └── metrics.py               # counter / gauge / histogram primitives
│
└── samples/
    └── triggers.py              # one realistic payload per incident class
```

---

## Quickstart

```bash
cd agents
# venv assumed already set up per the outer README
.venv/bin/python -m agentic_solution.orchestrator.demo
```

The demo submits 14 heterogeneous triggers (CloudWatch, GuardDuty, Snyk, IDS,
PagerDuty, Prometheus, …) in deliberately chaotic order and prints a summary
showing:

- **Priority scheduling worked** — the SEV0 ransomware indicator is handled
  first even though it arrived 3rd, and SEV4 hygiene is handled last.
- **Severity scoring is authoritative** — a CVSS-10 Log4j CVE that arrived
  tagged `"info"` upstream is normalized to SEV0 because the CVSS rule fires
  before text scanning.
- **Every incident class** dispatches to its declared specialist agent.

---

## Programmatic use

```python
import asyncio
from agentic_solution.orchestrator import build_default_orchestrator
from agentic_solution.orchestrator.contracts import RawTrigger, TriggerSource

async def main():
    orch = build_default_orchestrator()
    await orch.start()
    await orch.submit(RawTrigger(
        source=TriggerSource.GUARDDUTY,
        correlation_hint="ransomware-fleet-prod",
        payload={
            "type": "ransomware",
            "service": "asset-store",
            "environment": "prod",
            "indicators": ["mass_file_rename", "shadow_copy_deletion"],
            "severity": "critical",
        },
    ))
    await orch.run_until_idle()
    await orch.stop()

    for trace in await orch.traces():
        print(trace.event.incident_class, "->", trace.terminal_status)

asyncio.run(main())
```

---

## Registering a new agent

```python
from agentic_solution.orchestrator.agents.base import (
    BaseRemediationAgent, register_agent, make_outcome, utcnow,
)
from agentic_solution.orchestrator.contracts import (
    AgentCapability, IncidentClass, SeverityTier,
)

@register_agent
class KafkaLagRemediator(BaseRemediationAgent):
    capability = AgentCapability(
        name="kafka_lag_remediator",
        version="1.0.0",
        description="Consumer-group rebalance + partition reassignment for lag.",
        handles=(IncidentClass.ELEVATED_ERROR_RATE,),  # or a new IncidentClass
        min_severity=SeverityTier.SEV3,
        concurrency=2,
        timeout_seconds=25.0,
        cost_weight=1.5,
        tags=("kafka",),
    )

    async def execute(self, step, event, ctx):
        ctx.logger.info("kafka.rebalance", group=event.tags.get("consumer_group"))
        return make_outcome(
            agent=self.capability.name,
            step_id=step.step_id,
            success=True,
            started_at=utcnow(),
            output={"action": "rebalance_partitions"},
            compensating_handle=f"kafka::restore::{event.correlation_id}",
        )
```

Then either import the module before `build_default_orchestrator()` runs, or
call the registry directly:

```python
from agentic_solution.orchestrator.runtime.circuit_breaker import CircuitBreaker
orch.registry.register(KafkaLagRemediator(), breaker=CircuitBreaker(name="kafka_lag_remediator"))
```

---

## Incident classes supported out of the box

| Class | Default agent | Floor | Approval gate |
|---|---|---|---|
| `cpu_spike` | `cpu_pressure_remediator` | SEV4 | — |
| `memory_pressure` | `memory_pressure_remediator` | SEV3 | — |
| `database_saturation` | `database_saturation_remediator` | SEV2 | SEV0 |
| `service_downtime` | `service_downtime_remediator` | SEV2 | — |
| `elevated_error_rate` | `error_rate_remediator` | SEV3 | — |
| `failed_deployment` | `failed_deployment_remediator` | SEV3 | — |
| `cve_vulnerability` | `cve_remediator` | SEV3 | — |
| `suspicious_iam_activity` | `suspicious_iam_remediator` | SEV2 | SEV0 |
| `unauthorized_api_access` | `unauthorized_api_remediator` | SEV2 | SEV0 |
| `waf_anomaly` | `waf_anomaly_remediator` | SEV3 | — |
| `ids_anomaly` | `ids_anomaly_remediator` | SEV2 | SEV0 |
| `tls_certificate_expiry` | `tls_expiry_remediator` | SEV4 | — |
| `cloud_misconfiguration` | `cloud_misconfig_remediator` | SEV3 | SEV0 |
| `ransomware_indicator` | `ransomware_remediator` | SEV1 | SEV1 |

---

## Failure recovery walkthrough

1. Event ingested, journaled, normalized, scheduled.
2. Supervisor routes to primary agent; step 1 executes effectfully and returns
   `compensating_handle="hpa::checkout-service::+4"`.
3. Step 2 dispatches to a second agent that **fails after exhausting retries
   and tripping the circuit breaker**.
4. Supervisor rotates through `fallback_agents`. All fail.
5. Recovery coordinator walks executed steps in LIFO order, invoking each
   agent's `compensate(handle, event, ctx)` with the previously returned
   handle. Step 1's autoscale-out is reversed via `compensate` → autoscale-in.
6. Final audit record `incident.failed_rolled_back` is written, including
   every outcome and every compensation result.

The full trace is reconstructible from the audit journal alone.

---

## Reliability primitives

- **Retries** — exponential backoff with full jitter; cap 8s; per-step `max_retries` overrideable.
- **Timeouts** — `asyncio.wait_for` per call; overrun recorded as `TIMED_OUT`, counted against breaker.
- **Circuit breaker** — sliding-window failure ratio with `min_samples`, `OPEN → HALF_OPEN → CLOSED` probe.
- **Concurrency** — per-agent `asyncio.Semaphore` sized from `capability.concurrency`.
- **Backpressure** — bounded ingestion queue; over-quota submissions are rejected loudly with a metric and a log record.
- **Idempotency** — every effectful intent keyed on `(correlation_id, step_id)`; supervisor may retry without amplifying blast radius.

---

## Audit & observability

Every layer transition emits a structured JSON log line and an `AuditRecord`.
Sample log keys:

```
ts                   - ISO8601 with UTC offset
level                - DEBUG/INFO/WARNING/ERROR
logger               - "orchestrator"
event                - dot-notation transition name
correlation_id       - threads through one incident
agent / step_id      - on agent-level events
incident_class       - on supervisor / executor events
severity             - on routing / scheduling events
```

To replay an incident, filter the audit journal by `correlation_id` and read
the records in timestamp order. Routing decisions, agent outcomes, breaker
transitions, fallback rotations, and compensations are all in there.

---

## Performance characteristics

- **Routing** is O(N) in registered agent count per dispatch (N is small —
  typically 10–50). No allocations in the hot path beyond the
  `RoutingDecision`.
- **Scheduler** is O(log N) push, O(N) for fairness-slot pop (N bounded by
  inflight incident count; in practice < 1000).
- **Normalization** is O(rules) and rule count is fixed at module load.
- **Circuit breaker** is O(1) amortized with a deque trimmed lazily on each
  event.

---

## Integration with the existing daddies

The orchestrator deliberately does **not** invoke `incident_daddy` or
`bug_daddy` directly. Instead, an agent (e.g. `error_rate_remediator`) sets
`output.handoff_to_bug_daddy=True`, and a thin downstream adapter (not in
this package) reads the audit stream and dispatches a `BugRequest` to the
Bedrock AgentCore runtime defined in `apps/bug_daddy`. This keeps the
orchestrator domain-agnostic — it could just as easily front a different
remediation stack.

---

## What you should look at when reviewing

1. `contracts.py` — the type system that makes the rest of the system
   reproducible.
2. `routing/router.py` — the pure-function routing engine.
3. `runtime/supervisor.py` — the state machine that turns a routing decision
   into an audited execution trace.
4. `runtime/circuit_breaker.py` — the safety boundary around every agent
   call.
5. `agents/security.py` — the most opinionated remediation logic, including
   the human-approval gates.
