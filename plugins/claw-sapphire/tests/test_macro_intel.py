from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "macro_intel.py"

_spec = importlib.util.spec_from_file_location("macro_intel_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
macro_intel = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = macro_intel
_spec.loader.exec_module(macro_intel)


@pytest.fixture
def isolated_output(monkeypatch, tmp_path):
    out = tmp_path / "data" / "macro"
    monkeypatch.setattr(macro_intel, "DEFAULT_OUTPUT_ROOT", out)
    monkeypatch.delenv("SAPPHIRE_MACRO_INTEL_LIVE", raising=False)
    monkeypatch.delenv("SAPPHIRE_MACRO_INTEL_LIVE_BUS", raising=False)
    return out


def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_recent_action_reads_events(isolated_output):
    path = isolated_output / "2026-04-28" / "events.jsonl"
    write_jsonl(
        path,
        [
            {
                "id": "macro-1",
                "source": "fed_rss",
                "title": "FOMC Holds Rates",
                "metadata": {"source_url": "https://www.federalreserve.gov/example"},
            }
        ],
    )
    out = macro_intel.recent_action(date="2026-04-28")
    assert out["ok"] is True
    assert out["count"] == 1
    assert out["events"][0]["id"] == "macro-1"


def test_recent_action_missing_returns_soft_not_ok(isolated_output):
    out = macro_intel.recent_action(date="1900-01-01")
    assert out["ok"] is False
    assert out["events"] == []


def test_calendar_action_reads_file(isolated_output):
    path = isolated_output / "2026-04-28" / "calendar.jsonl"
    write_jsonl(
        path,
        [
            {
                "id": "cal-1",
                "title": "FOMC meeting",
                "category": "monetary_policy",
                "scheduled_at": "2026-04-28T18:00:00+00:00",
                "source": "fed_fomc",
                "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "assets": ["BTC", "USD"],
                "metadata": {"official_source": True},
            }
        ],
    )
    out = macro_intel.calendar_action(date="2026-04-28")
    assert out["ok"] is True
    assert out["calendar"][0]["id"] == "cal-1"


def test_calendar_action_falls_back_to_static_schedule(isolated_output):
    out = macro_intel.calendar_action(date="1900-01-01")
    assert out["ok"] is True
    assert out["count"] >= 1
    assert out["calendar"][0]["source_url"].startswith("https://www.bls.gov")


def test_next_event_for_asset_finds_match(isolated_output):
    path = isolated_output / datetime.now(UTC).strftime("%Y-%m-%d") / "calendar.jsonl"
    write_jsonl(
        path,
        [
            {
                "id": "cal-1",
                "title": "Treasury auction",
                "category": "treasury_auction",
                "scheduled_at": "2099-01-01T17:00:00+00:00",
                "source": "treasury_auctions",
                "source_url": "https://www.treasurydirect.gov/auctions/auctions-query/",
                "assets": ["BTC", "USD", "bonds"],
                "metadata": {"official_source": True},
            }
        ],
    )
    out = macro_intel.next_event_for_asset_action(asset="btc")
    assert out["ok"] is True
    assert out["event"]["id"] == "cal-1"


def test_next_event_for_asset_requires_asset(isolated_output):
    assert macro_intel.next_event_for_asset_action(asset="")["ok"] is False


def test_pull_once_defaults_to_dry_run(isolated_output):
    out = macro_intel.pull_once_action({"action": "pull-once", "live": True})
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert "SAPPHIRE_MACRO_INTEL_LIVE" in out["reason"]


def test_status_action_reports_caps(isolated_output):
    out = macro_intel.status_action()
    assert out["ok"] is True
    assert out["caps"]["max_pulls_per_hour_per_source"] == 4
    assert out["tool_version"] == "0.1.0"


def test_handle_unknown_action(isolated_output):
    out = macro_intel.handle({"action": "magic"})
    assert out["ok"] is False
    assert "valid_actions" in out


def test_main_reads_stdin_and_writes_json(isolated_output):
    out_buf = io.StringIO()
    rc = macro_intel.main(
        stream_in=io.StringIO(json.dumps({"action": "calendar"})),
        stream_out=out_buf,
    )
    parsed = json.loads(out_buf.getvalue())
    assert rc == 0
    assert parsed["ok"] is True
    assert "calendar" in parsed


def test_main_rejects_invalid_json(isolated_output):
    out_buf = io.StringIO()
    rc = macro_intel.main(stream_in=io.StringIO("{nope"), stream_out=out_buf)
    assert rc == 2
    assert "invalid JSON" in out_buf.getvalue()
