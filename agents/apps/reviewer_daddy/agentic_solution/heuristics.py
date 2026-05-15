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
    """Return True only when the explicit non-code tag appears on its own line."""
    import re
    signal = " ".join(parts)
    # The tag must be on its own line (possibly with leading whitespace/markdown bullets)
    return bool(re.search(r"^\s*[-*]?\s*\[RESOLUTION_TYPE:\s*NON_CODE\]\s*$", signal, re.MULTILINE))


def infer_review_disposition(text: str) -> str:
    import re
    tag = re.search(r"\[DECISION:\s*(APPROVE|JIRA_ONLY|REWORK)\]", text, re.IGNORECASE)
    if tag:
        decision = tag.group(1).upper()
        if decision == "REWORK":
            return "rework_required"
        if decision == "JIRA_ONLY":
            return "jira_ticket"
        return "pull_request"

    # Fallback for responses without the structured tag
    lowered = text.lower()
    if re.search(r"\b(rework required|requires rework|send back for rework|rejected)\b", lowered):
        return "rework_required"
    if "jira-only" in lowered or "non-code" in lowered:
        return "jira_ticket"
    return "pull_request"
