from __future__ import annotations

from pathlib import Path

import pytest

from lib.core import routine_pause


def test_is_paused_false_when_flag_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(routine_pause, "PAUSE_DIR", tmp_path)

    assert routine_pause.is_paused("morning-brief") is False


def test_is_paused_true_when_flag_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(routine_pause, "PAUSE_DIR", tmp_path)
    (tmp_path / "morning-brief").write_text("2026-04-28T00:00:00Z")

    assert routine_pause.is_paused("morning-brief") is True


def test_is_paused_falls_back_false_on_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(routine_pause, "PAUSE_DIR", tmp_path)

    def raise_oserror(self: Path) -> bool:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "exists", raise_oserror)

    assert routine_pause.is_paused("morning-brief") is False


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../morning-brief",
        "morning/brief",
        "morning\x00brief",
        "morning.brief",
        "morning brief",
    ],
)
def test_routine_name_sanitization_rejects_invalid_names(name: str) -> None:
    with pytest.raises(ValueError):
        routine_pause.is_paused(name)


def test_abort_if_paused_logs_structured_message_and_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(routine_pause, "PAUSE_DIR", tmp_path)
    (tmp_path / "morning-brief").write_text("paused")
    messages: list[str] = []

    with pytest.raises(SystemExit) as exc:
        routine_pause.abort_if_paused("morning-brief", log=messages.append)

    assert exc.value.code == 0
    assert messages == [
        '{"event": "routine_pause.skipped", "pause_flag": "'
        + str(tmp_path / "morning-brief")
        + '", "routine": "morning-brief"}'
    ]
