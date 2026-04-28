"""Command Guard — sandbox policy enforcement for Sapphire OS components.

Checks commands against sandbox_policy.json before execution. Blocks
dangerous commands outright; flags commands requiring confirmation.

Usage (in hermes-agent or any command executor):
    from command_guard import CommandGuard, GuardResult

    guard = CommandGuard(component="hermes-agent")
    result = guard.check("git push origin main")
    if result.blocked:
        raise PermissionError(result.reason)
    if result.requires_confirmation:
        # ask firewall for approval
        ...
    # safe to execute
    subprocess.run(...)

Wire into hermes-agent by patching the shell execution path:
    guard.execute("git push origin main")  # raises on block, prompts on confirm
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

POLICY_FILE = Path(__file__).parent / "sandbox_policy.json"


class GuardAction(Enum):
    ALLOW = "allow"
    BLOCK = "block"  # Always denied — dangerous command
    CONFIRM = "confirm"  # Allowed after confirmation


@dataclass
class GuardResult:
    action: GuardAction
    command: str
    reason: str = ""
    matched_rule: str = ""

    @property
    def allowed(self) -> bool:
        return self.action == GuardAction.ALLOW

    @property
    def blocked(self) -> bool:
        return self.action == GuardAction.BLOCK

    @property
    def requires_confirmation(self) -> bool:
        return self.action == GuardAction.CONFIRM


def _load_policy() -> dict:
    """Load sandbox_policy.json. Returns empty dict on failure."""
    try:
        return json.loads(POLICY_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.error("CommandGuard: failed to load policy: %s", e)
        return {}


def _normalize_command(cmd: str) -> str:
    """Collapse whitespace, strip shell variable references, and lowercase.

    Strips ``${VAR}`` and ``$VAR`` expansions so bypass tricks like
    ``${IFS}rm${IFS}-rf`` are reduced to ``rm -rf`` before pattern matching.
    Also collapses backtick command substitution markers.
    """
    import re as _re

    # Remove ${VAR} and $VAR style shell variable references
    cmd = _re.sub(r"\$\{[^}]*\}", " ", cmd)
    cmd = _re.sub(r"\$[A-Za-z_][A-Za-z0-9_]*", " ", cmd)
    # Remove backtick command substitution delimiters
    cmd = cmd.replace("`", " ")
    return " ".join(cmd.strip().split()).lower()


def _matches_pattern(command: str, pattern: str) -> bool:
    """Check if command contains a pattern (case-insensitive substring or regex)."""
    try:
        return bool(re.search(re.escape(pattern.lower()), command, re.IGNORECASE))
    except re.error:
        return pattern.lower() in command


class CommandGuard:
    """Enforces sandbox policy for a named Sapphire component."""

    def __init__(self, component: str, policy_file: Path | None = None):
        self.component = component
        self._policy_file = policy_file or POLICY_FILE
        self._policy = self._load_component_policy()

    def _load_component_policy(self) -> dict:
        try:
            all_policies = json.loads(self._policy_file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.error("CommandGuard: cannot load policy file %s: %s", self._policy_file, e)
            return {}
        policy = all_policies.get(self.component, {})
        if not policy:
            log.warning(
                "CommandGuard: no policy for component '%s' — fail-closed (CONFIRM required)",
                self.component,
            )
        return policy

    def reload(self) -> None:
        """Reload policy from disk (use after policy file changes)."""
        self._policy = self._load_component_policy()

    def check(self, command: str) -> GuardResult:
        """Check a command string against this component's sandbox policy.

        Returns GuardResult with action ALLOW / BLOCK / CONFIRM.
        BLOCK takes priority over CONFIRM.
        Fails closed: unknown components require confirmation unless policy
        opts in via `allow_all: true`.
        """
        if not command or not command.strip():
            return GuardResult(GuardAction.ALLOW, command, "empty command")

        # Fail-closed: no policy for this component → CONFIRM by default.
        # Operator may opt in with `"allow_all": true` inside the policy block.
        if not self._policy:
            reason = (
                f"No sandbox policy for component '{self.component}' — "
                f"fail-closed default (set `allow_all: true` to opt out)."
            )
            return GuardResult(GuardAction.CONFIRM, command, reason)
        if self._policy.get("allow_all") is True:
            return GuardResult(GuardAction.ALLOW, command, "allow_all in policy")

        normalized = _normalize_command(command)
        dangerous = self._policy.get("dangerous_commands", [])
        confirm = self._policy.get("requires_confirmation", [])

        # ── Block check (hard deny) ───────────────────────────────────────────
        for pattern in dangerous:
            if _matches_pattern(normalized, pattern):
                reason = f"Blocked by sandbox policy: matches dangerous pattern '{pattern}'"
                log.warning("CommandGuard[%s] BLOCKED: %s | %s", self.component, command, reason)
                return GuardResult(GuardAction.BLOCK, command, reason, pattern)

        # ── Confirmation check ────────────────────────────────────────────────
        for pattern in confirm:
            if _matches_pattern(normalized, pattern):
                reason = f"Requires confirmation: matches policy rule '{pattern}'"
                log.info("CommandGuard[%s] CONFIRM: %s | %s", self.component, command, reason)
                return GuardResult(GuardAction.CONFIRM, command, reason, pattern)

        return GuardResult(GuardAction.ALLOW, command, "within policy")

    def check_batch(self, commands: list[str]) -> list[GuardResult]:
        """Check multiple commands. Returns results in order."""
        return [self.check(cmd) for cmd in commands]

    def is_allowed(self, command: str) -> bool:
        """Quick check — True only if command is allowed without confirmation."""
        return self.check(command).allowed

    def execute(
        self,
        command: str,
        confirm_fn=None,
        shell: bool = True,
        capture_output: bool = True,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """Check and execute a shell command.

        Args:
            command:    Shell command string to execute
            confirm_fn: Optional callable(command, result) → bool for CONFIRM actions.
                        If None, CONFIRM actions raise PermissionError.
            shell:      Pass to subprocess.run
            capture_output: Pass to subprocess.run

        Raises:
            PermissionError: if command is BLOCKED or CONFIRM without confirm_fn returning True
        """
        result = self.check(command)

        if result.blocked:
            raise PermissionError(
                f"[sandbox] Command blocked by {self.component} policy: {command!r}\n"
                f"Reason: {result.reason}"
            )

        if result.requires_confirmation:
            if confirm_fn is None:
                raise PermissionError(
                    f"[sandbox] Command requires confirmation but no confirm_fn provided: {command!r}\n"
                    f"Rule: {result.matched_rule}"
                )
            approved = confirm_fn(command, result)
            if not approved:
                raise PermissionError(f"[sandbox] Command not approved: {command!r}")

        log.debug("CommandGuard[%s] executing: %s", self.component, command)
        return subprocess.run(
            command,
            shell=shell,
            capture_output=capture_output,
            text=True,
            **kwargs,
        )

    def audit_commands(self, commands: list[str]) -> dict:
        """Audit a list of commands and return a summary report."""
        results = self.check_batch(commands)
        blocked = [r for r in results if r.blocked]
        confirm = [r for r in results if r.requires_confirmation]
        allowed = [r for r in results if r.allowed]

        return {
            "component": self.component,
            "total": len(results),
            "allowed": len(allowed),
            "requires_confirmation": len(confirm),
            "blocked": len(blocked),
            "blocked_commands": [(r.command, r.matched_rule) for r in blocked],
            "confirm_commands": [(r.command, r.matched_rule) for r in confirm],
        }


# ─── Module-level convenience ─────────────────────────────────────────────────

_guards: dict[str, CommandGuard] = {}


def get_guard(component: str) -> CommandGuard:
    """Get or create a singleton CommandGuard for a component."""
    if component not in _guards:
        _guards[component] = CommandGuard(component)
    return _guards[component]


def check(component: str, command: str) -> GuardResult:
    """One-liner check: get_guard(component).check(command)."""
    return get_guard(component).check(command)


# ─── CLI entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check a command against Sapphire sandbox policy")
    parser.add_argument("component", help="Component name (e.g. hermes-agent)")
    parser.add_argument("command", help="Command to check")
    args = parser.parse_args()

    guard = CommandGuard(args.component)
    result = guard.check(args.command)

    icon = {"allow": "✓", "block": "✗", "confirm": "?"}.get(result.action.value, "?")
    print(f"{icon} [{result.action.value.upper()}] {args.command!r}")
    if result.reason:
        print(f"  Reason: {result.reason}")
    sys.exit(0 if result.allowed else 1)
