"""Token budget governance with real counts.

Tracks actual token usage per tier per day from API responses.
Enforces daily budgets. Auto-throttles when budgets approach limits.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

USAGE_PATH = Path.home() / ".sapphire" / "token_usage.json"

DAILY_BUDGETS = {
    "t0_nemotron": float("inf"),
    "t1_kimi": 500_000,
    "t2_claw": 300_000,
    "t3_claude": 200_000,
}

TIER_LABELS = {
    "t0_nemotron": "T0 Nemotron GPU (free)",
    "t1_kimi": "T1 Kimi CLI",
    "t2_claw": "T2 Claw-Code",
    "t3_claude": "T3 Claude",
}

TIER_MAP = {"t0": "t0_nemotron", "t1": "t1_kimi", "t2": "t2_claw", "t3": "t3_claude"}


def _load() -> dict:
    if USAGE_PATH.exists():
        try:
            return json.loads(USAGE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save(data: dict) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USAGE_PATH.write_text(json.dumps(data, indent=2))


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def record(tier: str, prompt_tokens: int, eval_tokens: int, task: str = "") -> dict:
    """Record real token usage from an API response.

    Args:
        tier: Short tier name (t0, t1, t3)
        prompt_tokens: Actual prompt/input tokens from API
        eval_tokens: Actual output/eval tokens from API
        task: Description for audit trail
    """
    budget_key = TIER_MAP.get(tier, tier)
    data = _load()
    today = _today()

    if today not in data:
        data[today] = {}
    if budget_key not in data[today]:
        data[today][budget_key] = {
            "prompt_tokens": 0, "eval_tokens": 0, "total_tokens": 0,
            "calls": 0, "tasks": [],
        }

    entry = data[today][budget_key]
    entry["prompt_tokens"] += prompt_tokens
    entry["eval_tokens"] += eval_tokens
    entry["total_tokens"] += prompt_tokens + eval_tokens
    entry["calls"] += 1
    if task:
        entry["tasks"].append(task[:100])
        entry["tasks"] = entry["tasks"][-20:]

    _save(data)
    return entry


def is_available(tier: str) -> bool:
    """Check if a tier has remaining daily budget."""
    budget_key = TIER_MAP.get(tier, tier)
    budget = DAILY_BUDGETS.get(budget_key, 0)
    if budget == float("inf"):
        return True

    data = _load()
    today = _today()
    used = data.get(today, {}).get(budget_key, {}).get("total_tokens", 0)
    return used < budget


def remaining(tier: str) -> int | float:
    """Get remaining tokens for a tier today."""
    budget_key = TIER_MAP.get(tier, tier)
    budget = DAILY_BUDGETS.get(budget_key, 0)
    if budget == float("inf"):
        return float("inf")

    data = _load()
    today = _today()
    used = data.get(today, {}).get(budget_key, {}).get("total_tokens", 0)
    return max(0, budget - used)


def status() -> dict:
    """Get budget status for all tiers."""
    data = _load()
    today = _today()
    today_data = data.get(today, {})

    result = {}
    for tier_short, budget_key in TIER_MAP.items():
        budget = DAILY_BUDGETS[budget_key]
        entry = today_data.get(budget_key, {})
        used = entry.get("total_tokens", 0)
        calls = entry.get("calls", 0)
        prompt = entry.get("prompt_tokens", 0)
        eval_tok = entry.get("eval_tokens", 0)

        result[tier_short] = {
            "label": TIER_LABELS[budget_key],
            "used": used,
            "prompt_tokens": prompt,
            "eval_tokens": eval_tok,
            "budget": budget if budget != float("inf") else "unlimited",
            "remaining": (budget - used) if budget != float("inf") else "unlimited",
            "calls": calls,
            "pct_used": round(used / budget * 100, 1) if budget != float("inf") else 0,
            "exhausted": used >= budget if budget != float("inf") else False,
        }

    return result


def format_report() -> str:
    """Human-readable budget report."""
    s = status()
    lines = [f"📊 *Token Budget — {_today()}*\n"]

    for _tier, info in s.items():
        if info["budget"] == "unlimited":
            lines.append(
                f"🟢 *{info['label']}*\n"
                f"   {info['used']:,} tokens ({info['prompt_tokens']:,}↓ {info['eval_tokens']:,}↑) "
                f"| {info['calls']} calls | ∞"
            )
        else:
            pct = info["pct_used"]
            icon = "🟢" if pct < 50 else "🟡" if pct < 80 else "🔴"
            filled = int(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)
            lines.append(
                f"{icon} *{info['label']}*\n"
                f"   {info['used']:,}/{info['budget']:,} ({pct}%) "
                f"| {info['calls']} calls | {bar}"
            )

    return "\n".join(lines)
