"""
Routing heuristics for the original three-runtime workflow.

This module is the single point where free-form agent text becomes a
discrete routing decision (severity tier, bug hand-off, non-code
resolution, reviewer disposition). Because every such decision can
silently skip the coder pipeline or escalate an incident, every public
function in this module returns either:

  * a typed verdict that callers MUST treat as authoritative, or
  * a `Decision` envelope carrying both the verdict AND the confidence
    score + matched signals that produced it.

Callers that need to audit *why* a routing decision was made should
prefer the ``*_with_decision`` variants. The plain-verdict variants are
preserved for backwards compatibility with the existing services.

Design rules enforced here:

1. **Critic verdict is authoritative.** When the Critic Agent emits a
   ``[STRATEGY_VERDICT: ...]`` tag the heuristic respects it and the
   confidence is ``HIGH`` — keyword sweeps never override the critic.
2. **Contradiction guard.** A planner tag claiming ``NON_CODE`` is
   *ignored* when the same text contains diff fences or PR references.
   A self-contradictory tag is a bug, not a signal.
3. **Reproducibility.** Every regex and keyword set is module-level and
   immutable. The heuristic is a pure function of its inputs — there is
   no environment, no clock, no LLM call. The same inputs always
   produce the same `Decision`.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from agentic_solution.contracts import Severity

# ---------------------------------------------------------------------------
# Public types.
# ---------------------------------------------------------------------------


class Confidence(str, enum.Enum):
    """Confidence in a heuristic verdict.

    * ``HIGH``   — an authoritative signal was present (critic verdict,
                   explicit decision tag, structured CVSS, etc.).
    * ``MEDIUM`` — multiple weak signals agree.
    * ``LOW``    — only a single weak keyword matched.
    * ``NONE``   — no signal; the result is the conservative default.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass(frozen=True)
class Decision:
    """Heuristic verdict with auditable provenance.

    `verdict` is the routing answer. `confidence` lets the caller decide
    whether to act autonomously or ask a human. `signals` is the
    enumerated list of matched patterns — exposed so the audit journal
    can record exactly *why* a routing decision was made."""

    verdict: str
    confidence: Confidence
    signals: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence.value,
            "signals": list(self.signals),
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Internal pattern tables. Kept module-level so they are compiled once.
# ---------------------------------------------------------------------------


_SEV1_MARKERS: tuple[str, ...] = (
    "sev1", "p1", "outage", "all customers", "critical",
)
_SEV2_MARKERS: tuple[str, ...] = (
    "sev2", "p2", "degraded", "partial outage",
)
_SEV3_MARKERS: tuple[str, ...] = (
    "sev3", "p3", "minor", "single tenant",
)


_CODE_CHANGE_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE | re.MULTILINE) for p in (
        r"```diff\b",
        r"^\s*---\s+a/",
        r"^\s*\+\+\+\s+b/",
        r"^@@\s",
        r"\breplace\s+`",
        r"\breplace\s+\S+\s+with\s+",
        r"\bcreate\s+(a\s+)?branch\b",
        r"\bcreate\s+(a\s+)?(new\s+)?pull request\b",
        r"\bopen(?:ed)?\s+(a\s+)?pr\b",
        r"\bfix/[\w\-/]+",
        r"\bmicroservices/\S+\.py\b",
        r"\bpull/\d+\b",
        r"\bgithub\.com/\S+/pull/\d+",
    )
)


