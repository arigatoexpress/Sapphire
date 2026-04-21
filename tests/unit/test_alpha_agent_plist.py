"""Unit tests for the AlphaAgent LaunchAgent plist."""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLIST_PATH = ROOT / "infra" / "launchagents" / "com.sapphire.alpha-agent.plist"

# The plist hard-codes the operator's Mac paths. Skip the host-filesystem
# assertions on CI / non-macOS environments, where /usr/local/bin/python3
# and /Users/aribs/Code/Sapphire do not exist.
_ON_HOST = (
    os.getenv("CI") is None
    and Path("/Users/aribs/Code/Sapphire").is_dir()
)


def _load_plist() -> dict:
    return plistlib.loads(PLIST_PATH.read_bytes())


def test_alpha_agent_plist_parses_as_xml() -> None:
    data = _load_plist()

    assert data["Label"] == "com.sapphire.alpha-agent"
    assert data["KeepAlive"] is True
    assert data["RunAtLoad"] is True
    assert data["WorkingDirectory"] == "/Users/aribs/Code/Sapphire"


def test_alpha_agent_program_and_args_are_wellformed() -> None:
    data = _load_plist()

    assert data["Program"] == "/usr/local/bin/python3"
    assert data["ProgramArguments"] == [
        "/usr/local/bin/python3",
        "-m",
        "lib.agents.runner",
        "--agent",
        "alpha",
        "--interval",
        "300",
    ]


@pytest.mark.skipif(not _ON_HOST, reason="plist paths only exist on the operator Mac")
def test_alpha_agent_program_and_args_point_to_real_paths() -> None:
    data = _load_plist()

    program = Path(data["Program"])
    argv = data["ProgramArguments"]

    assert program.is_file()
    assert Path(argv[0]).is_file()
    assert Path(data["WorkingDirectory"]).is_dir()


def test_alpha_agent_log_dirs_can_be_created(tmp_path: Path) -> None:
    data = _load_plist()
    mirrored_paths = []
    for key in ("StandardOutPath", "StandardErrorPath"):
        mirrored = Path(str(data[key]).replace("/Users/aribs", str(tmp_path)))
        mirrored.parent.mkdir(parents=True, exist_ok=True)
        mirrored_paths.append(mirrored.parent)

    for path in mirrored_paths:
        assert path.is_dir()
