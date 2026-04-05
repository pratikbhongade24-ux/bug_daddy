from __future__ import annotations

from agentic_solution.contracts import Severity


def infer_incident_severity(text: str) -> Severity:
    lowered = text.lower()
    if any(marker in lowered for marker in ["sev1", "p1", "outage", "all customers", "critical"]):
        return "sev1"
    if any(marker in lowered for marker in ["sev2", "p2", "degraded", "partial outage"]):
        return "sev2"
    if any(marker in lowered for marker in ["sev3", "p3", "minor", "single tenant"]):
        return "sev3"
    return "unknown"


def needs_bug_handoff(*parts: str) -> bool:
    signal = " ".join(parts).lower()
    markers = [
        "code fix",
        "bug",
        "exception",
        "stack trace",
        "regression",
        "root cause",
        "repository",
        "service crash",
    ]
    return any(marker in signal for marker in markers)


def is_non_code_resolution(*parts: str) -> bool:
    signal = " ".join(parts).lower()
    markers = ["runbook", "configuration only", "manual remediation", "non-code", "jira-only"]
    return any(marker in signal for marker in markers)


def infer_review_disposition(text: str) -> str:
    lowered = text.lower()
    if "rework" in lowered or "reject" in lowered:
        return "rework_required"
    if "jira-only" in lowered or "non-code" in lowered:
        return "jira_ticket"
    return "pull_request"
