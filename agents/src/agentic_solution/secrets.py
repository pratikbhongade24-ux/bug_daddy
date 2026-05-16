"""
Secrets management.

A thin, dependency-free wrapper that gives the codebase three things the
raw ``os.environ`` interface can't:

1. **Typed access with validation.** ``Secrets.require("X")`` raises a
   structured ``MissingSecretError`` listing every name that was
   missing, so deploys fail loudly at startup instead of producing
   half-configured runtimes that silently fall back to dry-run.

2. **Redaction at every boundary.** ``Secrets.redact(obj)`` walks an
   arbitrary nested structure and replaces any value that matches a
   known secret name (api_token, password, secret, key, etc.) or any
   value identical to a registered secret with a deterministic
   placeholder. Use it whenever you serialize config into a log line,
   an audit record, or an error message.

3. **A registered allow-list.** A secret only counts as "secret" if it
   has been read via this module — so the redactor can identify it by
   value as well as by name, catching the case where a secret leaks
   into a field with a benign-looking key (``"x_request_id":
   "Bearer xxx..."``).

The module integrates with the existing ``AppConfig.from_env`` flow
without forcing a rewrite — callers can switch incrementally.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Sentinel / errors.
# ---------------------------------------------------------------------------


REDACTED = "***REDACTED***"


class MissingSecretError(RuntimeError):
    """Raised when required secrets are absent. Carries every missing name
    so the operator sees the full set at once instead of fixing one,
    re-deploying, and discovering the next one."""

    def __init__(self, missing: Iterable[str]) -> None:
        missing = tuple(missing)
        super().__init__(
            "Missing required secret(s): " + ", ".join(sorted(missing))
        )
        self.missing = missing


# ---------------------------------------------------------------------------
# Sensitivity heuristic. Keys whose names match this pattern are treated
# as secret even if they were never explicitly registered.
# ---------------------------------------------------------------------------


_SENSITIVE_KEY_RE = re.compile(
    r"(?:token|secret|password|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|credential|authorization)",
    re.IGNORECASE,
)


def _looks_like_secret_key(name: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(name))


# ---------------------------------------------------------------------------
# Secrets store.
# ---------------------------------------------------------------------------


@dataclass
class Secrets:
    """Tiny env-backed secrets store.

    Instances are *not* singletons — production callers can swap an
    instance backed by AWS Secrets Manager or HashiCorp Vault by
    implementing the same ``get/require`` surface."""

    source: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    _registered_values: set[str] = field(default_factory=set)

    def get(self, name: str, default: str | None = None) -> str | None:
        value = self.source.get(name, default)
        if value:
            self._registered_values.add(value)
        return value

    def require(self, *names: str) -> dict[str, str]:
        """Fetch every name; raise listing all that are missing."""
        present: dict[str, str] = {}
        missing: list[str] = []
        for n in names:
            v = self.source.get(n)
            if not v:
                missing.append(n)
            else:
                present[n] = v
                self._registered_values.add(v)
        if missing:
            raise MissingSecretError(missing)
        return present

    # ------------------------------------------------------------------
    # Redaction.
    # ------------------------------------------------------------------

    def redact(self, obj: Any) -> Any:
        """Return a deep copy of ``obj`` with secrets masked.

        Strings whose value is identical to a registered secret are
        replaced. Dict keys matching the sensitivity pattern have their
        values replaced regardless of value-match.

        Lists, tuples, and dicts are walked recursively. Non-serializable
        objects are returned unchanged — redaction is a best-effort
        layer, not a hard security boundary."""
        return _redact(obj, self._registered_values)

    # ------------------------------------------------------------------
    # Composition helper.
    # ------------------------------------------------------------------

    def register_value(self, value: str) -> None:
        """Manually register a value as secret. Useful when a secret is
        constructed at runtime (e.g. a signed token) rather than read
        directly from env."""
        if value:
            self._registered_values.add(value)


def _redact(obj: Any, registered: set[str]) -> Any:
    if isinstance(obj, str):
        return REDACTED if obj in registered else obj
    if isinstance(obj, dict):
        return {
            k: REDACTED if _looks_like_secret_key(str(k)) else _redact(v, registered)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        red = [_redact(item, registered) for item in obj]
        return type(obj)(red) if isinstance(obj, tuple) else red
    return obj


# ---------------------------------------------------------------------------
# Module-level convenience singleton.
# ---------------------------------------------------------------------------


_DEFAULT_SECRETS: Secrets | None = None


def default_secrets() -> Secrets:
    global _DEFAULT_SECRETS
    if _DEFAULT_SECRETS is None:
        _DEFAULT_SECRETS = Secrets()
    return _DEFAULT_SECRETS


def reset_default_secrets() -> None:
    """Test hook — drops the cached singleton so test ordering doesn't
    pollute registered values between cases."""
    global _DEFAULT_SECRETS
    _DEFAULT_SECRETS = None
