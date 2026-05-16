import pytest

from agentic_solution.peer import PeerInvocationError
from agentic_solution.services.combined import CombinedBugDaddyRuntime, LocalPeerRuntimeClient


class _DummyRuntime:
    def __init__(self, response):
        self.response = response
        self.last_payload = None

    def handle(self, payload):
        self.last_payload = payload
        return self.response


def test_local_peer_runtime_client_raises_for_unknown_peer():
    client = LocalPeerRuntimeClient(runtimes={})
    peer = type("Peer", (), {"name": "missing_peer"})()

    with pytest.raises(PeerInvocationError):
        client.invoke(peer, {"prompt": "hello"})


def test_combined_runtime_routes_to_feature_daddy_for_prd_payload():
    incident_runtime = _DummyRuntime({"component": "incident_daddy"})
    feature_runtime = _DummyRuntime({"component": "feature_daddy", "summary": "prd accepted"})
    runtime = CombinedBugDaddyRuntime(
        config=type("Cfg", (), {})(),
        incident_daddy=incident_runtime,
        bug_daddy=_DummyRuntime({"component": "bug_daddy"}),
        reviewer_daddy=_DummyRuntime({"component": "reviewer_daddy"}),
        sme_agent=_DummyRuntime({"component": "sme_agent"}),
        classifier=_DummyRuntime({"component": "classifier"}),
        feature_daddy=feature_runtime,
    )

    payload = {"prd": "Build audit timeline", "service_name": "transactions"}
    out = runtime.handle(payload)

    assert out["component"] == "feature_daddy"
    assert feature_runtime.last_payload == payload
    assert incident_runtime.last_payload is None
