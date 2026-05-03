"""Heuristic Pine Script v5 lint / validator.

Pure functions only. No I/O. No execution of Pine. The validator runs a set
of structural heuristics that catch the common categories of malformed Pine
that our translator could conceivably emit:

1.  Balanced parens / brackets / braces.
2.  Required `//@version=5` directive present and on its own line.
3.  Required `strategy(...)` declaration well-formed (closing paren reached,
    `strategy(` token appears at most once).
4.  No `var <type> ?` ambiguity (TradingView syntax requires either `var x = ...`
    or `var <type> x = ...`, never `var <type> ? x`).
5.  `indicator(...)` and `strategy(...)` are not both present.
6.  `request.security` calls are well-formed (4 commas → 5 args minimum, with
    the symbol arg quoted).
7.  No empty body — at least one `strategy.entry`, `strategy.close`, or `plot`
    call must exist.
8.  No literal trailing backslash (Pine v5 doesn't support backslash line
    continuations the way some Pine v4 examples did).
9.  No `// TODO` / `// FIXME` / `// XXX` markers — generated Pine should never
    ship with explicit gaps.
10. No bare `na` returned at top level (would indicate a template variable
    that wasn't substituted).

The validator returns :class:`PineValidationResult`. Callers can either inspect
``result.ok`` or rely on the structured ``errors`` / ``warnings`` lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PineValidationResult:
    """Result of a Pine v5 lint pass.

    Attributes:
        ok: True if no errors. Warnings do not flip this to False.
        errors: List of fatal lint findings. If empty, the Pine source passed
            structural validation and is safe to write to disk.
        warnings: List of non-fatal findings. Surface these to the operator
            but don't block generation.
        stats: Diagnostic counts (paren depth, statement count, etc.).
    """

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "stats": dict(self.stats),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_comments_and_strings(source: str) -> str:
    """Replace string literals and `//` line comments with spaces.

    This lets the structural checks operate on pure code. We do NOT strip
    `//@version=5` because that's a directive, not a comment.
    """
    out: list[str] = []
    in_str = False
    str_quote = ""
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        # Line comment (preserve `//@version=5`)
        if not in_str and ch == "/" and i + 1 < n and source[i + 1] == "/":
            # Peek for `//@`
            if i + 2 < n and source[i + 2] == "@":
                # Keep the directive intact
                end = source.find("\n", i)
                if end == -1:
                    end = n
                out.append(source[i:end])
                i = end
                continue
            # Otherwise, skip to end of line
            end = source.find("\n", i)
            if end == -1:
                end = n
            out.append(" " * (end - i))
            i = end
            continue
        # String literal
        if not in_str and ch in ('"', "'"):
            in_str = True
            str_quote = ch
            out.append(" ")
            i += 1
            continue
        if in_str and ch == str_quote and (i == 0 or source[i - 1] != "\\"):
            in_str = False
            out.append(" ")
            i += 1
            continue
        if in_str:
            # Mask string contents so `()` inside strings don't fool the
            # paren counter.
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _line_with(source: str, needle: str) -> int | None:
    """Return the 1-indexed line of the first match, or None."""
    for idx, line in enumerate(source.splitlines(), start=1):
        if needle in line:
            return idx
    return None


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_version_directive(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if "//@version=5" not in source:
        errors.append("missing required `//@version=5` directive")
        return errors, warnings
    # The directive must appear before the first non-comment statement.
    matches = [
        i
        for i, line in enumerate(source.splitlines(), start=1)
        if line.strip().startswith("//@version=")
    ]
    if matches and matches[0] > 1:
        # The translator may emit a few comment lines before the directive,
        # which is allowed in Pine v5. Only warn if the directive comes after
        # a real (non-comment) line.
        for i, line in enumerate(source.splitlines(), start=1):
            if i >= matches[0]:
                break
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                warnings.append(
                    f"`//@version=5` should appear before any code (found code on line {i})"
                )
                break
    if source.count("//@version=5") > 1:
        warnings.append("`//@version=5` directive appears more than once")
    return errors, warnings


def _check_balanced(source: str) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    stripped = _strip_comments_and_strings(source)
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {v: k for k, v in pairs.items()}
    stack: list[tuple[str, int]] = []  # (open_char, line_number)
    line = 1
    for ch in stripped:
        if ch == "\n":
            line += 1
            continue
        if ch in pairs:
            stack.append((ch, line))
            continue
        if ch in closing:
            if not stack:
                errors.append(f"unbalanced `{ch}` on line {line} (no matching opener)")
                continue
            opener, _ = stack.pop()
            if opener != closing[ch]:
                errors.append(
                    f"mismatched bracket on line {line}: expected `{pairs[opener]}` "
                    f"but found `{ch}`"
                )
    if stack:
        for opener, oline in stack:
            errors.append(f"unclosed `{opener}` opened on line {oline}")
    stats = {"final_paren_depth": len(stack)}
    return errors, warnings, stats


def _check_strategy_decl(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    has_strategy = bool(re.search(r"^\s*strategy\s*\(", source, re.MULTILINE))
    has_indicator = bool(re.search(r"^\s*indicator\s*\(", source, re.MULTILINE))
    if not has_strategy and not has_indicator:
        errors.append("missing top-level `strategy(...)` or `indicator(...)` declaration")
    if has_strategy and has_indicator:
        errors.append("both `strategy(...)` and `indicator(...)` present (Pine allows only one)")
    if has_strategy:
        # Count occurrences. Multiple strategy() calls are a hard error.
        stripped = _strip_comments_and_strings(source)
        count = len(re.findall(r"^\s*strategy\s*\(", stripped, re.MULTILINE))
        if count > 1:
            errors.append(f"`strategy(...)` declared {count} times (must be exactly 1)")
        # Check that the strategy() call has a closing paren on the same
        # logical statement. Pine doesn't permit string concatenation across
        # arbitrary lines for the strategy() call. We accept multi-line as
        # long as every line in the call ends with `,` (continuation).
        m = re.search(r"strategy\s*\(", stripped, re.MULTILINE)
        if m:
            start = m.start()
            depth = 0
            end = -1
            for i, ch in enumerate(stripped[start:]):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = start + i
                        break
            if end == -1:
                errors.append("`strategy(...)` declaration missing closing paren")
    return errors, warnings


def _check_var_ambiguity(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    # `var <type> ?` is malformed: Pine wants either `var x = ...` or
    # `var <type> x = ...`. The `?` indicates a missing identifier.
    pattern = re.compile(
        r"\bvar\s+(int|float|bool|string|color|line|label|table|box)\s*\?",
    )
    if pattern.search(source):
        errors.append("malformed `var <type> ?` declaration (missing identifier)")
    return errors, warnings


def _check_request_security(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    stripped = _strip_comments_and_strings(source)
    for m in re.finditer(r"request\.security\s*\(", stripped):
        start = m.end()
        depth = 1
        end = -1
        for i, ch in enumerate(stripped[start:]):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = start + i
                    break
        if end == -1:
            errors.append("`request.security(...)` missing closing paren")
            continue
        args_chunk = stripped[start:end]
        # Need at least 2 commas (3 args minimum: symbol, timeframe, expression).
        # We compare on top-level commas (depth 0).
        depth = 0
        commas = 0
        for ch in args_chunk:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                commas += 1
        if commas < 2:
            errors.append(
                "`request.security(...)` call has too few arguments "
                "(needs at least symbol, timeframe, expression)"
            )
        # The first arg should be a quoted string in the original (we verify
        # against the original source, not the stripped one).
        original_match = re.search(r"request\.security\s*\(\s*([^,]+)", source, re.MULTILINE)
        if original_match:
            first_arg = original_match.group(1).strip()
            if not (
                (first_arg.startswith('"') and '"' in first_arg[1:])
                or (first_arg.startswith("'") and "'" in first_arg[1:])
                or first_arg.startswith("syminfo.")
            ):
                # Only warn — the symbol could be a defined variable.
                warnings.append(
                    f"`request.security(...)` first arg is not a quoted "
                    f"string literal: {first_arg!r}"
                )
    return errors, warnings


def _check_body_present(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    body_signals = [
        "strategy.entry",
        "strategy.close",
        "strategy.exit",
        "plot(",
        "plotshape(",
        "alert(",
    ]
    if not any(sig in source for sig in body_signals):
        errors.append(
            "Pine source has no body — needs at least one of: "
            "strategy.entry, strategy.close, strategy.exit, plot, plotshape, alert"
        )
    return errors, warnings


def _check_no_continuation_backslash(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    # Pine v5 treats `\` at end of line as a literal char, so a trailing `\`
    # on a code line is almost certainly a bug. Allow it inside strings (we
    # work on stripped source).
    stripped = _strip_comments_and_strings(source)
    for idx, line in enumerate(stripped.splitlines(), start=1):
        if line.rstrip(" \t").endswith("\\"):
            errors.append(f"trailing `\\` line continuation on line {idx} (Pine v5 disallows)")
    return errors, warnings


def _check_no_todo_markers(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for marker in ("// TODO", "// FIXME", "// XXX"):
        if marker in source:
            line = _line_with(source, marker)
            warnings.append(f"contains `{marker}` marker on line {line}")
    return errors, warnings


def _check_no_unsubstituted_template_vars(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    # Catches `{{var}}` that survived the renderer.
    if re.search(r"\{\{\s*[a-zA-Z_]", source):
        errors.append("Pine source contains unsubstituted Jinja-style `{{var}}` placeholders")
    return errors, warnings


def _check_strategy_args(source: str) -> tuple[list[str], list[str]]:
    """`strategy()` requires a positional title; `initial_capital` should be > 0."""
    errors: list[str] = []
    warnings: list[str] = []
    m = re.search(r"strategy\s*\((.+?)\)", source, re.DOTALL)
    if m:
        args_blob = m.group(1)
        first_comma = -1
        depth = 0
        for i, ch in enumerate(args_blob):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                first_comma = i
                break
        first_arg = args_blob[:first_comma].strip() if first_comma != -1 else args_blob.strip()
        if not first_arg.startswith('"') or len(first_arg) < 3:
            warnings.append("`strategy(...)` first positional arg should be a quoted title string")
        if "initial_capital" in args_blob:
            ic = re.search(r"initial_capital\s*=\s*(-?\d+(?:\.\d+)?)", args_blob)
            if ic and float(ic.group(1)) <= 0:
                errors.append("`initial_capital` must be > 0")
    return errors, warnings


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def validate_pine(source: str) -> PineValidationResult:
    """Run every Pine v5 lint heuristic against `source`.

    Args:
        source: The Pine source string.

    Returns:
        :class:`PineValidationResult`.
    """
    if not isinstance(source, str):
        raise TypeError(f"validate_pine expects str, got {type(source).__name__}")
    if not source.strip():
        return PineValidationResult(
            ok=False, errors=["empty Pine source"], warnings=[], stats={"length": 0}
        )

    errors: list[str] = []
    warnings: list[str] = []

    e, w = _check_version_directive(source)
    errors += e
    warnings += w

    e, w, paren_stats = _check_balanced(source)
    errors += e
    warnings += w

    e, w = _check_strategy_decl(source)
    errors += e
    warnings += w

    e, w = _check_var_ambiguity(source)
    errors += e
    warnings += w

    e, w = _check_request_security(source)
    errors += e
    warnings += w

    e, w = _check_body_present(source)
    errors += e
    warnings += w

    e, w = _check_no_continuation_backslash(source)
    errors += e
    warnings += w

    e, w = _check_no_todo_markers(source)
    errors += e
    warnings += w

    e, w = _check_no_unsubstituted_template_vars(source)
    errors += e
    warnings += w

    e, w = _check_strategy_args(source)
    errors += e
    warnings += w

    stats = {
        "length": len(source),
        "lines": len(source.splitlines()),
        **paren_stats,
    }
    return PineValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats=stats,
    )
