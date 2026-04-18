"""Task classification and tier routing.

Uses Nemotron (free, 196 t/s) to classify tasks, then routes to cheapest tier.
Keyword fallback if Nemotron is unavailable.

T1 (Kimi) uses kimi_client HTTP API — no CLI subprocess, no hourly auth expiry.
Priority: MOONSHOT_API_KEY → OPENROUTER_API_KEY → unavailable
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# kimi_client — permanent API key HTTP client (no auth expiry)
sys.path.insert(0, str(Path.home() / "Code" / "kimi-tools"))
from kimi_client import complete as kimi_complete  # noqa: E402

# Import nemotron client — handle both plugin context and direct execution
try:
    from .nemotron import MODELS, generate
except ImportError:
    from nemotron import MODELS, generate

CLAW_BIN = Path.home() / ".local" / "bin" / "claw"

CLASSIFY_PROMPT = """Classify this software development task into ONE tier.

TIERS:
- t0: Read-only analysis, explanation, docs, monitoring, summaries (no code changes needed)
- t1: Simple code fix (1-2 files), lint, imports, small bugs, deploy commands, ops tasks
- t3: Complex refactor (3+ files), architecture, security audit, trading logic, planning

TASK: {task}

Respond with ONLY valid JSON:
{{"tier": "t0"|"t1"|"t3", "reason": "brief reason", "complexity": 1-5}}"""


@dataclass
class Classification:
    """Task classification result."""

    tier: str  # t0, t1, t3
    reason: str
    complexity: int  # 1-5
    method: str  # "nemotron" or "keyword"


@dataclass
class ExecutionResult:
    """Result from executing a task on a tier."""

    tier: str
    agent: str
    output: str
    prompt_tokens: int
    eval_tokens: int
    total_tokens: int
    success: bool
    error: str = ""


def classify(task: str) -> Classification:
    """Classify a task into a tier using Nemotron (free)."""
    result = generate(
        CLASSIFY_PROMPT.format(task=task),
        model=MODELS["classify"],
        timeout=15,
        max_tokens=100,
    )

    if result.success and result.response:
        try:
            start = result.response.find("{")
            end = result.response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(result.response[start:end])
                return Classification(
                    tier=data.get("tier", "t1"),
                    reason=data.get("reason", ""),
                    complexity=data.get("complexity", 2),
                    method="nemotron",
                )
        except (json.JSONDecodeError, KeyError):
            pass

    # Keyword fallback — no LLM needed
    return _keyword_classify(task)


def _keyword_classify(task: str) -> Classification:
    """Deterministic keyword-based classification. No LLM call."""
    t = task.lower()

    # T3 keywords — complex, high-stakes
    t3_words = ["refactor", "architect", "security", "trading", "redesign", "plan",
                 "migrate", "restructure", "rewrite", "multi-file", "breaking change"]
    if any(w in t for w in t3_words):
        return Classification("t3", "keyword: complex/high-stakes", 4, "keyword")

    # T0 keywords — read-only
    t0_words = ["explain", "analyze", "summarize", "review", "status", "list",
                 "describe", "what is", "how does", "show me", "report", "scan"]
    if any(w in t for w in t0_words):
        return Classification("t0", "keyword: read-only/analysis", 1, "keyword")

    # Default → T1
    return Classification("t1", "keyword: default simple fix", 2, "keyword")


def execute_t0(task: str, repo: str | None = None) -> ExecutionResult:
    """Execute via Nemotron GPU (free, deep analysis)."""
    context = ""
    if repo:
        repo_path = Path.home() / "Code" / repo
        if repo_path.exists():
            files = subprocess.run(
                ["find", ".", "-maxdepth", "2", "-name", "*.py", "-o", "-name", "*.ts"],
                capture_output=True, text=True, cwd=str(repo_path), timeout=5,
            ).stdout[:2000]
            context = f"\n\nRepo: {repo}\nKey files:\n{files}"

    result = generate(task + context, model=MODELS["analyze"], timeout=120, max_tokens=1024)

    return ExecutionResult(
        tier="t0",
        agent=f"nemotron/{result.model}@{result.endpoint}",
        output=result.response,
        prompt_tokens=result.prompt_tokens,
        eval_tokens=result.eval_tokens,
        total_tokens=result.total_tokens,
        success=result.success,
        error=result.error,
    )


def execute_t1(task: str, repo: str | None = None) -> ExecutionResult:
    """Execute via Kimi Cloud (permanent API key, no auth expiry)."""
    system = "You are a senior software engineer. Be concise, precise, and complete."
    if repo:
        system += f" Working in the {repo} repository."

    result = kimi_complete(task, model="balanced", system=system, max_tokens=4096)
    return ExecutionResult(
        tier="t1",
        agent=f"kimi/{result.provider}/{result.model}",
        output=result.content if result.success else "",
        prompt_tokens=result.prompt_tokens,
        eval_tokens=result.eval_tokens,
        total_tokens=result.total_tokens,
        success=result.success,
        error=result.error,
    )


def execute_t3(task: str, repo: str | None = None) -> ExecutionResult:
    """Execute via Claw-Code (Claude API)."""
    if not CLAW_BIN.exists():
        return ExecutionResult("t3", "claw", "", 0, 0, 0, False, "Claw binary not found")

    cwd = str(Path.home() / "Code" / repo) if repo else str(Path.home() / "Code" / "Sapphire")
    env = {**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{os.environ.get('PATH', '')}"}

    try:
        proc = subprocess.run(
            [str(CLAW_BIN), "prompt", task],
            capture_output=True, text=True, cwd=cwd, timeout=300, env=env,
        )
        output = proc.stdout.strip()
        # Rough estimate for Claude — claw doesn't expose token counts in stdout yet
        est_tokens = (len(task) + len(output)) // 4

        return ExecutionResult(
            tier="t3",
            agent="claw/claude",
            output=output,
            prompt_tokens=est_tokens // 3,
            eval_tokens=est_tokens * 2 // 3,
            total_tokens=est_tokens,
            success=proc.returncode == 0,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult("t3", "claw", "", 0, 0, 0, False, "Timed out")


# Tier execution chain — cheapest first with fallbacks
EXECUTORS = {
    "t0": execute_t0,
    "t1": execute_t1,
    "t3": execute_t3,
}

FALLBACK_CHAINS = {
    "t0": ["t0", "t1", "t3"],
    "t1": ["t1", "t0", "t3"],
    "t3": ["t3", "t1", "t0"],
}
