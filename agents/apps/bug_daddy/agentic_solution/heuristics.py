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
    # Circuit breaker: bug handoff disabled — heuristic fires too broadly
    return False


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
    r"\bfix/[\w\-/]+",                # branch names like fix/foo-bar
    r"\bpull/\d+\b",                  # PR refs like pull/46
    r"\bgithub\.com/\S+/pull/\d+",    # PR URLs
    r"\bPR\s*#\s*\d+",                # PR #48
    # repo-specific file paths and code locations
    r"\bmicroservices/\S+\.py\b",
    r"\b\S+\.py[:#]\s*line\s*\d+",   # foo.py: line 63
    r"\bline\s+\d+\s+(?:in|of)\s+\S+\.py\b",
    r"\bat\s+line\s+\d+\b",          # "at line 63"
)


def _looks_like_code_change(text: str) -> bool:
    """Heuristic: does ``text`` describe an actual code change?

    Used as a tie-breaker when the planner's NON_CODE tag contradicts a body that
    plainly describes editing files / opening a PR.
    """
    import re
    for pat in _CODE_CHANGE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def _critic_verdict(*parts: str) -> str | None:
    """Extract the Critic Agent's [STRATEGY_VERDICT: ...] tag if present.

    Returns one of "CODE" / "NON_CODE" / "UNCLEAR", or None when no verdict tag
    was emitted (e.g. older critic outputs that pre-date the prompt change).
    """
    import re
    signal = " ".join(parts)
    m = re.search(
        r"\[STRATEGY_VERDICT:\s*(CODE|NON_CODE|UNCLEAR)\s*\]",
        signal,
        re.IGNORECASE,
    )
    return m.group(1).upper() if m else None


def is_non_code_resolution(*parts: str) -> bool:
    """Decide whether to skip the Coder/Reviewer pipeline and route to Jira-only.

    Biased toward CODE: a NON_CODE routing only sticks when there is zero
    evidence of a code change in the combined signal.

    Decision order:
    1. **Critic verdict** — if the Critic Agent emitted
       ``[STRATEGY_VERDICT: ...]``: CODE/UNCLEAR → run the pipeline. NON_CODE
       is honored ONLY if the same text contains no code-change evidence
       (diff blocks, branch names, PR refs, file:line, etc.); otherwise the
       verdict contradicts its own context and is overridden to CODE.
    2. **Planner tag with contradiction guard** — fall back to detecting
       ``[RESOLUTION_TYPE: NON_CODE]`` or jira-only/non-code keywords, BUT
       ignore the tag if the same text also describes a code change.
    """
    signal = " ".join(parts)
    looks_codey = _looks_like_code_change(signal)

    verdict = _critic_verdict(*parts)
    if verdict == "NON_CODE":
        # Contradiction guard: critic said NON_CODE but the strategy text
        # plainly describes a code fix. Trust the evidence, not the tag.
        if looks_codey:
            return False
        return True
    if verdict in ("CODE", "UNCLEAR"):
        return False

    # No critic verdict available — fall back to the planner tag / keyword scan.
    import re
    tag_present = bool(
        re.search(r"^\s*[-*]?\s*\[RESOLUTION_TYPE:\s*NON_CODE\]\s*$", signal, re.MULTILINE)
    )
    lowered = signal.lower()
    keyword_present = "jira-only" in lowered or "non-code" in lowered

    if not (tag_present or keyword_present):
        return False

    # Tie-break: if the same text also describes a real code change, the tag is wrong.
    if looks_codey:
        return False
    return True


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

    # Fallback for responses without the tag — require explicit rejection phrases
    lowered = text.lower()
    if re.search(r"\b(rework required|requires rework|send back for rework|rejected)\b", lowered):
        return "rework_required"
    if "jira-only" in lowered or "non-code" in lowered:
        return "jira_ticket"
    return "pull_request"
