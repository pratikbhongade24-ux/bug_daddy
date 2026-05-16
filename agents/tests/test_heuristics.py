"""Granular tests for the heuristics module.

Two surfaces are tested:
1. Backwards-compatible verdict-only API (`infer_*`, `is_*`) so legacy
   callers keep working.
2. New `Decision`-returning variants — confidence levels, signal
   provenance, and the contradiction-guard branch get explicit
   assertions because they are the routing-safety boundary.
"""

from __future__ import annotations

import pytest

from agentic_solution.heuristics import (
    Confidence,
    Decision,
    infer_incident_severity,
    infer_incident_severity_decision,
    infer_review_disposition,
    infer_review_disposition_decision,
    is_non_code_resolution,
    is_non_code_resolution_decision,
    needs_bug_handoff,
    needs_bug_handoff_decision,
)


class TestInferIncidentSeverity:
    def test_sev1_marker_returns_sev1(self):
        assert infer_incident_severity("P1 outage affecting all customers") == "sev1"

    def test_decision_carries_signals_and_confidence(self):
        d = infer_incident_severity_decision("P1 outage affecting all customers")
        assert d.verdict == "sev1"
        assert d.confidence == Confidence.HIGH  # >=2 markers => HIGH
        assert "p1" in d.signals
        assert "outage" in d.signals

    def test_single_marker_is_medium_confidence(self):
        d = infer_incident_severity_decision("nightly degraded performance")
        assert d.verdict == "sev2"
        assert d.confidence == Confidence.MEDIUM

    def test_sev2_marker_returns_sev2(self):
        assert infer_incident_severity("Service is degraded for some users") == "sev2"

    def test_sev3_marker_returns_sev3(self):
        assert infer_incident_severity("Minor issue affecting a single tenant") == "sev3"

    def test_unknown_when_no_markers(self):
        d = infer_incident_severity_decision("everything is fine")
        assert d.verdict == "unknown"
        assert d.confidence == Confidence.NONE

    def test_higher_severity_short_circuits_lower(self):
        """SEV1 must win even if a SEV3 marker is also present in the
        same text — incident triage prefers false-high to false-low."""
        d = infer_incident_severity_decision("P1 outage with a minor knock-on issue")
        assert d.verdict == "sev1"

    def test_handles_empty_string(self):
        assert infer_incident_severity("") == "unknown"

    def test_case_insensitive(self):
        assert infer_incident_severity("OUTAGE") == "sev1"


class TestNeedsBugHandoff:
    def test_always_returns_false(self):
        """Bug hand-off is now classifier-driven; the heuristic is a
        no-op stub. Asserting it stays a no-op prevents an accidental
        re-enable that would silently re-introduce the false-positive
        flood the original review called out."""
        assert needs_bug_handoff("Exception in checkout") is False

    def test_decision_documents_deprecation(self):
        d = needs_bug_handoff_decision("anything")
        assert d.verdict == "no"
        assert "classifier" in d.rationale


class TestIsNonCodeResolution:
    def test_critic_non_code_verdict_wins(self):
        text = "[STRATEGY_VERDICT: NON_CODE] this is an ops thing"
        assert is_non_code_resolution(text) is True
        d = is_non_code_resolution_decision(text)
        assert d.confidence == Confidence.HIGH

    def test_critic_code_verdict_blocks_planner_tag(self):
        """The critic outranks the planner — even with [RESOLUTION_TYPE:
        NON_CODE] in the same text, a CODE critic verdict means we run
        the coder pipeline."""
        text = "[STRATEGY_VERDICT: CODE]\n[RESOLUTION_TYPE: NON_CODE]"
        assert is_non_code_resolution(text) is False
        d = is_non_code_resolution_decision(text)
        assert d.confidence == Confidence.HIGH
        assert "STRATEGY_VERDICT:CODE" in d.signals

    def test_critic_unclear_runs_pipeline(self):
        text = "[STRATEGY_VERDICT: UNCLEAR]"
        assert is_non_code_resolution(text) is False

    def test_planner_tag_alone_triggers_non_code(self):
        text = "- [RESOLUTION_TYPE: NON_CODE]"
        assert is_non_code_resolution(text) is True

    def test_keyword_alone_triggers_non_code(self):
        assert is_non_code_resolution("this is a jira-only resolution") is True

    def test_contradiction_guard_overrides_tag(self):
        """The canonical regression case — the planner tagged NON_CODE
        but the body explicitly opens a PR. A self-contradicting tag is
        a bug, not a routing signal."""
        text = (
            "[RESOLUTION_TYPE: NON_CODE]\n"
            "```diff\n--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n```"
        )
        assert is_non_code_resolution(text) is False
        d = is_non_code_resolution_decision(text)
        assert "contradiction_guard" in d.signals[0]

    def test_contradiction_guard_detects_branch_name(self):
        text = "[RESOLUTION_TYPE: NON_CODE] please push fix/checkout-bug"
        assert is_non_code_resolution(text) is False

    def test_contradiction_guard_detects_pr_url(self):
        text = (
            "[RESOLUTION_TYPE: NON_CODE] "
            "see https://github.com/org/repo/pull/123"
        )
        assert is_non_code_resolution(text) is False

    def test_empty_input_returns_false(self):
        assert is_non_code_resolution("") is False

    def test_multiple_args_are_concatenated(self):
        """Callers pass multiple parts — they must be considered together,
        not independently, so a tag in part A and a contradiction in part
        B still cancels out."""
        assert (
            is_non_code_resolution(
                "[RESOLUTION_TYPE: NON_CODE]",
                "```diff\n--- a/foo\n```",
            )
            is False
        )


class TestInferReviewDisposition:
    def test_approve_tag_returns_pull_request(self):
        assert infer_review_disposition("[DECISION: APPROVE]") == "pull_request"

    def test_rework_tag_returns_rework_required(self):
        assert infer_review_disposition("[DECISION: REWORK]") == "rework_required"

    def test_jira_only_tag_returns_jira_ticket(self):
        assert infer_review_disposition("[DECISION: JIRA_ONLY]") == "jira_ticket"

    def test_tag_is_authoritative_over_phrases(self):
        """If the reviewer emits a tag, the tag wins even if the body
        contains contradictory keywords."""
        text = "[DECISION: APPROVE] this is rework required, but we approve anyway"
        assert infer_review_disposition(text) == "pull_request"
        assert infer_review_disposition_decision(text).confidence == Confidence.HIGH

    def test_rework_phrase_without_tag(self):
        assert infer_review_disposition("This patch is rejected.") == "rework_required"
        d = infer_review_disposition_decision("This patch is rejected.")
        assert d.confidence == Confidence.MEDIUM

    def test_jira_only_keyword_without_tag(self):
        assert infer_review_disposition("Non-code fix — jira-only.") == "jira_ticket"

    def test_default_is_pull_request(self):
        d = infer_review_disposition_decision("LGTM")
        assert d.verdict == "pull_request"
        assert d.confidence == Confidence.MEDIUM


class TestDecisionDataclass:
    def test_as_dict_is_serializable(self):
        d = Decision(
            verdict="x",
            confidence=Confidence.MEDIUM,
            signals=("a", "b"),
            rationale="r",
        )
        out = d.as_dict()
        assert out == {
            "verdict": "x",
            "confidence": "medium",
            "signals": ["a", "b"],
            "rationale": "r",
        }

    def test_decision_is_frozen(self):
        d = Decision(verdict="x", confidence=Confidence.NONE)
        with pytest.raises(Exception):
            d.verdict = "y"  # type: ignore[misc]
