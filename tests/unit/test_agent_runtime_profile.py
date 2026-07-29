from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.agents.runtime_profile import (
    RuntimeProfileError,
    deprecated_launchagent_labels,
    load_runtime_profile,
    required_local_models,
    validate_runtime_profile,
)

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_profile_loads_repo_config() -> None:
    profile = load_runtime_profile(ROOT / "config" / "agent_runtime_next.yaml")

    assert profile["policy"]["bot_api_ingress_owner"] == "sapphire_pm_bot"
    assert required_local_models(profile) == ["gemma3:4b", "deepseek-r1:14b"]
    assert "com.sapphire.healthz-watcher" in deprecated_launchagent_labels(profile)


def test_runtime_profile_rejects_live_send_default() -> None:
    profile = json.loads(json.dumps(load_runtime_profile()))
    profile["policy"]["telegram_send_default"] = "send_live"

    with pytest.raises(RuntimeProfileError, match="draft_only"):
        validate_runtime_profile(profile)


def test_runtime_profile_rejects_deprecated_default_model() -> None:
    profile = json.loads(json.dumps(load_runtime_profile()))
    profile["model_lanes"][0]["recommended_model"] = "nemotron-mini:4b"

    with pytest.raises(RuntimeProfileError, match="deprecated local model"):
        validate_runtime_profile(profile)


def test_runtime_profile_requires_hosted_defaults() -> None:
    profile = json.loads(json.dumps(load_runtime_profile()))
    for lane in profile["model_lanes"]:
        if lane["provider"] == "google_vertex":
            lane["default"] = False

    with pytest.raises(RuntimeProfileError, match="google_vertex"):
        validate_runtime_profile(profile)
