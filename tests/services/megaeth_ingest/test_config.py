"""Tests for config loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from megaeth_ingest.config import (
    DEFAULT_CHAIN_ID,
    DEFAULT_HEALTH_PORT,
    DEFAULT_HTTP_RPC,
    DEFAULT_QUEUE_MAX,
    DEFAULT_SIGNAL_LOGGER_URL,
    DEFAULT_WSS,
    MAINNET_CHAIN_ID,
    TESTNET_CHAIN_ID,
    WSSRequiredError,
    assert_startup_invariants,
    killswitch_active,
    load_config,
)


def test_defaults_when_no_env_no_yaml(tmp_path):
    cfg = load_config(env={}, config_path=tmp_path / "missing.yaml")
    assert cfg.wss_url == DEFAULT_WSS
    assert cfg.chain_id == DEFAULT_CHAIN_ID
    assert cfg.health_port == DEFAULT_HEALTH_PORT
    assert cfg.signal_logger_url == DEFAULT_SIGNAL_LOGGER_URL
    assert cfg.queue_max == DEFAULT_QUEUE_MAX
    assert cfg.forwarding_enabled is False
    assert cfg.log_filters == ()


def test_chain_id_constants_match_canonical_values():
    """Mainnet 4326 (0x10e6); testnet (carrot) 6343 (0x18c7)."""
    assert MAINNET_CHAIN_ID == 4326
    assert TESTNET_CHAIN_ID == 6343
    # The default must point at mainnet now.
    assert DEFAULT_CHAIN_ID == MAINNET_CHAIN_ID


def test_default_targets_mainnet_http_with_no_wss(tmp_path):
    """Defaults: mainnet HTTP, blank WSS, polling-mode-by-default."""
    cfg = load_config(env={}, config_path=tmp_path / "missing.yaml")
    assert cfg.http_rpc_url == DEFAULT_HTTP_RPC == "https://mainnet.megaeth.com/rpc"
    assert cfg.wss_url == ""
    assert cfg.use_http_polling is True
    assert cfg.wss_required is False
    assert cfg.poll_interval_sec == 1.0


def test_assert_startup_invariants_passes_for_polling_mode(tmp_path):
    cfg = load_config(env={}, config_path=tmp_path / "missing.yaml")
    # Default is HTTP-polling — should not raise.
    assert_startup_invariants(cfg)


def test_assert_startup_invariants_refuses_when_wss_required_but_no_url(tmp_path):
    cfg = load_config(
        env={"SAPPHIRE_MEGAETH_WSS_REQUIRED": "1"},
        config_path=tmp_path / "missing.yaml",
    )
    assert cfg.wss_required is True
    assert cfg.wss_url == ""
    with pytest.raises(WSSRequiredError, match="public mainnet WSS unavailable"):
        assert_startup_invariants(cfg)


def test_assert_startup_invariants_passes_when_wss_required_with_url(tmp_path):
    cfg = load_config(
        env={
            "SAPPHIRE_MEGAETH_WSS_REQUIRED": "1",
            "SAPPHIRE_MEGAETH_WSS": "wss://partner.example/megaeth",
        },
        config_path=tmp_path / "missing.yaml",
    )
    assert cfg.wss_required is True
    assert cfg.wss_url == "wss://partner.example/megaeth"
    assert cfg.use_http_polling is False
    # Should not raise.
    assert_startup_invariants(cfg)


def test_testnet_override_via_env(tmp_path):
    """Operator opts in to carrot testnet via env."""
    cfg = load_config(
        env={
            "SAPPHIRE_MEGAETH_CHAIN_ID": str(TESTNET_CHAIN_ID),
            "SAPPHIRE_MEGAETH_RPC_URL": "https://carrot.megaeth.com/rpc",
            "SAPPHIRE_MEGAETH_WSS": "wss://carrot.megaeth.com/ws",
        },
        config_path=tmp_path / "missing.yaml",
    )
    assert cfg.chain_id == 6343
    assert cfg.http_rpc_url == "https://carrot.megaeth.com/rpc"
    assert cfg.wss_url == "wss://carrot.megaeth.com/ws"
    assert cfg.use_http_polling is False


def test_env_overrides_defaults(tmp_path):
    cfg = load_config(
        env={
            "SAPPHIRE_MEGAETH_WSS": "wss://example.test/ws",
            "SAPPHIRE_MEGAETH_CHAIN_ID": "9999",
            "SAPPHIRE_MEGAETH_HEALTH_PORT": "9999",
            "SAPPHIRE_MEGAETH_INGEST_ENABLED": "1",
            "SAPPHIRE_MEGAETH_QUEUE_MAX": "256",
            "WEBHOOK_SECRET": "topsecret",
        },
        config_path=tmp_path / "missing.yaml",
    )
    assert cfg.wss_url == "wss://example.test/ws"
    assert cfg.chain_id == 9999
    assert cfg.health_port == 9999
    assert cfg.forwarding_enabled is True
    assert cfg.queue_max == 256
    assert cfg.webhook_secret == "topsecret"


def test_env_overrides_yaml(tmp_path):
    yaml_path = tmp_path / "megaeth.yaml"
    yaml_path.write_text(
        "wss_url: wss://from-yaml.test/ws\n"
        "chain_id: 1234\n"
        "forwarding_enabled: false\n"
        "queue_max: 1000\n"
    )
    cfg = load_config(
        env={"SAPPHIRE_MEGAETH_WSS": "wss://from-env.test/ws"},
        config_path=yaml_path,
    )
    # env wins for wss_url
    assert cfg.wss_url == "wss://from-env.test/ws"
    # yaml is used for keys not in env
    assert cfg.chain_id == 1234
    assert cfg.queue_max == 1000


def test_log_filters_from_yaml(tmp_path):
    yaml_path = tmp_path / "megaeth.yaml"
    yaml_path.write_text(
        "log_filters:\n"
        "  - addresses:\n"
        "      - '0x" + "0" * 39 + "1'\n"
        "    topics:\n"
        "      - '0xabc'\n"
        "  - addresses: ['0x" + "1" * 39 + "2']\n"
    )
    cfg = load_config(env={}, config_path=yaml_path)
    assert len(cfg.log_filters) == 2
    assert cfg.log_filters[0].addresses == ("0x" + "0" * 39 + "1",)
    assert cfg.log_filters[0].topics == ("0xabc",)
    assert cfg.log_filters[1].topics == ()


def test_log_filters_from_env_json(tmp_path):
    addr = "0x" + "a" * 40
    cfg = load_config(
        env={
            "SAPPHIRE_MEGAETH_LOG_FILTERS": json.dumps(
                [{"addresses": [addr], "topics": ["0xdead"]}]
            )
        },
        config_path=tmp_path / "missing.yaml",
    )
    assert len(cfg.log_filters) == 1
    assert cfg.log_filters[0].addresses == (addr,)
    assert cfg.log_filters[0].topics == ("0xdead",)


def test_log_filters_drop_invalid_addresses(tmp_path):
    cfg = load_config(
        env={
            "SAPPHIRE_MEGAETH_LOG_FILTERS": json.dumps(
                [
                    {"addresses": ["not-an-address"]},  # dropped — no valid addr → no filter
                    {"addresses": ["0x" + "b" * 40, "GARBAGE"]},  # one valid
                ]
            )
        },
        config_path=tmp_path / "missing.yaml",
    )
    assert len(cfg.log_filters) == 1
    assert cfg.log_filters[0].addresses == ("0x" + "b" * 40,)


def test_killswitch_active(tmp_path: Path):
    pause = tmp_path / "pause"
    assert killswitch_active(pause) is False
    pause.write_text("")
    assert killswitch_active(pause) is True
    pause.unlink()
    assert killswitch_active(pause) is False


def test_killswitch_path_override(tmp_path):
    custom = tmp_path / "custom_pause"
    cfg = load_config(
        env={"SAPPHIRE_MEGAETH_KILLSWITCH": str(custom)},
        config_path=tmp_path / "missing.yaml",
    )
    assert cfg.killswitch_path == custom


def test_queue_max_floor(tmp_path):
    cfg = load_config(
        env={"SAPPHIRE_MEGAETH_QUEUE_MAX": "1"},
        config_path=tmp_path / "missing.yaml",
    )
    assert cfg.queue_max == 16  # floor


def test_reconnect_max_lower_bound(tmp_path):
    # If max < backoff, max is raised to match.
    cfg = load_config(
        env={
            "SAPPHIRE_MEGAETH_RECONNECT_BACKOFF": "10",
            "SAPPHIRE_MEGAETH_RECONNECT_MAX": "1",
        },
        config_path=tmp_path / "missing.yaml",
    )
    assert cfg.reconnect_backoff_sec == 10.0
    assert cfg.reconnect_max_sec == 10.0
