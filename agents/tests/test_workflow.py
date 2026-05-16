from datetime import datetime, timedelta, timezone

from agentic_solution.heuristics import (
    infer_incident_severity,
    infer_review_disposition,
    is_non_code_resolution,
    needs_bug_handoff,
)
from agentic_solution.config import AppConfig
from agentic_solution.mcp import MCPToolBundle
from agentic_solution.contracts import IncidentRequest
from agentic_solution.services.incident import _compute_sla_kpis, _effective_criticality, _effective_priority
from agentic_solution.services.classifier import ClassifierRuntime
from agentic_solution.services.combined import LocalPeerRuntimeClient, _enable_local_peers, _target_from_payload


class DummyRuntime:
    def __init__(self, response):
        self.response = response

    def handle(self, payload):
        self.payload = payload
        return self.response


def test_infer_incident_severity_detects_sev1_markers():
    assert infer_incident_severity("P1 outage affecting all customers") == "sev1"


def test_needs_bug_handoff_detects_code_signals():
    assert needs_bug_handoff("Exception in checkout service", "stack trace attached") is True


def test_is_non_code_resolution_detects_jira_only_path():
    assert is_non_code_resolution("This is a non-code operational fix", "jira-only resolution") is True


def test_is_non_code_resolution_overrides_critic_verdict_when_body_describes_code_fix():
    strategy = (
        "Edited microservices/AutoDebitService/lambda_function.py at line 63 to "
        "cast the value to str. Branch fix/BUG-101 opened in PR #48."
    )
    critic = "Looks good.\n[STRATEGY_VERDICT: NON_CODE]"
    assert is_non_code_resolution(strategy, critic) is False


def test_is_non_code_resolution_honors_critic_non_code_when_body_is_operational():
    strategy = "Update the runbook and assign the Jira ticket to the on-call. No code changes."
    critic = "Agreed.\n[STRATEGY_VERDICT: NON_CODE]"
    assert is_non_code_resolution(strategy, critic) is True


def test_infer_review_disposition_detects_rework():
    assert infer_review_disposition("Reject this patch and send for rework") == "rework_required"


def test_combined_runtime_target_detection():
    assert _target_from_payload({"target": "sme"}) == "sme_agent"
    assert _target_from_payload({"agent": "reviewer-daddy"}) == "reviewer_daddy"
    assert _target_from_payload({"question": "Who owns this?", "context": {}}) == "sme_agent"
    assert _target_from_payload({"issue": {}, "plan": "fix", "fix_proposal": "patch"}) == "reviewer_daddy"
    assert _target_from_payload({"prompt": "Fix this", "incident_summary": "P1"}) == "bug_daddy"
    assert _target_from_payload({"prompt": "P1 outage"}) == "incident_daddy"


def test_local_peer_runtime_client_invokes_in_process_runtime():
    runtime = DummyRuntime({"component": "sme_agent", "summary": "ok"})
    client = LocalPeerRuntimeClient({"sme_agent": runtime})

    peer = type("Peer", (), {"name": "sme_agent"})()
    response = client.invoke(peer, {"question": "Q"})

    assert response == {"component": "sme_agent", "summary": "ok"}
    assert runtime.payload == {"question": "Q"}


def test_combined_runtime_enables_local_peer_configs():
    config = AppConfig()

    _enable_local_peers(config)

    assert config.sme_agent.enabled is True
    assert config.bug_daddy.enabled is True
    assert config.reviewer_daddy.enabled is True
    assert config.sme_agent.url == "local://sme_agent"


def test_classifier_creates_jira_before_bug_handoff(monkeypatch):
    class DummyClassifierAgent:
        def __call__(self, prompt):
            return "[ROUTE: BUG] [SUMMARY: needs code remediation]"

    class DummyPeers:
        def invoke(self, peer, payload):
            self.peer = peer
            self.payload = payload
            return {"component": "bug_daddy", "summary": "ok"}

    created = {}

    def fake_create_issue(**kwargs):
        created.update(kwargs)
        return {"key": "BUG-123"}

    config = AppConfig()
    _enable_local_peers(config)
    tools = MCPToolBundle([], [], [], [], {})
    peers = DummyPeers()
    runtime = ClassifierRuntime(config=config, tools=tools, peers=peers)
    monkeypatch.setattr(runtime, "_build_agent", lambda: DummyClassifierAgent())
    monkeypatch.setattr("agentic_solution.services.classifier.jira_create_issue", fake_create_issue)

    response = runtime.handle(
        {
            "prompt": "Unhandled ClientError in lambda",
            "service_name": "kyc-service",
            "repository": "org/repo",
            "logs": ["Traceback"],
            "metadata": {"request_id": "req-1"},
        }
    )

    assert response == {"component": "bug_daddy", "summary": "ok"}
    assert created["summary"].startswith("[Bug Daddy] kyc-service")
    assert created["issue_type"] == "Task"
    assert peers.peer.name == "bug_daddy"
    assert peers.payload["resolution_jira"] == "BUG-123"
    assert peers.payload["metadata"]["jira_key"] == "BUG-123"
    assert peers.payload["metadata"]["request_id"] == "req-1"


def test_incident_sla_kpis_and_priority_criticality_defaults():
    opened_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    acknowledged_at = opened_at + timedelta(minutes=10)
    request = IncidentRequest(prompt="P1 outage", opened_at=opened_at, acknowledged_at=acknowledged_at)

    priority = _effective_priority("unknown", "sev1")
    criticality = _effective_criticality("unknown", "sev1")
    kpis = _compute_sla_kpis(request, priority)

    assert priority == "p1"
    assert criticality == "critical"
    assert kpis.ack_target_minutes == 15
    assert kpis.time_to_ack_minutes == 10
    assert kpis.ack_breached is False
