"""Smoke test: every audited runbook ships ≥ 3 syntactically valid bash commands.

Tranche 7-C lift (docs/ops/runbook-coverage-audit-2026-04-29.md). Each runbook
listed in `LIFTED_RUNBOOKS` corresponds to an operational surface that the
2026-04-29 audit flagged for uplift. This test enforces the contract that
operators inherit from the runbook lift:

1. The runbook markdown file exists at the expected path.
2. It contains at least three fenced ```bash``` (or unlabelled) command blocks.
3. The first three blocks parse with `bash -n` (syntax check, no execution).

The test deliberately does NOT execute the commands. Full live drills require a
live Sapphire mesh and are tracked separately. This test catches syntax
regressions when a runbook gets edited and a quote, continuation, or
heredoc fence drifts.

Trading-critical-path runbooks (`webhook-runbook.md`,
`trading-shadow-runbook.md`, `tranche5-live-soak-runbook.md`) are deliberately
NOT in this set. They are gated by a separate review track per
`AGENTS.md` ownership rules; smoke-testing them here would imply this lane
covers them, which it does not.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = REPO_ROOT / "docs" / "ops"

# Runbooks lifted in Tranche 7-C. Each is a non-trading-critical-path
# operational surface from the 2026-04-29 coverage audit's recommended
# remediation order. See docs/ops/runbook-coverage-audit-2026-04-29.md.
LIFTED_RUNBOOKS: tuple[str, ...] = (
    "backtest-weekly-runbook.md",
    "telemetry-collector-runbook.md",
    "content-publisher-runbook.md",
    "tradingview-cdp-runbook.md",
    "control-plane-runbook.md",
    "foundry-sync-runbook.md",
    "security-pipeline-runbook.md",
    "heartbeat-runbook.md",
    "logrotate-runbook.md",
    "market-intel-runbook.md",
    "morning-brief-runbook.md",
    "morning-digest-runbook.md",
    "self-optimization-runbook.md",
    "service-supervisor-runbook.md",
    "openbb-api-runbook.md",
    "gcp-pipeline-runbook.md",
)

# Trading-critical-path runbooks — explicitly excluded. Document the skip so a
# future maintainer cannot silently widen the smoke set into restricted paths.
SKIPPED_TRADING_CRITICAL: tuple[str, ...] = (
    "webhook-runbook.md",
    "trading-shadow-runbook.md",
    "tranche5-live-soak-runbook.md",
    "hyperliquid-feed-runbook.md",
    "hyperliquid-live-trading-runbook.md",
    "robinhood-real-funds-readiness.md",
)


_FENCE_PATTERN = re.compile(
    r"^```(?P<lang>[A-Za-z0-9_+\-]*)\s*\n(?P<body>.*?)\n```",
    re.DOTALL | re.MULTILINE,
)


def _extract_fenced_blocks(markdown: str) -> list[tuple[str, str]]:
    """Return ``(lang, body)`` for each fenced code block, in document order."""

    return [(m.group("lang") or "", m.group("body")) for m in _FENCE_PATTERN.finditer(markdown)]


def _is_bash_block(lang: str, body: str) -> bool:
    """Heuristic: count a block as a bash command block when it is

    - tagged ``bash`` or ``sh`` or ``shell`` or ``console``, OR
    - untagged but the first non-blank line looks like a shell command.

    Skips obvious non-bash payloads (json, yaml, python, text, jsonc, plist xml).
    """

    lang_norm = lang.lower().strip()
    bash_langs = {"bash", "sh", "shell", "zsh", "console"}
    if lang_norm in bash_langs:
        return True
    non_bash_langs = {
        "json",
        "jsonc",
        "yaml",
        "yml",
        "python",
        "py",
        "text",
        "txt",
        "xml",
        "html",
        "diff",
        "patch",
        "ini",
        "toml",
        "sql",
        "ts",
        "typescript",
        "js",
        "javascript",
        "rust",
        "go",
        "csv",
        "log",
        "pine",
    }
    if lang_norm in non_bash_langs:
        return False
    if lang_norm:
        # Unknown tagged language — be conservative and skip.
        return False
    # Untagged: only treat as bash if the first non-blank line starts with a
    # plausible command character (alpha, /, ., $).
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped[0].isalpha() or stripped[0] in {"/", ".", "$"}:
            return True
        return False
    return False


def _first_n_bash_blocks(markdown: str, n: int = 3) -> list[str]:
    """Return up to ``n`` bash block bodies in document order."""

    blocks = []
    for lang, body in _extract_fenced_blocks(markdown):
        if _is_bash_block(lang, body):
            blocks.append(body)
            if len(blocks) >= n:
                break
    return blocks


def _bash_syntax_check(script: str) -> tuple[bool, str]:
    """Run ``bash -n`` against ``script`` and return ``(ok, stderr)``."""

    bash_path = shutil.which("bash")
    if bash_path is None:  # pragma: no cover — every dev box has bash
        pytest.skip("bash not on PATH")
    proc = subprocess.run(  # noqa: S603 — bash on PATH is trusted
        [bash_path, "-n"],
        input=script,
        text=True,
        capture_output=True,
        timeout=10,
    )
    return proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("runbook_name", LIFTED_RUNBOOKS)
def test_runbook_exists(runbook_name: str) -> None:
    """Every lifted runbook is present at the expected path."""

    path = OPS_DIR / runbook_name
    assert path.is_file(), f"missing runbook: {path.relative_to(REPO_ROOT)}"


@pytest.mark.parametrize("runbook_name", LIFTED_RUNBOOKS)
def test_runbook_has_three_bash_blocks(runbook_name: str) -> None:
    """Each lifted runbook ships ≥ 3 bash command blocks an operator can paste."""

    path = OPS_DIR / runbook_name
    markdown = path.read_text(encoding="utf-8")
    blocks = _first_n_bash_blocks(markdown, n=3)
    assert len(blocks) >= 3, (
        f"{runbook_name}: expected ≥ 3 bash blocks, found {len(blocks)}. "
        "Tranche 7-C contract: every audited runbook surfaces a 3-step triage "
        "quickstart so an operator does not have to read the whole doc."
    )


@pytest.mark.parametrize("runbook_name", LIFTED_RUNBOOKS)
def test_runbook_first_three_commands_parse(runbook_name: str) -> None:
    """First three bash blocks pass `bash -n` syntax check.

    This is a syntax check, not execution. Catches dangling continuations,
    unmatched quotes, and accidental non-bash payloads.
    """

    path = OPS_DIR / runbook_name
    markdown = path.read_text(encoding="utf-8")
    blocks = _first_n_bash_blocks(markdown, n=3)
    failures: list[str] = []
    for idx, body in enumerate(blocks, start=1):
        ok, stderr = _bash_syntax_check(body)
        if not ok:
            failures.append(f"  block {idx}: {stderr.strip()}\n    body:\n{body}")
    assert not failures, f"{runbook_name}: first-3-commands failed `bash -n`:\n" + "\n".join(
        failures
    )


def test_trading_critical_runbooks_not_in_smoke_set() -> None:
    """Defense in depth: the smoke set never silently widens into trading paths.

    AGENTS.md gates trading-critical-path runbooks under CODEOWNERS review. If a
    future PR adds one of `SKIPPED_TRADING_CRITICAL` to `LIFTED_RUNBOOKS`, this
    test fails and forces an explicit review.
    """

    overlap = set(LIFTED_RUNBOOKS) & set(SKIPPED_TRADING_CRITICAL)
    assert overlap == set(), (
        "trading-critical-path runbooks must not be in the Tranche 7-C smoke set: "
        f"{sorted(overlap)}"
    )


def test_audit_doc_referenced() -> None:
    """The 2026-04-29 audit doc still exists — the smoke set's source of truth."""

    audit_path = OPS_DIR / "runbook-coverage-audit-2026-04-29.md"
    assert audit_path.is_file(), (
        "runbook-coverage-audit-2026-04-29.md is the source of truth for "
        "LIFTED_RUNBOOKS; if it moves, update tests/runbooks/test_runbook_smoke.py."
    )
