"""Tests for the read-only Hermes runtime readiness probe."""

from __future__ import annotations

import json
import plistlib
from pathlib import Path

from scripts.ops import hermes_runtime_readiness as hrr


def _write_run_py(root: Path, *, quick_guard: bool, confirmation: bool = True) -> None:
    gateway = root / "gateway"
    gateway.mkdir(parents=True)
    chunks = ["# fake gateway"]
    if confirmation:
        chunks.extend(hrr.CONFIRMATION_REPLY_NEEDLES)
    if quick_guard:
        chunks.extend(hrr.QUICK_GUARD_NEEDLES)
    (gateway / "run.py").write_text("\n".join(chunks), encoding="utf-8")
    (root / ".git").mkdir()


def _write_plist(path: Path, *, runtime: Path, sapphire_env: bool) -> None:
    env = {"HERMES_HOME": str(path.parent)}
    if sapphire_env:
        env["SAPPHIRE_REPO_PATH"] = "/Users/example/Code/Sapphire"
    path.parent.mkdir(parents=True)
    path.write_bytes(
        plistlib.dumps(
            {
                "Label": "ai.hermes.gateway",
                "WorkingDirectory": str(runtime),
                "ProgramArguments": [
                    str(runtime / "venv" / "bin" / "python"),
                    "-m",
                    "hermes_cli.main",
                    "gateway",
                    "run",
                ],
                "EnvironmentVariables": env,
            }
        )
    )


def _runner(args: list[str], cwd: Path) -> dict:
    if args[:2] == ["git", "rev-parse"]:
        return {"ok": True, "stdout": f"{cwd.name[:8]}1234", "stderr": ""}
    if args[:3] == ["git", "branch", "--show-current"]:
        return {"ok": True, "stdout": "main", "stderr": ""}
    if args[:3] == ["git", "status", "--short"]:
        return {"ok": True, "stdout": "## main...origin/main", "stderr": ""}
    return {"ok": False, "stdout": "", "stderr": "unexpected"}


def test_runtime_pass_requires_guard_and_launchagent_sapphire_repo_env(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    dev = tmp_path / "dev"
    plist = tmp_path / "LaunchAgents" / "ai.hermes.gateway.plist"
    config = tmp_path / "config.yaml"
    _write_run_py(runtime, quick_guard=True)
    _write_run_py(dev, quick_guard=True)
    _write_plist(plist, runtime=runtime, sapphire_env=True)
    config.write_text(
        """
quick_commands:
  health:
    type: exec
    command: python -m gateway.status
""",
        encoding="utf-8",
    )

    report = hrr.collect_readiness(
        runtime_path=runtime,
        dev_path=dev,
        launchagent_plist=plist,
        config_path=config,
        runner=_runner,
    )

    assert report["status"] == "pass"
    assert report["required_runtime_controls"]["runtime_quick_exec_command_guard"] is True
    assert report["required_runtime_controls"]["launchagent_sapphire_repo_path_env"] is True


def test_dev_guard_without_runtime_guard_is_warn_and_never_prints_command_body(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    dev = tmp_path / "dev"
    plist = tmp_path / "LaunchAgents" / "ai.hermes.gateway.plist"
    config = tmp_path / "config.yaml"
    secretish_command = "launchctl kickstart gui/501/ai.hermes.gateway # token=SHOULD_NOT_RENDER"
    _write_run_py(runtime, quick_guard=False)
    _write_run_py(dev, quick_guard=True)
    _write_plist(plist, runtime=runtime, sapphire_env=False)
    config.write_text(
        f"""
quick_commands:
  restart:
    type: exec
    command: {secretish_command!r}
""",
        encoding="utf-8",
    )

    report = hrr.collect_readiness(
        runtime_path=runtime,
        dev_path=dev,
        launchagent_plist=plist,
        config_path=config,
        runner=_runner,
    )
    serialized = json.dumps(report)

    assert report["status"] == "warn"
    assert report["runtime"]["quick_exec_command_guard"] is False
    assert report["development_clone"]["quick_exec_command_guard"] is True
    assert report["quick_commands"]["production_adjacent_exec_count"] == 1
    assert "SHOULD_NOT_RENDER" not in serialized
    assert secretish_command not in hrr.render_markdown(report)


def test_missing_runtime_is_fail(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    runtime = tmp_path / "missing-runtime"
    plist = tmp_path / "LaunchAgents" / "ai.hermes.gateway.plist"
    _write_run_py(dev, quick_guard=True)
    _write_plist(plist, runtime=runtime, sapphire_env=True)

    report = hrr.collect_readiness(
        runtime_path=runtime,
        dev_path=dev,
        launchagent_plist=plist,
        config_path=tmp_path / "missing-config.yaml",
        runner=_runner,
    )

    assert report["status"] == "fail"
