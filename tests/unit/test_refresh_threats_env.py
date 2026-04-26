"""Tests for the threat-refresh LaunchAgent wrapper."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

from services.dashboard import refresh_threats


def test_refresh_threats_uses_env_overrides_and_path_resolution(tmp_path, monkeypatch):
    bot = tmp_path / "threat-bot"
    _write_executable(
        bot,
        """
import json
print(json.dumps([{
    "canonical_id": "CVE-2026-0001",
    "source": "nvd",
    "source_type": "cve",
    "title": "Synthetic CVE",
    "url": "https://example.invalid/CVE-2026-0001",
    "published_at": "2026-04-25T00:00:00Z",
    "summary": "Synthetic threat",
    "score": 9.1,
    "exploited": False,
    "tags": ["synthetic"],
    "evidence": []
}]))
""",
    )
    data_dir = tmp_path / "intel"
    monkeypatch.setenv("PATH", f"{tmp_path}:{Path('/usr/bin')}")
    monkeypatch.setenv("SAPPHIRE_THREATS_BOT_BIN", "threat-bot")
    monkeypatch.setenv("SAPPHIRE_THREATS_DATA_DIR", str(data_dir))

    assert refresh_threats.main() == 0

    artifacts = [path for path in data_dir.glob("*/threats.json") if "latest" not in path.parts]
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text())
    assert payload["source_count"] == 1
    assert payload["threats"][0]["canonical_id"] == "CVE-2026-0001"
    latest = data_dir / "latest"
    assert latest.is_symlink()


def test_refresh_threats_rejects_invalid_json_without_artifact(tmp_path, monkeypatch):
    bot = tmp_path / "bad-threat-bot"
    _write_executable(bot, "print('not-json')")
    data_dir = tmp_path / "intel"
    monkeypatch.setenv("SAPPHIRE_THREATS_BOT_BIN", str(bot))
    monkeypatch.setenv("SAPPHIRE_THREATS_DATA_DIR", str(data_dir))

    assert refresh_threats.main() == 1
    assert not list(data_dir.glob("*/threats.json"))


def test_refresh_threats_native_mode_writes_artifact(tmp_path, monkeypatch):
    data_dir = tmp_path / "intel"
    monkeypatch.setenv("SAPPHIRE_THREATS_BOT_BIN", "native")
    monkeypatch.setenv("SAPPHIRE_THREATS_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        refresh_threats,
        "_collect_native_public_threats",
        lambda *, days, per_source: [{"canonical_id": "CVE-2026-0002"}],
    )

    assert refresh_threats.main() == 0
    artifact = next(path for path in data_dir.glob("*/threats.json") if "latest" not in path.parts)
    payload = json.loads(artifact.read_text())
    assert payload["threats"] == [{"canonical_id": "CVE-2026-0002"}]


def test_refresh_threats_reports_missing_bot(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "missing-threat-bot"
    monkeypatch.setenv("SAPPHIRE_THREATS_BOT_BIN", str(missing))
    monkeypatch.setenv("SAPPHIRE_THREATS_DATA_DIR", str(tmp_path / "intel"))

    assert refresh_threats.main() == 1
    assert "threat-bot not found" in capsys.readouterr().err


def _write_executable(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n{body.strip()}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
