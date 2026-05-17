from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from agentic_solution.contracts import Severity


# ---------------------------------------------------------------------------
# Shared result types
# ---------------------------------------------------------------------------

class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    NONE = "none"


@dataclass(frozen=True)
class Decision:
    verdict: str
    confidence: Confidence = Confidence.NONE
    signals: Sequence[str] = field(default_factory=tuple)
    rationale: str = ""

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence.value,
            "signals": list(self.signals),
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Incident severity
# ---------------------------------------------------------------------------

_SEV1_MARKERS = ("sev1", "p1", "outage", "all customers", "critical")
_SEV2_MARKERS = ("sev2", "p2", "degraded", "partial outage")
_SEV3_MARKERS = ("sev3", "p3", "minor", "single tenant")


def infer_incident_severity(text: str) -> Severity:
    return infer_incident_severity_decision(text).verdict  # type: ignore[return-value]


def infer_incident_severity_decision(text: str) -> Decision:
    lowered = text.lower()

    sev1_hits = [m for m in _SEV1_MARKERS if m in lowered]
    if sev1_hits:
        confidence = Confidence.HIGH if len(sev1_hits) >= 2 else Confidence.MEDIUM
        return Decision(verdict="sev1", confidence=confidence, signals=tuple(sev1_hits))

    sev2_hits = [m for m in _SEV2_MARKERS if m in lowered]
    if sev2_hits:
        confidence = Confidence.HIGH if len(sev2_hits) >= 2 else Confidence.MEDIUM
        return Decision(verdict="sev2", confidence=confidence, signals=tuple(sev2_hits))

    sev3_hits = [m for m in _SEV3_MARKERS if m in lowered]
    if sev3_hits:
        confidence = Confidence.HIGH if len(sev3_hits) >= 2 else Confidence.MEDIUM
        return Decision(verdict="sev3", confidence=confidence, signals=tuple(sev3_hits))

    return Decision(verdict="unknown", confidence=Confidence.NONE)


# ---------------------------------------------------------------------------
# Bug handoff
# ---------------------------------------------------------------------------

def needs_bug_handoff(*parts: str) -> bool:
    # Bug handoff routing is classifier-driven (see orchestrator classifier prompt).
    # This heuristic deliberately returns False so the classifier remains the sole
    # authority — a heuristic-based gate was retired after it generated false positives.
    return False


def needs_bug_handoff_decision(*parts: str) -> Decision:
    return Decision(
        verdict="no",
        confidence=Confidence.HIGH,
        signals=(),
        rationale="Bug handoff is classifier-driven; this heuristic is intentionally a no-op stub.",
    )


# ---------------------------------------------------------------------------
# Code-change detection (contradiction guard)
# ---------------------------------------------------------------------------

_CODE_CHANGE_PATTERNS = (
    # diff fences / hunk headers
    r"```diff\b",
    r"^\s*---\s+a/",
    r"^\s*\+\+\+\s+b/",
    r"^@@\s",
    # explicit code mutation verbs
    r"\breplace\s+`",
    r"\breplace\s+\S+\s+with\s+",
    r"\bmodif(?:y|ied|ying)\s+line\b",
    r"\bedit(?:ed|ing)?\s+line\b",
    r"\bconvert(?:ed|ing)?\s+(?:the\s+)?(?:integer|int|string|str|value)\b",
    r"\bcast(?:ed|ing)?\s+\S+\s+to\b",
    r"\bwrap(?:ped|ping)?\s+\S+\s+(?:in|with)\s+`?str\b",
    # branches / commits / PRs
    r"\bcreate\s+(a\s+)?branch\b",
    r"\bcreate\s+(a\s+)?(new\s+)?pull request\b",
    r"\bopen(?:ed)?\s+(a\s+)?pr\b",
    r"\bfix/[\w\-/]+",
    r"\bpull/\d+\b",
    r"\bgithub\.com/\S+/pull/\d+",
    r"\bPR\s*#\s*\d+",
    # repo-specific file paths and code locations
    r"\bmicroservices/\S+\.py\b",
    r"\b\S+\.py[:#]\s*line\s*\d+",
    r"\bline\s+\d+\s+(?:in|of)\s+\S+\.py\b",
    r"\bat\s+line\s+\d+\b",
)


def _looks_like_code_change(text: str) -> bool:
    """Return True when text describes an actual code change.

    Used as a tie-breaker when a NON_CODE tag contradicts body that
    plainly describes editing files or opening a PR.
    """
    for pat in _CODE_CHANGE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def _critic_verdict(*parts: str) -> str | None:
    signal = " ".join(parts)
    m = re.search(
        r"\[STRATEGY_VERDICT:\s*(CODE|NON_CODE|UNCLEAR)\s*\]",
        signal,
        re.IGNORECASE,
    )
    return m.group(1).upper() if m else None


