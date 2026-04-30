from agentic_solution.heuristics import (
    infer_incident_severity,
    infer_review_disposition,
    is_non_code_resolution,
    needs_bug_handoff,
)
from agentic_solution.config import AppConfig
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
