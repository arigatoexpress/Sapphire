"""Deep-coverage tests for ``lib/core/autonomy_audit.py`` security guards.

The existing ``test_autonomy_audit.py`` covers happy-path append + the
two most obvious redaction cases. This file adds the missing edge-case
coverage for the security-critical helpers (``_bounded_text``,
``sanitize_metadata``), the ``_resolve_path`` selection logic, and the
field-bound contract on ``AutonomyAuditLog.append``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.core import autonomy_audit as aa

# ── _bounded_text ────────────────────────────────────────────────────


def test_bounded_text_truncates_long_strings():
    long = "a" * 500

    result = aa._bounded_text(long, max_len=240)

    assert len(result) == 240
    assert result.endswith("...")


def test_bounded_text_collapses_whitespace():
    assert aa._bounded_text("foo\n\n  bar\tbaz") == "foo bar baz"


def test_bounded_text_handles_empty_and_none():
    assert aa._bounded_text(None) == ""  # type: ignore[arg-type]
    assert aa._bounded_text("") == ""


def test_bounded_text_redacts_inline_api_key():
    text = "loaded api_key=sk-AKIA1234 from env"

    result = aa._bounded_text(text)

    assert "sk-AKIA1234" not in result
    assert "<redacted>" in result


@pytest.mark.parametrize(
    "raw,sensitive_substring",
    [
        ("password: hunter2", "hunter2"),
        ("api_key=sk-abc123", "sk-abc123"),
        ("token: abc.xyz.123", "abc.xyz.123"),
        ("secret=topsecret!", "topsecret!"),
        ("private_key: -----BEGIN", "BEGIN"),
        ("Bearer eyJhbGciOiJIUzI1NiI", "eyJhbGc"),
    ],
)
def test_bounded_text_redacts_sensitive_patterns(raw, sensitive_substring):
    result = aa._bounded_text(raw)

    assert sensitive_substring not in result


def test_bounded_text_under_limit_unchanged():
    assert aa._bounded_text("short", max_len=240) == "short"


# ── _stable_hash ─────────────────────────────────────────────────────


def test_stable_hash_returns_12_hex_chars():
    digest = aa._stable_hash("trade-12345")

    assert len(digest) == 12
    assert all(c in "0123456789abcdef" for c in digest)


def test_stable_hash_is_deterministic():
    assert aa._stable_hash("x") == aa._stable_hash("x")


def test_stable_hash_differs_for_different_inputs():
    assert aa._stable_hash("a") != aa._stable_hash("b")


# ── sanitize_metadata: scalars ───────────────────────────────────────


@pytest.mark.parametrize("value", [None, True, False, 42, 3.14, 0])
def test_sanitize_metadata_scalars_pass_through(value):
    assert aa.sanitize_metadata(value) == value


def test_sanitize_metadata_string_bounded():
    long = "x" * 500

    result = aa.sanitize_metadata(long)

    assert isinstance(result, str)
    assert len(result) <= 240


# ── sanitize_metadata: dict redaction ────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "API_KEY",
        "api-key",
        "token",
        "access_token",
        "password",
        "passwd",
        "secret",
        "private_key",
        "private-key",
        "credential",
        "credentials",
        "authorization",
        "Authorization",
    ],
)
def test_sanitize_metadata_redacts_sensitive_keys(key):
    result = aa.sanitize_metadata({key: "value-leak"})

    assert result[key] == "<redacted>"


def test_sanitize_metadata_does_not_redact_clean_keys():
    result = aa.sanitize_metadata({"id": "x", "name": "y", "value": 1})

    assert result == {"id": "x", "name": "y", "value": 1}


def test_sanitize_metadata_redacts_nested_keys():
    result = aa.sanitize_metadata({"outer": {"inner": {"api_key": "leak"}}})

    assert result["outer"]["inner"]["api_key"] == "<redacted>"


def test_sanitize_metadata_caps_dict_at_50_entries():
    payload = {f"key_{i}": i for i in range(60)}

    result = aa.sanitize_metadata(payload)

    # 50 real entries + the truncation marker
    assert len(result) == 51
    assert result["<truncated>"] == 10


def test_sanitize_metadata_bounds_string_keys():
    long_key = "k" * 200

    result = aa.sanitize_metadata({long_key: "v"})

    only_key = next(iter(result))
    assert len(only_key) <= 80


# ── sanitize_metadata: list bounds ───────────────────────────────────


def test_sanitize_metadata_caps_list_at_20_items():
    payload = list(range(30))

    result = aa.sanitize_metadata(payload)

    # 20 real items + the truncation marker dict
    assert len(result) == 21
    assert result[-1] == {"<truncated>": 10}


def test_sanitize_metadata_lists_recurse():
    result = aa.sanitize_metadata([{"api_key": "x"}, {"id": 1}])

    assert result[0]["api_key"] == "<redacted>"
    assert result[1] == {"id": 1}


# ── sanitize_metadata: depth bound ───────────────────────────────────


def test_sanitize_metadata_max_depth_returns_marker():
    payload = {"l1": {"l2": {"l3": {"l4": {"l5": "too deep"}}}}}

    result = aa.sanitize_metadata(payload, max_depth=4)

    # Once we reach max_depth, the value is replaced with the sentinel.
    assert result["l1"]["l2"]["l3"]["l4"] == "<max_depth>"


def test_sanitize_metadata_within_depth_passes():
    payload = {"l1": {"l2": "ok"}}

    result = aa.sanitize_metadata(payload, max_depth=3)

    assert result == {"l1": {"l2": "ok"}}


# ── sanitize_metadata: bytes ────────────────────────────────────────


def test_sanitize_metadata_bytes_become_bounded_text():
    """Bytes fall through to the str() catch-all."""
    result = aa.sanitize_metadata(b"binary blob")

    assert isinstance(result, str)


# ── AutonomyAuditLog._resolve_path ──────────────────────────────────


def test_resolve_path_explicit_path(tmp_path: Path):
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl")

    assert log.path == tmp_path / "audit.jsonl"


def test_resolve_path_false_disables_log():
    log = aa.AutonomyAuditLog(path=False)

    assert log.path is None


def test_resolve_path_env_var(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(aa.AUTONOMY_AUDIT_LOG_ENV, str(tmp_path / "from-env.jsonl"))

    log = aa.AutonomyAuditLog()

    assert log.path == tmp_path / "from-env.jsonl"


def test_resolve_path_default_when_no_env(monkeypatch):
    monkeypatch.delenv(aa.AUTONOMY_AUDIT_LOG_ENV, raising=False)

    log = aa.AutonomyAuditLog()

    assert log.path == aa.DEFAULT_AUTONOMY_AUDIT_LOG


def test_resolve_path_expands_user(monkeypatch):
    monkeypatch.setenv(aa.AUTONOMY_AUDIT_LOG_ENV, "~/test-audit.jsonl")

    log = aa.AutonomyAuditLog()

    assert "~" not in str(log.path)


# ── AutonomyAuditLog.append ─────────────────────────────────────────


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_append_creates_parent_directories(tmp_path: Path):
    nested = tmp_path / "a" / "b" / "c" / "audit.jsonl"
    log = aa.AutonomyAuditLog(path=nested, now=lambda: 0.0)

    log.append("decision", actor="a", action="b", outcome="c")

    assert nested.exists()


def test_append_appends_rather_than_overwrites(tmp_path: Path):
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl", now=lambda: 0.0)

    log.append("e1", actor="a", action="b", outcome="c")
    log.append("e2", actor="a", action="b", outcome="c")
    log.append("e3", actor="a", action="b", outcome="c")

    rows = _read_lines(log.path)
    assert [r["event_type"] for r in rows] == ["e1", "e2", "e3"]


def test_append_omits_optional_risk_when_blank(tmp_path: Path):
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl", now=lambda: 0.0)

    log.append("decision", actor="a", action="b", outcome="c", risk="")

    rows = _read_lines(log.path)
    assert "risk" not in rows[0]


def test_append_includes_optional_risk_when_set(tmp_path: Path):
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl", now=lambda: 0.0)

    log.append("decision", actor="a", action="b", outcome="c", risk="high")

    rows = _read_lines(log.path)
    assert rows[0]["risk"] == "high"


def test_append_omits_optional_object_ref_when_blank(tmp_path: Path):
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl", now=lambda: 0.0)

    log.append("decision", actor="a", action="b", outcome="c")

    rows = _read_lines(log.path)
    assert "object_ref_hash" not in rows[0]
    assert "object_ref_chars" not in rows[0]


def test_append_bounds_text_fields(tmp_path: Path):
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl", now=lambda: 0.0)

    log.append(
        "x" * 200,
        actor="y" * 200,
        action="z" * 300,
        outcome="o" * 200,
    )

    rows = _read_lines(log.path)
    assert len(rows[0]["event_type"]) <= 120
    assert len(rows[0]["actor"]) <= 120
    assert len(rows[0]["action"]) <= 160
    assert len(rows[0]["outcome"]) <= 80


def test_append_writes_compact_sorted_json(tmp_path: Path):
    """Records must be one-line, sort-keyed, separator-tight for log parsers."""
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl", now=lambda: 1.0)

    log.append("decision", actor="a", action="b", outcome="c")

    raw = log.path.read_text(encoding="utf-8")
    assert raw.count("\n") == 1
    # Sorted keys + tight separators
    assert raw == '{"action":"b","actor":"a","event_type":"decision","outcome":"c","ts":1.0}\n'


def test_append_handles_secret_in_metadata_string(tmp_path: Path):
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl", now=lambda: 0.0)

    log.append(
        "decision",
        actor="a",
        action="b",
        outcome="c",
        metadata={"note": "loaded api_key=sk-LEAK from secrets"},
    )

    rows = _read_lines(log.path)
    note = rows[0]["metadata"]["note"]
    assert "sk-LEAK" not in note
    assert "<redacted>" in note


def test_append_default_now_uses_time_module(monkeypatch, tmp_path: Path):
    """When no now-callable is passed, time.time() is used by default."""
    monkeypatch.setattr(aa.time, "time", lambda: 9_999.5)
    log = aa.AutonomyAuditLog(path=tmp_path / "audit.jsonl")

    log.append("decision", actor="a", action="b", outcome="c")

    rows = _read_lines(log.path)
    assert rows[0]["ts"] == 9_999.5
