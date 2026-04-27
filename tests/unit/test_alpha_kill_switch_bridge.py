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


def test_mirror_uses_default_singleton_when_switch_missing(monkeypatch):
    """When `switch=None`, the bridge fetches the global kill switch.

    We patch the import target so we never touch the real singleton.
    """
    calls: dict[str, object] = {}

    class _StubSwitch:
        def force_activate(self, reason, *, notify=True):
            calls["activate"] = (reason, notify)
            return True

        def force_deactivate(self, reason, *, notify=True):
            calls["deactivate"] = (reason, notify)
            return True

    fake_switch = _StubSwitch()

    import lib.core.kill_switch as ks_mod

    monkeypatch.setattr(ks_mod, "get_kill_switch", lambda: fake_switch)

    assert mirror_alpha_kill_switch(True, "default-switch test") is True
    assert calls["activate"] == ("alpha_control: default-switch test", False)


def test_mirror_uses_default_singleton_for_deactivate(monkeypatch):
    """The default-singleton path also covers the deactivate branch."""
    calls: dict[str, object] = {}

    class _StubSwitch:
        def force_activate(self, reason, *, notify=True):  # pragma: no cover
            raise AssertionError("activate must not be called for resume")

        def force_deactivate(self, reason, *, notify=True):
            calls["deactivate"] = (reason, notify)
            return True

    import lib.core.kill_switch as ks_mod

    monkeypatch.setattr(ks_mod, "get_kill_switch", lambda: _StubSwitch())

    assert mirror_alpha_kill_switch(False, "all clear") is True
    assert calls["deactivate"] == ("alpha_control: all clear", False)


def test_mirror_blank_reason_falls_back_to_active_default(tmp_path):
    """An empty/whitespace reason on activate becomes 'manual kill switch'."""
    switch = KillSwitch(
        notify=lambda *args, **kwargs: None,
        now=lambda: datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        audit_path=tmp_path / "kill_switch.jsonl",
    )

    assert mirror_alpha_kill_switch(True, "   ", switch=switch)
    record = json.loads((tmp_path / "kill_switch.jsonl").read_text().splitlines()[0])
    assert record["reason"] == "alpha_control: manual kill switch"


def test_mirror_blank_reason_falls_back_to_resume_default(tmp_path):
    """An empty/whitespace reason on deactivate becomes 'manual resume'."""
    switch = KillSwitch(
        notify=lambda *args, **kwargs: None,
        now=lambda: datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        audit_path=tmp_path / "kill_switch.jsonl",
    )
    # Pre-activate so we have a state to deactivate from.
    switch.force_activate("seed", notify=False)

    assert mirror_alpha_kill_switch(False, "", switch=switch)
    records = [
        json.loads(line) for line in (tmp_path / "kill_switch.jsonl").read_text().splitlines()
    ]
    # The last record is the bridged deactivation.
    assert records[-1]["reason"] == "alpha_control: manual resume"


def test_mirror_custom_source_prefix(tmp_path):
    """The `source` parameter is the audit-log prefix before the colon."""
    switch = KillSwitch(
        notify=lambda *args, **kwargs: None,
        now=lambda: datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        audit_path=tmp_path / "kill_switch.jsonl",
    )

    assert mirror_alpha_kill_switch(
        True,
        "ops drill",
        switch=switch,
        source="security_console",
    )
    record = json.loads((tmp_path / "kill_switch.jsonl").read_text().splitlines()[0])
    assert record["reason"] == "security_console: ops drill"


def test_mirror_notify_true_propagates_to_underlying_switch():
    """notify=True must be forwarded to force_activate/deactivate."""
    captured: dict[str, dict] = {}

    class _StubSwitch:
        def force_activate(self, reason, *, notify=True):
            captured["activate"] = {"reason": reason, "notify": notify}
            return True

        def force_deactivate(self, reason, *, notify=True):
            captured["deactivate"] = {"reason": reason, "notify": notify}
            return True

    s = _StubSwitch()
    assert mirror_alpha_kill_switch(True, "halt", switch=s, notify=True)
    assert mirror_alpha_kill_switch(False, "resume", switch=s, notify=True)
    assert captured["activate"]["notify"] is True
    assert captured["deactivate"]["notify"] is True


def test_mirror_returns_underlying_switch_boolean():
    """The return value is exactly what the underlying switch reports."""

    class _StubSwitch:
        def __init__(self, activate_ret: bool, deactivate_ret: bool) -> None:
            self.activate_ret = activate_ret
            self.deactivate_ret = deactivate_ret

        def force_activate(self, reason, *, notify=True):  # noqa: ARG002
            return self.activate_ret

        def force_deactivate(self, reason, *, notify=True):  # noqa: ARG002
            return self.deactivate_ret

    truthy = _StubSwitch(activate_ret=True, deactivate_ret=True)
    falsy = _StubSwitch(activate_ret=False, deactivate_ret=False)

    assert mirror_alpha_kill_switch(True, "x", switch=truthy) is True
    assert mirror_alpha_kill_switch(False, "x", switch=truthy) is True
    assert mirror_alpha_kill_switch(True, "x", switch=falsy) is False
    assert mirror_alpha_kill_switch(False, "x", switch=falsy) is False


def test_mirror_strips_surrounding_whitespace_in_reason(tmp_path):
    """Reasons with leading/trailing whitespace are normalized in the audit log."""
    switch = KillSwitch(
        notify=lambda *args, **kwargs: None,
        now=lambda: datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        audit_path=tmp_path / "kill_switch.jsonl",
    )

    assert mirror_alpha_kill_switch(True, "  user halt  ", switch=switch)
    record = json.loads((tmp_path / "kill_switch.jsonl").read_text().splitlines()[0])
    assert record["reason"] == "alpha_control: user halt"
