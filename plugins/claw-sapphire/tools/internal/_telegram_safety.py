"""Pure-function safety primitives for the Sapphire Telegram operator console.

This module is the single place where the Telegram bot's safety posture is
declared. Everything in this file is intentionally:

* **Pure / no I/O at import** — the module can be imported during tests
  and during validate_tool_registry compile checks without touching the
  filesystem, hitting the network, or reading environment variables.
* **Stdlib-only** — no new dependencies. The bot already uses ``re``,
  ``time``, ``os``; this module sticks to that surface.
* **Fail-closed** — every helper either rejects or returns a generic
  refusal. None of them reveal which Telegram user IDs are allowed,
  what secret pattern matched, or what command was attempted.

The bot module imports from here. Tests import from here directly to
exercise the rules in isolation. The runbook at
``docs/ops/telegram-operator-console-runbook.md`` is the prose mirror.

Live trading is **always** disabled from Telegram. ``LIVE_TRADING_DISABLED_FROM_TELEGRAM``
below is read on every command path. Flipping it to ``False`` does not
unlock anything in the existing code — there is no command path that
queries it for permission. The constant exists as a tripwire: if a
future maintainer mutates it expecting trading to enable, the assertion
in :func:`assert_no_live_trading` will refuse first.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — these are deliberately set in stone in source control, not
# environment variables. Loosening them requires a code change + PR review.
# ---------------------------------------------------------------------------

LIVE_TRADING_DISABLED_FROM_TELEGRAM: bool = True
"""Hard tripwire. The Telegram bot must never place orders or move funds.

Read on every dispatched command. See :func:`assert_no_live_trading`."""

DEFAULT_RATE_LIMIT_PER_MINUTE: int = 10
"""Default per-user-per-minute command cap. Below the Telegram Bot API
sustained-send ceiling and well below human realistic operator velocity."""

DEFAULT_RATE_LIMIT_PER_HOUR: int = 60
"""Default per-user-per-hour command cap. Caps a runaway loop or compromised
session before it can exfiltrate by command volume alone."""

GENERIC_REFUSAL_TEXT: str = (
    "This Sapphire PM bot is not enabled for your Telegram user ID on this host."
)
"""Single generic refusal used by allowlist + forbidden-command + rate-limit
denials. Identical wording prevents a probe from learning *why* it was
rejected — only that it was."""

OPERATOR_ONLY_PHYSICAL_ACTION_TEXT: str = (
    "Operator-only physical action. Telegram cannot execute this command. "
    "Run it locally on the commander host with the appropriate confirmation flow."
)
"""Returned for any command in the forbidden list (trading, transfers,
key rotation, shell exec). Wording is unambiguous: this is policy, not bug."""

CONFIRM_TOKEN: str = "CONFIRM"
"""Suffix the operator must append to dangerous commands. Case-sensitive
on purpose — autocorrect / mobile keyboards rarely match a fully-uppercase
literal by accident, so an unintentional confirmation is unlikely."""


# ---------------------------------------------------------------------------
# Secret denylist — anything matching this is stripped from outgoing text.
# ---------------------------------------------------------------------------

_SECRET_KEYWORDS = (
    r"api[_\-\s]?key",
    r"api[_\-\s]?token",
    r"secret",
    r"password",
    r"passwd",
    r"bearer",
    r"authorization",
    r"private[_\-\s]?key",
    r"access[_\-\s]?token",
    r"refresh[_\-\s]?token",
    r"client[_\-\s]?secret",
    r"sk[_\-][A-Za-z0-9]{8,}",  # OpenAI-style key prefix
    r"xox[baprs]-[A-Za-z0-9\-]{8,}",  # Slack token prefix
    r"ghp_[A-Za-z0-9]{8,}",  # GitHub fine-grained / PAT
    r"AIza[0-9A-Za-z_\-]{8,}",  # Google API key prefix
)

SECRET_DENYLIST_RE = re.compile(
    r"(?i)\b(?:" + "|".join(_SECRET_KEYWORDS) + r")\b",
)
"""Case-insensitive regex that matches any of: ``api_key``/``api-key``/``api key``,
``token``-family keywords, ``secret``, ``password``, ``bearer``,
``authorization``, plus a few high-confidence vendor-specific key prefixes
(OpenAI ``sk-``, GitHub ``ghp_``, Slack ``xox*``, Google ``AIza``).

