#!/usr/bin/env python3
"""sapphire_dispatch — route a task to the optimal inference tier.

Claw-code plugin tool. Receives task via stdin JSON from claw-code runtime.
Classifies via Nemotron (free), checks budget, executes on cheapest tier.

Input schema:
    {"task": "Fix the import error in main.py", "tier": "t1", "repo": "Sapphire"}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from router import classify, EXECUTORS, FALLBACK_CHAINS, Classification
from token_governor import is_available, record, format_report
from runtime_policy import is_tier_allowed, is_repo_allowed, max_complexity


def dispatch(task: str, tier: str | None = None, repo: str | None = None) -> dict:
    """Route and execute a task."""
    # Step 1: Classify
    if tier:
        classification = Classification(tier, "user-specified", 0, "manual")
    else:
        classification = classify(task)

    target = classification.tier

    # Step 2: Policy check
    if repo and not is_repo_allowed(repo):
        return {"error": f"Repo '{repo}' is blocked by runtime policy", "classification": classification.__dict__}

    if classification.complexity > max_complexity(target):
        # Escalate to higher tier
        for t in ["t1", "t3"]:
            if classification.complexity <= max_complexity(t) and is_tier_allowed(t):
                target = t
                break

    # Step 3: Execute with fallback chain
    chain = FALLBACK_CHAINS.get(target, ["t1"])

    for attempt_tier in chain:
        if not is_tier_allowed(attempt_tier):
            continue
        if not is_available(attempt_tier) and attempt_tier != "t0":
            continue

        executor = EXECUTORS.get(attempt_tier)
        if not executor:
            continue

        result = executor(task, repo)

        # Record real token usage
        record(
            attempt_tier,
            prompt_tokens=result.prompt_tokens,
            eval_tokens=result.eval_tokens,
            task=task[:80],
        )

        if result.success:
            return {
                "tier": result.tier,
                "agent": result.agent,
                "output": result.output,
                "tokens": {
                    "prompt": result.prompt_tokens,
                    "eval": result.eval_tokens,
                    "total": result.total_tokens,
                },
                "classification": classification.__dict__,
                "success": True,
            }

    return {
        "error": "All tiers failed or exhausted",
        "classification": classification.__dict__,
        "success": False,
    }


def main():
    """Plugin tool entry point — reads from stdin."""
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        # CLI mode — check argv
        if len(sys.argv) > 1:
            input_data = {"task": " ".join(sys.argv[1:])}
        else:
            print(json.dumps({"error": "No input provided. Pass JSON via stdin or task as argv."}))
            sys.exit(1)

    task = input_data.get("task", "")
    tier = input_data.get("tier")
    repo = input_data.get("repo")

    if not task:
        print(json.dumps({"error": "Missing 'task' field"}))
        sys.exit(1)

    result = dispatch(task, tier, repo)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