# ---------------------------------------------------------------------------
# Non-code resolution routing
# ---------------------------------------------------------------------------

def is_non_code_resolution(*parts: str) -> bool:
    return is_non_code_resolution_decision(*parts).verdict == "non_code"


def is_non_code_resolution_decision(*parts: str) -> Decision:
    """Decide whether to skip the Coder/Reviewer pipeline and route to Jira-only.

    Biased toward CODE: NON_CODE routing only sticks when there is zero
    evidence of a code change in the combined signal.

    Decision order:
    1. Critic verdict ([STRATEGY_VERDICT: ...]) — authoritative when present.
       NON_CODE is honored only if the same text contains no code-change evidence.
    2. Planner tag ([RESOLUTION_TYPE: NON_CODE]) or jira-only keyword —
       accepted only when the contradiction guard finds no code-change signals.
    """
    signal = " ".join(parts)
    looks_codey = _looks_like_code_change(signal)

    verdict = _critic_verdict(*parts)
    if verdict == "NON_CODE":
        if looks_codey:
            return Decision(
                verdict="code",
                confidence=Confidence.HIGH,
                signals=("contradiction_guard: critic NON_CODE overridden by code-change evidence",),
                rationale="Critic said NON_CODE but body contains code-change signals.",
            )
        return Decision(
            verdict="non_code",
            confidence=Confidence.HIGH,
            signals=(f"STRATEGY_VERDICT:NON_CODE",),
            rationale="Critic verdict NON_CODE with no contradicting code evidence.",
        )
    if verdict in ("CODE", "UNCLEAR"):
        return Decision(
            verdict="code",
            confidence=Confidence.HIGH,
            signals=(f"STRATEGY_VERDICT:{verdict}",),
            rationale=f"Critic verdict {verdict} routes to the coder pipeline.",
        )

    tag_present = bool(
        re.search(r"^\s*[-*]?\s*\[RESOLUTION_TYPE:\s*NON_CODE\]\s*$", signal, re.MULTILINE)
    )
    lowered = signal.lower()
    keyword_present = "jira-only" in lowered or "non-code" in lowered

    if not (tag_present or keyword_present):
        return Decision(
            verdict="code",
            confidence=Confidence.MEDIUM,
            signals=(),
            rationale="No NON_CODE signal found; defaulting to code pipeline.",
        )

    if looks_codey:
        return Decision(
            verdict="code",
            confidence=Confidence.HIGH,
            signals=("contradiction_guard: planner NON_CODE tag overridden by code-change evidence",),
            rationale="NON_CODE tag present but body describes a code change.",
        )

    source = "RESOLUTION_TYPE:NON_CODE tag" if tag_present else "non-code keyword"
    return Decision(
        verdict="non_code",
        confidence=Confidence.MEDIUM,
        signals=(source,),
        rationale=f"Routing to Jira-only based on {source}.",
    )


# ---------------------------------------------------------------------------
# Review disposition
# ---------------------------------------------------------------------------

def infer_review_disposition(text: str) -> str:
    return infer_review_disposition_decision(text).verdict


def infer_review_disposition_decision(text: str) -> Decision:
    tag = re.search(r"\[DECISION:\s*(APPROVE|JIRA_ONLY|REWORK)\]", text, re.IGNORECASE)
    if tag:
        decision = tag.group(1).upper()
        if decision == "REWORK":
            return Decision(verdict="rework_required", confidence=Confidence.HIGH, signals=(f"DECISION:{decision}",))
        if decision == "JIRA_ONLY":
            return Decision(verdict="jira_ticket", confidence=Confidence.HIGH, signals=(f"DECISION:{decision}",))
        return Decision(verdict="pull_request", confidence=Confidence.HIGH, signals=(f"DECISION:{decision}",))

    lowered = text.lower()
    if re.search(r"\b(rework required|requires rework|send back for rework|rejected)\b", lowered):
        return Decision(verdict="rework_required", confidence=Confidence.MEDIUM, signals=("rework phrase",))
    if "jira-only" in lowered or "non-code" in lowered:
        return Decision(verdict="jira_ticket", confidence=Confidence.MEDIUM, signals=("jira-only keyword",))
    return Decision(verdict="pull_request", confidence=Confidence.MEDIUM, signals=(), rationale="Default: no rejection signal.")
