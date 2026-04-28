"""Tests for CommandGuard — sandbox policy enforcement and bypass prevention.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_command_guard.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "infra" / "sandbox"))
from command_guard import CommandGuard, GuardAction, _normalize_command

# ─── Policy fixture ────────────────────────────────────────────────────────────

_TEST_POLICY = {
    "test-agent": {
        "dangerous_commands": [
            "rm -rf",
            "eval",
            "bash -c",
            "sh -c",
            "python3 -c",
        ],
        "requires_confirmation": [
            "git push",
            "pip install",
        ],
    }
}


@pytest.fixture
def policy_file(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(_TEST_POLICY))
    return p


@pytest.fixture
def guard(policy_file):
    return CommandGuard("test-agent", policy_file=policy_file)


# ─── Normalization tests ───────────────────────────────────────────────────────


class TestNormalize:
    def test_collapses_whitespace(self):
        assert _normalize_command("rm   -rf   /") == "rm -rf /"

    def test_lowercases(self):
        assert _normalize_command("RM -RF /") == "rm -rf /"

    def test_strips_dollar_brace_var(self):
        assert _normalize_command("rm${IFS}-rf") == "rm -rf"

    def test_strips_dollar_var(self):
        assert _normalize_command("rm$IFS-rf") == "rm -rf"

    def test_strips_backticks(self):
        result = _normalize_command("`rm -rf /`")
        assert "`" not in result

    def test_strips_complex_ifs_bypass(self):
        # Classic ${IFS} bypass
        result = _normalize_command("rm${IFS}-rf${IFS}/")
        assert "rm" in result
        assert "-rf" in result
        assert "${ifs}" not in result

    def test_strips_multiple_vars(self):
        result = _normalize_command("$FOO${BAR}cmd$BAZ")
        assert "$foo" not in result
        assert "${bar}" not in result


# ─── Block tests ───────────────────────────────────────────────────────────────


class TestBlock:
    def test_blocks_rm_rf(self, guard):
        result = guard.check("rm -rf /")
        assert result.action == GuardAction.BLOCK

    def test_blocks_rm_rf_uppercase(self, guard):
        result = guard.check("RM -RF /")
        assert result.action == GuardAction.BLOCK

    def test_blocks_eval(self, guard):
        result = guard.check("eval some_dangerous_code")
        assert result.action == GuardAction.BLOCK

    def test_blocks_bash_c(self, guard):
        result = guard.check("bash -c 'rm -rf /'")
        assert result.action == GuardAction.BLOCK

    def test_blocks_sh_c(self, guard):
        result = guard.check("sh -c 'rm -rf /'")
        assert result.action == GuardAction.BLOCK

    def test_blocks_python3_c(self, guard):
        result = guard.check("python3 -c 'import os; os.system(\"rm -rf /\")'")
        assert result.action == GuardAction.BLOCK

    def test_blocks_ifs_bypass(self, guard):
        # ${IFS} bypass should be caught after normalization
        result = guard.check("rm${IFS}-rf${IFS}/")
        assert result.action == GuardAction.BLOCK

    def test_blocks_dollar_ifs_bypass(self, guard):
        result = guard.check("rm$IFS-rf")
        assert result.action == GuardAction.BLOCK

    def test_block_has_reason(self, guard):
        result = guard.check("rm -rf /home")
        assert result.reason
        assert "rm -rf" in result.reason

    def test_block_priority_over_confirm(self, guard):
        # "git push" requires confirmation but contains "bash" which blocks
        # If we had both categories — block should win
        result = guard.check("bash -c 'git push'")
        assert result.action == GuardAction.BLOCK


# ─── Confirmation tests ────────────────────────────────────────────────────────


class TestConfirm:
    def test_requires_confirm_git_push(self, guard):
        result = guard.check("git push origin main")
        assert result.action == GuardAction.CONFIRM

    def test_requires_confirm_pip_install(self, guard):
        result = guard.check("pip install requests")
        assert result.action == GuardAction.CONFIRM

    def test_confirm_has_reason(self, guard):
        result = guard.check("git push origin main")
        assert result.reason
        assert result.matched_rule


# ─── Allow tests ───────────────────────────────────────────────────────────────


class TestAllow:
    def test_allows_safe_command(self, guard):
        result = guard.check("ls -la")
        assert result.action == GuardAction.ALLOW

    def test_allows_echo(self, guard):
        result = guard.check("echo hello")
        assert result.action == GuardAction.ALLOW

    def test_allows_empty_command(self, guard):
        result = guard.check("")
        assert result.action == GuardAction.ALLOW

    def test_allows_whitespace_only(self, guard):
        result = guard.check("   ")
        assert result.action == GuardAction.ALLOW

    def test_is_allowed_shortcut(self, guard):
        assert guard.is_allowed("echo hello") is True
        assert guard.is_allowed("rm -rf /") is False


# ─── Batch tests ───────────────────────────────────────────────────────────────


class TestBatch:
    def test_check_batch_mixed(self, guard):
        results = guard.check_batch(["echo hello", "rm -rf /", "git push"])
        assert results[0].action == GuardAction.ALLOW
        assert results[1].action == GuardAction.BLOCK
        assert results[2].action == GuardAction.CONFIRM

    def test_check_batch_empty(self, guard):
        assert guard.check_batch([]) == []


# ─── Missing policy tests ──────────────────────────────────────────────────────


class TestMissingPolicy:
    def test_unknown_component_defaults_confirm(self, policy_file):
        g = CommandGuard("nonexistent-component", policy_file=policy_file)
        result = g.check("rm -rf /")
        # No policy = fail-closed CONFIRM (C-CMD-2 audit fix).
        # Opt-out via `allow_all: true` in the component's policy entry.
        assert result.action == GuardAction.CONFIRM

    def test_reload_picks_up_changes(self, guard, policy_file):
        # Add new pattern
        new_policy = dict(_TEST_POLICY)
        new_policy["test-agent"]["dangerous_commands"].append("curl")
        policy_file.write_text(json.dumps(new_policy))
        guard.reload()
        result = guard.check("curl http://evil.com")
        assert result.action == GuardAction.BLOCK


# ─── Guard result properties ───────────────────────────────────────────────────


class TestGuardResult:
    def test_allowed_property(self, guard):
        result = guard.check("echo hello")
        assert result.allowed is True

    def test_blocked_not_allowed(self, guard):
        result = guard.check("rm -rf /")
        assert result.allowed is False

    def test_confirm_not_allowed(self, guard):
        result = guard.check("git push")
        assert result.allowed is False

    def test_requires_confirmation_property(self, guard):
        result = guard.check("git push")
        assert result.requires_confirmation is True

    def test_block_not_requires_confirmation(self, guard):
        result = guard.check("rm -rf /")
        assert result.requires_confirmation is False
