from agentic_solution.heuristics import (
    infer_incident_severity,
    infer_review_disposition,
    is_non_code_resolution,
    needs_bug_handoff,
)


def test_infer_incident_severity_detects_sev1_markers():
    assert infer_incident_severity("P1 outage affecting all customers") == "sev1"


def test_needs_bug_handoff_detects_code_signals():
    assert needs_bug_handoff("Exception in checkout service", "stack trace attached") is True


def test_is_non_code_resolution_detects_jira_only_path():
    assert is_non_code_resolution("This is a non-code operational fix", "jira-only resolution") is True


def test_infer_review_disposition_detects_rework():
    assert infer_review_disposition("Reject this patch and send for rework") == "rework_required"
