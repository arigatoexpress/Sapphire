"""Golden contract for heartbeat transition notifications.

The service monitor delegates delivery to the notification tool.  Keep this
test network-free: it pins only the subprocess boundary and never invokes the
Telegram transport.
"""

from __future__ import annotations

import subprocess

from services.heartbeat import heartbeat


def test_transition_notification_uses_notify_cli_contract(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(heartbeat.subprocess, "run", fake_run)

    heartbeat._notify("service changed", priority="p1")

    assert calls == [
        {
            "argv": [
                heartbeat.sys.executable,
                str(heartbeat.NOTIFY_DIR / "notify.py"),
                "--priority",
                "p1",
                "service changed",
            ],
            "capture_output": True,
            "text": True,
            "timeout": 15,
        }
    ]