It is intentionally **broad**. False positives are acceptable —
``[REDACTED:secret]`` in a status message is fine. False negatives are not."""

REDACTED_PLACEHOLDER: str = "[REDACTED:secret]"
"""Placeholder substituted in place of any line that matches the denylist."""


def redact_secrets(text: str) -> str:
    """Replace any line containing a secret-like keyword with a redaction marker.

    Operates line-by-line so a single offending line does not poison an
    entire status report. Always returns a string; ``None``/non-str input
    is coerced to an empty string.

    Examples::

        >>> redact_secrets("user=ari\\nAPI_KEY=sk-abc123\\nstatus=ok")
        'user=ari\\n[REDACTED:secret]\\nstatus=ok'
        >>> redact_secrets("everything fine")
        'everything fine'
    """
    if not text:
        return ""
    out_lines: list[str] = []
    for line in str(text).splitlines():
        if SECRET_DENYLIST_RE.search(line):
            out_lines.append(REDACTED_PLACEHOLDER)
        else:
            out_lines.append(line)
    # Preserve trailing newline iff the input had one
    suffix = "\n" if str(text).endswith("\n") else ""
    return "\n".join(out_lines) + suffix


def contains_secret(text: str) -> bool:
    """Return True if ``text`` contains any secret-denylist keyword.

    Useful for assertions in tests and as a pre-send tripwire."""
    if not text:
        return False
    return bool(SECRET_DENYLIST_RE.search(str(text)))


# ---------------------------------------------------------------------------
# Forbidden command denylist — top-level commands that must never run from
# Telegram, regardless of any future command file that registers them.
# ---------------------------------------------------------------------------

FORBIDDEN_COMMAND_PATTERNS = (
    r"trade",
    r"buy",
    r"sell",
    r"transfer",
    r"withdraw",
    r"deposit",
    r"rotate[_\-]?key",
    r"rotate[_\-]?secret",
    r"launch",
    r"deploy",
    r"exec",
    r"eval",
    r"sudo",
    r"shell",
    r"bash",
    r"cmd",
    r"ssh",
    r"kill[_\-]?switch",
    r"wire",
    r"send[_\-]?funds",
)
"""Slash-command stems that are forbidden from Telegram. Matching is on the
first word after ``/``, case-insensitive, exact match — ``/transfer-anything``
matches ``transfer`` because we anchor on word boundary."""

FORBIDDEN_COMMAND_RE = re.compile(
    r"^/(" + "|".join(FORBIDDEN_COMMAND_PATTERNS) + r")(?:[\s_\-/]|$)",
    re.IGNORECASE,
)
"""Regex used by :func:`is_forbidden_command`. Anchored at start-of-line
so ``/help-trade`` or ``status: trade today`` do not match — only the
command verb itself."""


def is_forbidden_command(text: str) -> bool:
    """Return True if the message is a forbidden top-level command.

    The check fires even before allowlist evaluation in the bot dispatcher:
    a forbidden command from an allowed user is still rejected. This keeps
    the policy in source control rather than configuration."""
    if not text:
        return False
    return bool(FORBIDDEN_COMMAND_RE.match(str(text).strip()))


def assert_no_live_trading() -> None:
    """Hard-assert that live trading is disabled. Called on every command path.

    If a maintainer ever flips :data:`LIVE_TRADING_DISABLED_FROM_TELEGRAM`
    without removing this assertion, the bot will refuse to dispatch and
    log the violation rather than silently start trading."""
    if not LIVE_TRADING_DISABLED_FROM_TELEGRAM:  # pragma: no cover - tripwire
        raise RuntimeError(
            "LIVE_TRADING_DISABLED_FROM_TELEGRAM was flipped. The Telegram bot "
            "must never place orders. Revert this change or remove the bot."
        )


# ---------------------------------------------------------------------------
# Allowlist — fail-closed.
# ---------------------------------------------------------------------------


def _parse_allowed_user_ids(raw: str, *, source: str) -> set[int]:
    allowed: set[int] = set()
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        try:
            allowed.add(int(text))
        except ValueError:
            logger.warning("Ignoring invalid Telegram allowlist entry in %s: %r", source, text)
    return allowed


def _read_allowed_user_ids_file(path_text: str) -> set[int]:
    path = Path(path_text).expanduser()
    try:
        raw = path.read_text().strip()
    except OSError:
        logger.warning("Could not read Telegram allowlist file: %s", path)
        return set()
    if not raw:
        return set()
    return _parse_allowed_user_ids(raw, source=str(path))


def load_allowed_user_ids(
    env_var: str = "SAPPHIRE_PM_BOT_ALLOWED_USER_IDS",
    file_var: str = "SAPPHIRE_PM_BOT_ALLOWED_USER_IDS_FILE",
) -> set[int]:
    """Load Telegram user IDs from an environment variable, fail-closed.

    Empty / unset → empty set → allowlist denies everyone. Invalid entries
    are logged at WARNING and skipped — they never grant access.
    """
    raw = os.getenv(env_var, "")
    if raw.strip():
        return _parse_allowed_user_ids(raw, source=env_var)

    file_path = os.getenv(file_var, "").strip()
    if file_path:
        return _read_allowed_user_ids_file(file_path)

    return set()


def is_allowed(user_id: int | None, allowed: set[int]) -> bool:
    """Return True iff ``user_id`` is in ``allowed`` and not None.

    A ``None`` sender ID always denies — there is no anonymous-allow path."""
    if user_id is None:
        return False
    return int(user_id) in allowed


# ---------------------------------------------------------------------------
# Rate limiter — per-user sliding window.
# ---------------------------------------------------------------------------


@dataclass
class RateLimitDecision:
    """Result of a single rate-limit check.

    ``allowed`` is the only field callers should branch on. ``reason`` and
    ``retry_after_seconds`` are diagnostics for logs — never echoed to the
    operator (revealing the exact window would help an attacker pace).
    """

    allowed: bool
    reason: str = ""
    retry_after_seconds: float = 0.0


@dataclass
class RateLimiter:
    """Thread-safe per-user sliding-window rate limiter.

    Two windows: per-minute and per-hour. A command is allowed only if both
    windows have headroom. Memory bounded by ``max_users * per_hour`` ints.

    The limiter is intentionally in-process: the bot is a single LaunchAgent
    process. If we ever shard, this becomes a Redis ZSET — but until then
    the simpler in-memory deque is correct and testable.
    """

    per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    per_hour: int = DEFAULT_RATE_LIMIT_PER_HOUR
    _events: dict[int, deque[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, user_id: int, now: float | None = None) -> RateLimitDecision:
        """Record an attempt and return whether it is allowed.

        ``now`` is injectable for deterministic testing. The default uses
        ``time.time()`` so the limiter behaves correctly under wall-clock
        drift (we do not need monotonic — we want absolute windows)."""
        ts = float(now) if now is not None else time.time()
        with self._lock:
            queue = self._events.setdefault(int(user_id), deque())
            cutoff_hour = ts - 3600.0
            while queue and queue[0] < cutoff_hour:
                queue.popleft()
            cutoff_minute = ts - 60.0
            count_minute = sum(1 for t in queue if t >= cutoff_minute)
            count_hour = len(queue)
            if count_minute >= self.per_minute:
                oldest_in_window = next((t for t in queue if t >= cutoff_minute), ts)
                retry_after = max(0.0, (oldest_in_window + 60.0) - ts)
                return RateLimitDecision(False, "per_minute", retry_after)
            if count_hour >= self.per_hour:
                oldest = queue[0] if queue else ts
                retry_after = max(0.0, (oldest + 3600.0) - ts)
                return RateLimitDecision(False, "per_hour", retry_after)
            queue.append(ts)
            return RateLimitDecision(True)

    def reset(self, user_id: int | None = None) -> None:
        """Clear state for a single user or globally. Test-only convenience."""
        with self._lock:
            if user_id is None:
                self._events.clear()
            else:
                self._events.pop(int(user_id), None)


# ---------------------------------------------------------------------------
# Routine pause flag — file-based mechanism shared with scheduled tasks.
# ---------------------------------------------------------------------------

ROUTINE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
"""Whitelist for routine names. No path separators, no shell metacharacters,
length-bounded. Anything else is rejected outright."""


def is_valid_routine_name(name: str) -> bool:
    """Return True if ``name`` is a safe routine identifier.

    The bot uses this before reading or writing to the pause-flag directory.
    It rejects anything that could traverse out of the directory or
    interact with shell. The directory is operator-owned (``~/.sapphire``)
    so the consequences of a bad name are bounded, but defense-in-depth is
    cheap here."""
    if not name:
        return False
    return bool(ROUTINE_NAME_RE.match(str(name)))
