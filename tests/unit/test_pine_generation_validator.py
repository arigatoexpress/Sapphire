"""Tests for lib.pine_generation.validator.

Coverage targets (per Tranche 5 Lane 8 spec):
- ≥ 14 cases.
- Catches malformed Pine.
- Accepts well-formed Pine.
"""

from __future__ import annotations

import pytest

from lib.pine_generation import PineSpec, generate_pine, validate_pine
from lib.pine_generation.validator import PineValidationResult

# ---------------------------------------------------------------------------
# 1) Acceptance: well-formed Pine
# ---------------------------------------------------------------------------


def _good_pine() -> str:
    return """\
//@version=5
strategy("Test", overlay=true, initial_capital=1000)
rsi = ta.rsi(close, 14)
if rsi < 30
    strategy.entry("Long", strategy.long)
plot(rsi, "RSI")
"""


def test_accepts_minimal_well_formed_pine() -> None:
    res = validate_pine(_good_pine())
    assert res.ok, f"errors: {res.errors}"
    assert not res.errors


def test_accepts_translator_output_for_every_strategy() -> None:
    from lib.pine_generation.translator import SUPPORTED_STRATEGIES

    for s in SUPPORTED_STRATEGIES:
        spec = PineSpec(strategy=s, symbol="BTC-USD")
        src = generate_pine(spec)
        res = validate_pine(src)
        assert res.ok, f"{s}: {res.errors}"


def test_validation_result_to_dict_round_trip() -> None:
    res = validate_pine(_good_pine())
    d = res.to_dict()
    assert d["ok"] is True
    assert isinstance(d["errors"], list)
    assert isinstance(d["warnings"], list)
    assert isinstance(d["stats"], dict)


# ---------------------------------------------------------------------------
# 2) Rejection: structural errors
# ---------------------------------------------------------------------------


def test_rejects_empty_source() -> None:
    res = validate_pine("")
    assert not res.ok
    assert any("empty" in e for e in res.errors)


def test_rejects_missing_version_directive() -> None:
    src = """\
strategy("Test", overlay=true)
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("//@version=5" in e for e in res.errors)


def test_rejects_unbalanced_parens() -> None:
    src = """\
//@version=5
strategy("Test"
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok


def test_rejects_unbalanced_closing_paren() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
plot(close, "Close"))
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("unbalanced" in e or "no matching" in e for e in res.errors)


def test_rejects_mismatched_brackets() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
arr = [1, 2, 3)
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok


def test_rejects_var_type_ambiguity() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
var int ? mystate = 0
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("var <type> ?" in e for e in res.errors)


def test_rejects_double_strategy_decl() -> None:
    src = """\
//@version=5
strategy("Test1", overlay=true)
strategy("Test2", overlay=false)
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("declared" in e and "times" in e for e in res.errors)


def test_rejects_indicator_and_strategy_both() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
indicator("Test2", overlay=false)
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("only one" in e for e in res.errors)


def test_rejects_no_strategy_or_indicator() -> None:
    src = """\
//@version=5
x = 5
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("strategy" in e and "indicator" in e for e in res.errors)


def test_rejects_no_body() -> None:
    """A pine source with strategy decl but no entry/exit/plot is invalid."""
    src = """\
//@version=5
strategy("Test", overlay=true)
x = ta.rsi(close, 14)
y = x + 1
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("body" in e for e in res.errors)


def test_rejects_unsubstituted_template() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
rsi_len = input.int({{rsi_period}}, "RSI")
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("Jinja" in e or "template" in e for e in res.errors)


def test_rejects_negative_initial_capital() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true, initial_capital=-100)
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("initial_capital" in e for e in res.errors)


def test_rejects_trailing_backslash_continuation() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
x = 1 + 2 + \\
    3 + 4
plot(close, "Close")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("\\" in e or "continuation" in e for e in res.errors)


def test_rejects_request_security_too_few_args() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
btc = request.security("BTC", close)
plot(btc, "BTC")
"""
    res = validate_pine(src)
    assert not res.ok
    assert any("too few" in e for e in res.errors)


# ---------------------------------------------------------------------------
# 3) Warnings (non-fatal)
# ---------------------------------------------------------------------------


def test_warns_on_todo_marker() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
// TODO: implement this
plot(close, "Close")
"""
    res = validate_pine(src)
    # TODO is a warning, not an error.
    assert res.ok
    assert any("TODO" in w for w in res.warnings)


def test_warns_on_fixme_marker() -> None:
    src = """\
//@version=5
strategy("Test", overlay=true)
// FIXME: edge case
plot(close, "Close")
"""
    res = validate_pine(src)
    assert res.ok
    assert any("FIXME" in w for w in res.warnings)


def test_warns_on_double_version_directive() -> None:
    src = """\
//@version=5
//@version=5
strategy("Test", overlay=true)
plot(close, "Close")
"""
    res = validate_pine(src)
    assert res.ok
    assert any("more than once" in w for w in res.warnings)


def test_does_not_count_parens_in_strings() -> None:
    """Parens in string literals must not break the balance counter."""
    src = """\
//@version=5
strategy("Hello (World)", overlay=true)
msg = "( ) ( ) ("
plot(close, "Close")
"""
    res = validate_pine(src)
    # Should pass — the string-stripping helper handles this case.
    assert res.ok, f"errors: {res.errors}"


def test_does_not_count_parens_in_comments() -> None:
    src = """\
//@version=5
// (((((( all of these are in a comment ((((
strategy("Test", overlay=true)
plot(close, "Close")
"""
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"


# ---------------------------------------------------------------------------
# 4) Type checks
# ---------------------------------------------------------------------------


def test_validate_pine_type_error() -> None:
    with pytest.raises(TypeError):
        validate_pine(b"not a string")  # type: ignore[arg-type]


def test_stats_reports_length_and_lines() -> None:
    res = validate_pine(_good_pine())
    assert res.stats["length"] > 0
    assert res.stats["lines"] > 0


def test_validation_result_dataclass_default_factory() -> None:
    """PineValidationResult() with errors=None should still produce a list."""
    r = PineValidationResult(ok=True)
    assert r.errors == []
    assert r.warnings == []
    assert r.stats == {}
