"""Task discipline preamble — Karpathy principles wrapper for agent task dispatch.

Wraps task prompts with Karpathy's 4 coding discipline principles to reduce
common LLM coding mistakes (over-engineering, silent assumptions, scope creep).

Usage:
    from sapphire_core.task_discipline import wrap_task_prompt, TaskDiscipline

    # Wrap before dispatching to an agent
    prompt = wrap_task_prompt("Add rate limiting to the signal logger API")

    # Or with explicit discipline level
    prompt = wrap_task_prompt("Fix the bug in paper_trader.py", level="surgical")
"""

from __future__ import annotations

from enum import StrEnum


class TaskDiscipline(StrEnum):
    """Discipline mode — controls which principles are emphasized."""

    FULL = "full"  # All 4 principles (non-trivial features, architecture)
    SURGICAL = "surgical"  # Principles 3+4 (bug fixes, targeted edits)
    MINIMAL = "minimal"  # Just principle 4 goals (trivial tasks)


_PREAMBLE_FULL = """Before implementing, apply these 4 coding discipline principles:

1. THINK FIRST — State assumptions explicitly. If the request has multiple interpretations, surface them before choosing. If unclear, ask.
2. SIMPLICITY FIRST — Write the minimum code that solves the stated problem. No speculative features, no unasked-for abstractions.
3. SURGICAL CHANGES — Touch only what the request requires. Do not refactor adjacent code, improve unrelated formatting, or delete pre-existing dead code.
4. GOAL-DRIVEN — Define a verifiable success criterion before writing code. For multi-step tasks, state a brief plan with a verification step for each.

Apply these principles to the following task:
"""

_PREAMBLE_SURGICAL = """Apply surgical precision to the following task:
- Touch ONLY the code the request requires — no adjacent refactoring
- Match existing style exactly
- Define a verifiable success criterion (e.g., "test X passes" or "behavior Y is confirmed")
- Remove imports/variables YOUR changes made unused; leave pre-existing dead code alone

Task:
"""

_PREAMBLE_MINIMAL = """State what "done" looks like (verifiable) before implementing.

Task:
"""

_PREAMBLES = {
    TaskDiscipline.FULL: _PREAMBLE_FULL,
    TaskDiscipline.SURGICAL: _PREAMBLE_SURGICAL,
    TaskDiscipline.MINIMAL: _PREAMBLE_MINIMAL,
}


def wrap_task_prompt(
    task: str,
    level: TaskDiscipline | str = TaskDiscipline.FULL,
    *,
    context: str | None = None,
) -> str:
    """Wrap a task prompt with Karpathy discipline preamble.

    Args:
        task: The raw task description to wrap.
        level: Discipline level — 'full', 'surgical', or 'minimal'.
        context: Optional context block (e.g., file path, current behavior).

    Returns:
        Wrapped prompt string ready for dispatch.

    Examples:
        >>> wrap_task_prompt("Add rate limiting to /api/signals")
        'Before implementing, apply these 4 coding discipline principles:...'

        >>> wrap_task_prompt("Fix the off-by-one in paper_trader.py line 142", level="surgical")
        'Apply surgical precision...'
    """
    if isinstance(level, str):
        level = TaskDiscipline(level)

    preamble = _PREAMBLES[level]
    parts = [preamble, task]

    if context:
        parts.append(f"\nContext:\n{context}")

    return "\n".join(parts)


def infer_discipline(task: str) -> TaskDiscipline:
    """Heuristically infer the appropriate discipline level from the task description.

    Args:
        task: Task description string.

    Returns:
        Recommended TaskDiscipline level.
    """
    task_lower = task.lower()

    # Surgical indicators
    surgical_keywords = [
        "fix",
        "bug",
        "off-by-one",
        "typo",
        "rename",
        "move",
        "delete",
        "remove",
        "update",
        "patch",
        "line ",
        "crash",
        "error",
    ]
    # Full discipline indicators
    full_keywords = [
        "add",
        "create",
        "build",
        "implement",
        "feature",
        "new",
        "refactor",
        "redesign",
        "architecture",
        "system",
    ]

    if any(k in task_lower for k in surgical_keywords):
        return TaskDiscipline.SURGICAL
    if any(k in task_lower for k in full_keywords):
        return TaskDiscipline.FULL
    return TaskDiscipline.MINIMAL


def auto_wrap(task: str, context: str | None = None) -> str:
    """Wrap a task prompt with automatically inferred discipline level.

    Convenience function — infers level from task keywords.

    Args:
        task: Task description.
        context: Optional context block.

    Returns:
        Wrapped prompt.
    """
    level = infer_discipline(task)
    return wrap_task_prompt(task, level=level, context=context)
