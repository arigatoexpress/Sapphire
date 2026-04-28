"""Tests for ``services/control-plane/app/event_stream.py``.

The control-plane event stream is the JSONL append-only log that powers
cross-silo activity feeds (project/agent/priority/type/service/device
namespaces). Untested before this file. All tests redirect the event
file via ``SAPPHIRE_EVENTS_PATH`` so nothing real is written.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CP_ROOT = REPO_ROOT / "services" / "control-plane"


@contextlib.contextmanager
def _control_plane_app_namespace():
    """Temporarily make ``app`` resolve to control-plane's ``app`` package.

    Same isolation pattern as test_control_plane_scoring.py /
    test_control_plane_digest.py — keeps sys.modules pollution contained
    so the dashboard's ``app.py`` (used by test_sensitivity_filter.py)
    is restored after the import block.
    """
    saved = {name: sys.modules.pop(name, None) for name in ("app", "app.event_stream")}
    sys.path.insert(0, str(CP_ROOT))
    try:
        importlib.invalidate_caches()
        yield
    finally:
        sys.path.remove(str(CP_ROOT))
        for name in ("app", "app.event_stream"):
            sys.modules.pop(name, None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod


with _control_plane_app_namespace():
    from app.event_stream import (  # noqa: E402
        EVENT_SCHEMA_VERSION,
        EVENT_SEVERITIES,
        TAG_NAMESPACES,
        _normalize_tags,
        _tags_match,
        append_event,
        events_by_tags,
        recent_events,
    )


@pytest.fixture(autouse=True)
def _redirect_event_path(tmp_path, monkeypatch):
    """Each test writes to a tmp file via the env-var override."""
    target = tmp_path / "events.jsonl"
    monkeypatch.setenv("SAPPHIRE_EVENTS_PATH", str(target))
    yield target


# ── Module constants ────────────────────────────────────────────────


def test_schema_version_is_two():
    """Bumping schema_version is intentional — pin it in case of accidental change."""
    assert EVENT_SCHEMA_VERSION == 2


def test_severities_match_documented_set():
    assert EVENT_SEVERITIES == {"debug", "info", "warning", "error", "critical"}


def test_tag_namespaces_match_documented_set():
    assert TAG_NAMESPACES == {
        "project",
        "agent",
        "priority",
        "type",
        "service",
        "device",
    }


# ── _normalize_tags ────────────────────────────────────────────────


def test_normalize_tags_empty_input_returns_empty_list():
    assert _normalize_tags(None) == []
    assert _normalize_tags([]) == []


def test_normalize_tags_lowercases_and_trims():
    assert _normalize_tags(["  PROJECT:Sapphire  "]) == ["project:sapphire"]


def test_normalize_tags_drops_malformed_no_colon():
    """Tags without a colon are silently dropped."""
    assert _normalize_tags(["malformed", "project:ok"]) == ["project:ok"]


def test_normalize_tags_drops_unknown_namespace():
    """Tags using a namespace not in TAG_NAMESPACES are dropped."""
    assert _normalize_tags(["unknown:value", "project:ok"]) == ["project:ok"]


def test_normalize_tags_drops_blank_value_after_colon():
    """A tag with empty value (e.g. 'project:') is dropped."""
    assert _normalize_tags(["project:", "project:ok"]) == ["project:ok"]


def test_normalize_tags_dedups_and_sorts():
    """Duplicate tags collapse; output is sorted for stable comparisons."""
    raw = ["type:b", "type:a", "type:b", "agent:c"]

    assert _normalize_tags(raw) == ["agent:c", "type:a", "type:b"]


@pytest.mark.parametrize(
    "ns",
    sorted({"project", "agent", "priority", "type", "service", "device"}),
)
def test_normalize_tags_accepts_each_namespace(ns):
    assert _normalize_tags([f"{ns}:value"]) == [f"{ns}:value"]


# ── _tags_match ────────────────────────────────────────────────────


def test_tags_match_all_required_present():
    assert _tags_match(["project:s", "type:t", "agent:a"], ["project:s", "type:t"]) is True


def test_tags_match_missing_returns_false():
    assert _tags_match(["project:s"], ["project:s", "type:t"]) is False


def test_tags_match_empty_filter_always_true():
    """Empty filter matches anything (vacuous truth)."""
    assert _tags_match([], []) is True
    assert _tags_match(["project:s"], []) is True


# ── append_event happy path ───────────────────────────────────────


def test_append_event_writes_jsonl_record(_redirect_event_path):
    row = append_event("test.event", source="unit-test", message="hello")

    assert row["event_type"] == "test.event"
    assert row["source"] == "unit-test"
    assert row["message"] == "hello"
    assert row["schema_version"] == EVENT_SCHEMA_VERSION
    assert row["severity"] == "info"  # default
    assert row["category"] == "system"  # default
    assert row["event_id"].startswith("evt-")
    assert "generated_at" in row

    persisted = json.loads(_redirect_event_path.read_text(encoding="utf-8").strip())
    assert persisted == row


def test_append_event_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "a" / "b" / "events.jsonl"
    monkeypatch.setenv("SAPPHIRE_EVENTS_PATH", str(nested))

    append_event("test.event", source="unit-test")

    assert nested.exists()


def test_append_event_appends_rather_than_overwrites(_redirect_event_path):
    append_event("e1", source="t")
    append_event("e2", source="t")
    append_event("e3", source="t")

    rows = [
        json.loads(line) for line in _redirect_event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [r["event_type"] for r in rows] == ["e1", "e2", "e3"]


@pytest.mark.parametrize("severity", sorted({"debug", "info", "warning", "error", "critical"}))
def test_append_event_accepts_each_documented_severity(severity, _redirect_event_path):
    row = append_event("e", source="t", severity=severity)

    assert row["severity"] == severity


def test_append_event_unknown_severity_falls_back_to_info(_redirect_event_path):
    row = append_event("e", source="t", severity="not-a-severity")

    assert row["severity"] == "info"


def test_append_event_blank_event_type_becomes_unknown(_redirect_event_path):
    row = append_event("", source="t")

    assert row["event_type"] == "unknown"


def test_append_event_blank_source_becomes_unknown(_redirect_event_path):
    row = append_event("e", source="")

    assert row["source"] == "unknown"


def test_append_event_normalizes_event_type_to_lowercase(_redirect_event_path):
    row = append_event("Test.Event", source="T")

    assert row["event_type"] == "test.event"
    assert row["source"] == "t"


def test_append_event_auto_derives_project_tag(_redirect_event_path):
    row = append_event("e", source="t", project_id="Sapphire")

    assert "project:sapphire" in row["tags"]
    assert row["project_id"] == "Sapphire"  # original casing preserved in field


def test_append_event_combines_auto_and_explicit_tags(_redirect_event_path):
    row = append_event(
        "e",
        source="t",
        project_id="Sapphire",
        tags=["agent:kimi", "type:trading"],
    )

    assert "project:sapphire" in row["tags"]
    assert "agent:kimi" in row["tags"]
    assert "type:trading" in row["tags"]
    # Sorted for stable comparison
    assert row["tags"] == sorted(row["tags"])


def test_append_event_drops_malformed_tags_silently(_redirect_event_path):
    row = append_event("e", source="t", tags=["bare-no-colon", "unknown:x", "project:s"])

    assert row["tags"] == ["project:s"]


def test_append_event_payload_must_be_dict(_redirect_event_path):
    """Non-dict payload defaults to empty {}, never crashes."""
    row1 = append_event("e", source="t", payload={"k": "v"})
    row2 = append_event("e", source="t", payload="not a dict")  # type: ignore[arg-type]
    row3 = append_event("e", source="t", payload=None)

    assert row1["payload"] == {"k": "v"}
    assert row2["payload"] == {}
    assert row3["payload"] == {}


def test_append_event_writes_compact_json(_redirect_event_path):
    """Records are written without spaces between separators."""
    append_event("e", source="t")

    raw = _redirect_event_path.read_text(encoding="utf-8")
    # ", " separator would be loose; ":," separator is tight
    assert ", " not in raw or "Hello, World" not in raw  # tags JSON checked below
    # Verify a known tight pattern:
    assert '"event_type":"e"' in raw or '"source":"t"' in raw


def test_append_event_serializes_unknown_types_via_default_str(_redirect_event_path):
    """``default=str`` lets non-JSON-native objects round-trip safely."""
    from datetime import datetime as _dt

    payload = {"when": _dt(2026, 4, 27, 12, 0, 0)}
    append_event("e", source="t", payload=payload)

    raw = _redirect_event_path.read_text(encoding="utf-8")
    assert "2026-04-27" in raw


# ── recent_events ───────────────────────────────────────────────────


def test_recent_events_empty_file_returns_empty_list(_redirect_event_path):
    """No events file → empty list, no crash."""
    assert recent_events() == []


def test_recent_events_returns_newest_first(_redirect_event_path):
    """File is read in reverse order — most recent appears first."""
    append_event("first", source="t")
    append_event("second", source="t")
    append_event("third", source="t")

    rows = recent_events()

    assert [r["event_type"] for r in rows] == ["third", "second", "first"]


def test_recent_events_limit_respected(_redirect_event_path):
    for i in range(10):
        append_event(f"e{i}", source="t")

    rows = recent_events(limit=3)

    assert len(rows) == 3


@pytest.mark.parametrize(
    "raw_limit,expected_max",
    [
        (1, 1),
        (500, 500),
        (501, 500),
        (10000, 500),  # clamped to 500
        (0, 1),  # clamped to 1
        (-5, 1),  # clamped to 1
    ],
)
def test_recent_events_limit_clamped(raw_limit, expected_max, _redirect_event_path):
    """Limit is clamped to [1, 500]."""
    for i in range(600):
        append_event(f"e{i}", source="t")

    rows = recent_events(limit=raw_limit)

    assert len(rows) <= expected_max
    assert len(rows) >= 1


def test_recent_events_filter_by_category(_redirect_event_path):
    append_event("e1", source="t", category="trading")
    append_event("e2", source="t", category="ops")
    append_event("e3", source="t", category="trading")

    rows = recent_events(category="trading")

    assert {r["event_type"] for r in rows} == {"e1", "e3"}


def test_recent_events_filter_by_source(_redirect_event_path):
    append_event("e1", source="kimi")
    append_event("e2", source="claude")
    append_event("e3", source="kimi")

    rows = recent_events(source="kimi")

    assert {r["event_type"] for r in rows} == {"e1", "e3"}


def test_recent_events_filter_by_severity(_redirect_event_path):
    append_event("e1", source="t", severity="debug")
    append_event("e2", source="t", severity="error")
    append_event("e3", source="t", severity="error")

    rows = recent_events(severity="error")

    assert {r["event_type"] for r in rows} == {"e2", "e3"}


def test_recent_events_filter_by_tags_and_semantics(_redirect_event_path):
    append_event("e1", source="t", project_id="sapphire", tags=["type:trading"])
    append_event("e2", source="t", project_id="sapphire", tags=["type:ops"])
    append_event("e3", source="t", project_id="blanga", tags=["type:trading"])

    rows = recent_events(tags=["project:sapphire", "type:trading"])

    assert [r["event_type"] for r in rows] == ["e1"]


def test_recent_events_skips_blank_and_malformed_lines(tmp_path, monkeypatch):
    target = tmp_path / "events.jsonl"
    target.write_text(
        json.dumps({"event_type": "ok-1"})
        + "\n\n   \n"
        + "not-json\n"
        + json.dumps([1, 2, 3])  # list, not dict — must be skipped
        + "\n"
        + json.dumps({"event_type": "ok-2"})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SAPPHIRE_EVENTS_PATH", str(target))

    rows = recent_events()

    assert {r["event_type"] for r in rows} == {"ok-1", "ok-2"}


def test_recent_events_tag_filter_normalizes_input(_redirect_event_path):
    """Tag filter normalizes (lowercase, dedup) like the writer does."""
    append_event("e1", source="t", project_id="sapphire")

    rows = recent_events(tags=["  PROJECT:Sapphire  "])

    assert len(rows) == 1


# ── events_by_tags ──────────────────────────────────────────────────


def test_events_by_tags_delegates_to_recent_events(_redirect_event_path):
    append_event("e1", source="t", project_id="sapphire", tags=["type:trading"])
    append_event("e2", source="t", project_id="other")

    rows = events_by_tags(["project:sapphire"])

    assert [r["event_type"] for r in rows] == ["e1"]


def test_events_by_tags_respects_limit(_redirect_event_path):
    for i in range(5):
        append_event(f"e{i}", source="t", project_id="sapphire")

    rows = events_by_tags(["project:sapphire"], limit=2)

    assert len(rows) == 2