_CRITIC_VERDICT_RE = re.compile(
    r"\[STRATEGY_VERDICT:\s*(CODE|NON_CODE|UNCLEAR)\s*\]",
    re.IGNORECASE,
)
_RESOLUTION_TAG_RE = re.compile(
    r"^\s*[-*]?\s*\[RESOLUTION_TYPE:\s*NON_CODE\]\s*$",
    re.MULTILINE,
)
_DECISION_TAG_RE = re.compile(
    r"\[DECISION:\s*(APPROVE|JIRA_ONLY|REWORK)\]",
    re.IGNORECASE,
)
_REWORK_PHRASES_RE = re.compile(
    r"\b(rework required|requires rework|send back for rework|rejected)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public heuristics.
# ---------------------------------------------------------------------------


def infer_incident_severity(text: str) -> Severity:
    """Backwards-compatible verdict-only variant."""
    return infer_incident_severity_decision(text).verdict  # type: ignore[return-value]


def infer_incident_severity_decision(text: str) -> Decision:
    """Decide a severity tier with auditable provenance.

    Order: SEV1 markers > SEV2 markers > SEV3 markers > ``unknown``. The
    first matching tier wins; this is intentionally a *floor* rather
    than a vote — incident triage prefers false-high to false-low."""
    lowered = (text or "").lower()
    matched = _collect_markers(lowered, _SEV1_MARKERS)
    if matched:
        return Decision(
            verdict="sev1",
            confidence=_marker_confidence(matched),
            signals=matched,
            rationale="SEV1 markers present",
        )
    matched = _collect_markers(lowered, _SEV2_MARKERS)
    if matched:
        return Decision(
            verdict="sev2",
            confidence=_marker_confidence(matched),
            signals=matched,
            rationale="SEV2 markers present",
        )
    matched = _collect_markers(lowered, _SEV3_MARKERS)
    if matched:
        return Decision(
            verdict="sev3",
            confidence=_marker_confidence(matched),
            signals=matched,
            rationale="SEV3 markers present",
        )
    return Decision(
        verdict="unknown",
        confidence=Confidence.NONE,
        signals=(),
        rationale="no severity markers matched",
    )


def needs_bug_handoff(*parts: str) -> bool:
    """Backwards-compatible verdict-only variant.

    The bug-handoff inference was previously disabled because the
    keyword sweep fired too broadly. The new behavior delegates to the
    classifier-driven routing in the services layer; this helper only
    returns ``False`` so legacy callers continue to compile, and the
    decision variant explains the deprecation."""
    return needs_bug_handoff_decision(*parts).verdict == "yes"


def needs_bug_handoff_decision(*parts: str) -> Decision:
    return Decision(
        verdict="no",
        confidence=Confidence.NONE,
        signals=(),
        rationale=(
            "bug handoff is now decided by the classifier service, not "
            "by keyword heuristics — see services/classifier.py"
        ),
    )


def is_non_code_resolution(*parts: str) -> bool:
    return is_non_code_resolution_decision(*parts).verdict == "yes"


def is_non_code_resolution_decision(*parts: str) -> Decision:
    """Decide whether the Coder / Reviewer pipeline should be skipped.

    Decision order is identical to the legacy function:
    1. Critic verdict (HIGH confidence) if present.
    2. Planner tag / keyword scan, with the contradiction guard against
       text that simultaneously describes a code change.
    """
    signal = " ".join(p for p in parts if p)

    verdict = _critic_verdict(signal)
    if verdict == "NON_CODE":
        return Decision(
            verdict="yes",
            confidence=Confidence.HIGH,
            signals=("STRATEGY_VERDICT:NON_CODE",),
            rationale="critic verdict authoritative",
        )
    if verdict in ("CODE", "UNCLEAR"):
        return Decision(
            verdict="no",
            confidence=Confidence.HIGH,
            signals=(f"STRATEGY_VERDICT:{verdict}",),
            rationale="critic verdict authoritative",
        )

    tag_present = bool(_RESOLUTION_TAG_RE.search(signal))
    lowered = signal.lower()
    keyword_present = "jira-only" in lowered or "non-code" in lowered

    if not (tag_present or keyword_present):
        return Decision(
            verdict="no",
            confidence=Confidence.NONE,
            signals=(),
            rationale="no resolution-type tag or keyword",
        )

    if _looks_like_code_change(signal):
        return Decision(
            verdict="no",
            confidence=Confidence.MEDIUM,
            signals=("contradiction_guard:code_change_present",),
            rationale=(
                "planner tagged NON_CODE but body describes a code change; "
                "tag treated as a self-contradiction"
            ),
        )

    matched: list[str] = []
    if tag_present:
        matched.append("RESOLUTION_TYPE:NON_CODE")
    if keyword_present:
        matched.append("keyword:jira-only/non-code")
    return Decision(
        verdict="yes",
        confidence=Confidence.MEDIUM if tag_present else Confidence.LOW,
        signals=tuple(matched),
        rationale="non-code resolution detected without contradicting signals",
    )


def infer_review_disposition(text: str) -> str:
    return infer_review_disposition_decision(text).verdict


def infer_review_disposition_decision(text: str) -> Decision:
    """Decide reviewer disposition from final-step output.

    Tag wins over keyword sweep. Tag presence = HIGH confidence; keyword
    fallbacks = MEDIUM; otherwise MEDIUM ``pull_request`` default since
    the existing pipeline opens a PR if no rejection signal is present."""
    raw = text or ""
    tag = _DECISION_TAG_RE.search(raw)
    if tag:
        decision_raw = tag.group(1).upper()
        if decision_raw == "REWORK":
            return Decision(
                verdict="rework_required",
                confidence=Confidence.HIGH,
                signals=("DECISION:REWORK",),
                rationale="reviewer decision tag authoritative",
            )
        if decision_raw == "JIRA_ONLY":
            return Decision(
                verdict="jira_ticket",
                confidence=Confidence.HIGH,
                signals=("DECISION:JIRA_ONLY",),
                rationale="reviewer decision tag authoritative",
            )
        return Decision(
            verdict="pull_request",
            confidence=Confidence.HIGH,
            signals=("DECISION:APPROVE",),
            rationale="reviewer decision tag authoritative",
        )

    lowered = raw.lower()
    if _REWORK_PHRASES_RE.search(lowered):
        return Decision(
            verdict="rework_required",
            confidence=Confidence.MEDIUM,
            signals=("phrase:rework",),
            rationale="explicit rework phrase detected",
        )
    if "jira-only" in lowered or "non-code" in lowered:
        return Decision(
            verdict="jira_ticket",
            confidence=Confidence.MEDIUM,
            signals=("keyword:jira-only/non-code",),
            rationale="non-code keyword detected",
        )
    return Decision(
        verdict="pull_request",
        confidence=Confidence.MEDIUM,
        signals=(),
        rationale="default disposition when no rejection signal present",
    )


# ---------------------------------------------------------------------------
# Internals.
# ---------------------------------------------------------------------------


def _collect_markers(lowered: str, markers: Iterable[str]) -> tuple[str, ...]:
    return tuple(m for m in markers if m in lowered)


def _marker_confidence(matched: tuple[str, ...]) -> Confidence:
    if not matched:
        return Confidence.NONE
    return Confidence.HIGH if len(matched) >= 2 else Confidence.MEDIUM


def _critic_verdict(signal: str) -> str | None:
    m = _CRITIC_VERDICT_RE.search(signal)
    return m.group(1).upper() if m else None


def _looks_like_code_change(text: str) -> bool:
    return any(p.search(text) for p in _CODE_CHANGE_PATTERNS)
