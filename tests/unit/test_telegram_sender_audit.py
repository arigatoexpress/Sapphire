from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = REPO_ROOT / "scripts" / "ops"
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))

import telegram_sender_audit as audit  # noqa: E402


def test_parse_launchctl_list_handles_loaded_and_unloaded_labels():
    output = """PID\tStatus\tLabel
11583\t0\tai.hermes.gateway
-\t0\tcom.sapphire.healthz-watcher
4074\t-15\tcom.sapphire.pm-bot
"""
    agents = audit.parse_launchctl_list(output)

    assert agents["ai.hermes.gateway"]["pid"] == 11583
    assert agents["com.sapphire.healthz-watcher"]["pid"] is None
    assert agents["com.sapphire.pm-bot"]["status"] == -15


def test_parse_disabled_extracts_disabled_labels():
    output = """
disabled services = {
    "ai.hermes.gateway" => disabled
    "com.sapphire.healthz-watcher" => enabled
}
"""
    assert audit.parse_disabled(output) == {"ai.hermes.gateway"}


def test_find_non_desktop_telegram_sockets_ignores_telegram_app():
    output = """COMMAND   PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
Telegram 77881 aribs 36u IPv4 0x1 0t0 TCP 10.2.0.2:64307->149.154.175.52:443 (ESTABLISHED)
Python   80654 aribs 16u IPv4 0x2 0t0 TCP 10.2.0.2:56123->149.154.166.110:443 (ESTABLISHED)
"""
    assert audit.find_non_desktop_telegram_sockets(output) == [
        "Python   80654 aribs 16u IPv4 0x2 0t0 TCP 10.2.0.2:56123->149.154.166.110:443 (ESTABLISHED)"
    ]


def test_build_report_fails_legacy_sender_paths():
    report = audit.build_report(
        launch_agents={
            "ai.hermes.gateway": {"pid": 11583, "status": 0, "label": "ai.hermes.gateway"},
            "com.sapphire.healthz-watcher": {
                "pid": 74552,
                "status": 0,
                "label": "com.sapphire.healthz-watcher",
            },
            "com.sapphire.pm-bot": {"pid": 4074, "status": -15, "label": "com.sapphire.pm-bot"},
        },
        disabled_labels=set(),
        telegram_socket_offenders=["Python -> 149.154.166.110:443"],
        pm_bot_ownership={
            "mode": "webhook",
            "polling_active": False,
            "single_ingress_owner": "pm_bot_webhook_unregistered",
            "agent_group_ready": False,
            "agent_group_blockers": ["webhook_missing"],
        },
        pm_bot_error=None,
        inference_status={
            "telegram_relay_available": True,
            "telegram_relay_enabled": True,
            "active_route": "mac-local",
            "mode": "local_failover",
        },
        inference_error=None,
    )

    assert report["status"] == "fail"
    failed = {check["name"] for check in report["checks"] if check["status"] == "fail"}
    assert failed == {
        "hermes_gateway_polling_disabled",
        "healthz_watcher_direct_send_paused",
        "inference_telegram_relay_disabled",
        "non_desktop_telegram_sockets_absent",
    }


def test_build_report_passes_quiet_rollout_posture():
    report = audit.build_report(
        launch_agents={
            "com.sapphire.pm-bot": {"pid": 4074, "status": -15, "label": "com.sapphire.pm-bot"},
            "com.sapphire.inference-proxy": {
                "pid": 4067,
                "status": -15,
                "label": "com.sapphire.inference-proxy",
            },
        },
        disabled_labels={"ai.hermes.gateway"},
        telegram_socket_offenders=[],
        pm_bot_ownership={
            "mode": "webhook",
            "polling_active": False,
            "single_ingress_owner": "pm_bot_webhook_unregistered",
            "agent_group_ready": False,
            "agent_group_blockers": ["webhook_missing"],
        },
        pm_bot_error=None,
        inference_status={
            "telegram_relay_available": True,
            "telegram_relay_enabled": False,
            "active_route": "mac-local",
            "mode": "local_failover",
        },
        inference_error=None,
    )

    assert report["status"] == "ok"
    assert audit.format_markdown(report).startswith("Status: ok")
