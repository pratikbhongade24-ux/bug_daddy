from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_solution.config import AppConfig, PeerAgentConfig
from agentic_solution.peer import PeerInvocationError
from agentic_solution.services import bug, incident, reviewer, sme, classifier


@dataclass(slots=True)
class LocalPeerRuntimeClient:
    runtimes: dict[str, Any]

    def invoke(self, peer: PeerAgentConfig, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self.runtimes.get(peer.name)
        if runtime is None:
            raise PeerInvocationError(f"Local peer runtime '{peer.name}' is not configured.")
        return runtime.handle(payload)


@dataclass(slots=True)
class CombinedBugDaddyRuntime:
    config: AppConfig
    incident_daddy: incident.IncidentDaddyRuntime
    bug_daddy: bug.BugDaddyRuntime
    reviewer_daddy: reviewer.ReviewerDaddyRuntime
    sme_agent: sme.SMEAgentRuntime
    classifier: classifier.ClassifierRuntime

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = _target_from_payload(payload)

        if target == "sme_agent":
            return self.sme_agent.handle(payload)
        if target == "reviewer_daddy":
            return self.reviewer_daddy.handle(payload)
        if target == "bug_daddy":
            return self.bug_daddy.handle(payload)
        if target == "classifier":
            return self.classifier.handle(payload)
        return self.incident_daddy.handle(payload)


def build_runtime(config: AppConfig | None = None) -> CombinedBugDaddyRuntime:
    cfg = config or AppConfig.from_env()
    _enable_local_peers(cfg)

    sme_runtime = sme.build_runtime(cfg)
    reviewer_runtime = reviewer.build_runtime(cfg)
    bug_runtime = bug.build_runtime(cfg)
    incident_runtime = incident.build_runtime(cfg)
    classifier_runtime = classifier.build_runtime(cfg)

    local_peers = LocalPeerRuntimeClient(
        {
            "sme_agent": sme_runtime,
            "reviewer_daddy": reviewer_runtime,
            "bug_daddy": bug_runtime,
            "incident_daddy": incident_runtime,
        }
    )
    bug_runtime.peers = local_peers
    incident_runtime.peers = local_peers

    return CombinedBugDaddyRuntime(
        config=cfg,
        incident_daddy=incident_runtime,
        bug_daddy=bug_runtime,
        reviewer_daddy=reviewer_runtime,
        sme_agent=sme_runtime,
        classifier=classifier_runtime,
    )


def _enable_local_peers(config: AppConfig) -> None:
    config.sme_agent.url = config.sme_agent.url or "local://sme_agent"
    config.bug_daddy.url = config.bug_daddy.url or "local://bug_daddy"
    config.reviewer_daddy.url = config.reviewer_daddy.url or "local://reviewer_daddy"


def _target_from_payload(payload: dict[str, Any]) -> str:
    raw_target = payload.get("target") or payload.get("agent") or payload.get("component")
    if isinstance(raw_target, str):
        normalized = raw_target.strip().lower().replace("-", "_")
        aliases = {
            "incident": "incident_daddy",
            "incident_daddy": "incident_daddy",
            "bug": "bug_daddy",
            "bug_daddy": "bug_daddy",
            "reviewer": "reviewer_daddy",
            "reviewer_daddy": "reviewer_daddy",
            "sme": "sme_agent",
            "sme_agent": "sme_agent",
            "classifier": "classifier",
        }
        if normalized in aliases:
            return aliases[normalized]

    if "question" in payload and "context" in payload:
        return "sme_agent"
    if {"issue", "plan", "fix_proposal"}.issubset(payload):
        return "reviewer_daddy"
    if "incident_summary" in payload or "incident_artifacts" in payload:
        return "bug_daddy"
    if "fingerprint" in payload or "stack_trace" in payload:
        return "classifier"
    return "incident_daddy"
