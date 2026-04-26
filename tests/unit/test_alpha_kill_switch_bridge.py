"""Tests for Alpha-to-core kill-switch mirroring."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.core.alpha_kill_switch_bridge import mirror_alpha_kill_switch
from lib.core.kill_switch import KillSwitch


class _EventRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class _NotifyRecorder:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def __call__(self, text: str, *, priority: str = "p1", **_) -> dict:
        self.messages.append({"text": text, "priority": priority})
        return {"ok": True}


def test_mirror_alpha_halt_and_resume_without_duplicate_notify(tmp_path):
    events = _EventRecorder()
    notifier = _NotifyRecorder()
    switch = KillSwitch(
        publish_event=events,
        notify=notifier,
        now=lambda: datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        audit_path=tmp_path / "kill_switch.jsonl",
    )

    assert mirror_alpha_kill_switch(
        True,
        "Manual command from Telegram",
        switch=switch,
        notify=False,
    )
    assert switch.is_active
    assert notifier.messages == []

    assert mirror_alpha_kill_switch(
        False,
        "Manual command from Telegram",
        switch=switch,
        notify=False,
    )
    assert not switch.is_active
    assert notifier.messages == []

    assert [event_type for event_type, _ in events.events] == [
        "kill_switch.activated",
        "kill_switch.deactivated",
    ]
    records = [
        json.loads(line) for line in (tmp_path / "kill_switch.jsonl").read_text().splitlines()
    ]
    assert records[0]["reason"] == "alpha_control: Manual command from Telegram"
    assert records[1]["reason"] == "alpha_control: Manual command from Telegram"


def test_mirror_alpha_is_transition_only(tmp_path):
    switch = KillSwitch(
        notify=lambda *args, **kwargs: None,
        now=lambda: datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        audit_path=tmp_path / "kill_switch.jsonl",
    )

    assert mirror_alpha_kill_switch(True, "halt", switch=switch)
    assert not mirror_alpha_kill_switch(True, "halt again", switch=switch)
    assert mirror_alpha_kill_switch(False, "resume", switch=switch)
    assert not mirror_alpha_kill_switch(False, "resume again", switch=switch)
