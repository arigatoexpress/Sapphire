"""Guardrails for version-controlled LaunchAgent definitions."""

from __future__ import annotations

import plistlib
from pathlib import Path

from services.pipeline import check_routines

ROOT = Path(__file__).resolve().parents[2]
INFRA_LAUNCHAGENTS = ROOT / "infra" / "launchagents"
SERVICE_LAUNCHAGENT_DIRS = tuple((ROOT / "services").glob("*/launchagent"))


def _plist_paths() -> list[Path]:
    paths = list(INFRA_LAUNCHAGENTS.glob("*.plist"))
    for directory in SERVICE_LAUNCHAGENT_DIRS:
        paths.extend(directory.glob("*.plist"))
    return sorted(paths)


def _load_plist(path: Path) -> dict:
    with path.open("rb") as handle:
        return plistlib.load(handle)


def test_launchagent_plists_parse_and_have_unique_labels() -> None:
    labels: dict[str, Path] = {}

    for path in _plist_paths():
        plist = _load_plist(path)
        label = plist.get("Label")
        assert label, f"{path} is missing Label"
        assert label not in labels, f"{path} duplicates {label} from {labels[label]}"
        labels[label] = path


def test_launchagents_do_not_target_stale_worktrees() -> None:
    for path in _plist_paths():
        plist = _load_plist(path)
        working_directory = plist.get("WorkingDirectory")
        assert working_directory is None or "/Code/_worktrees/" not in working_directory, (
            f"{path} points WorkingDirectory at stale worktree {working_directory!r}"
        )


def test_daily_brief_has_one_versioned_launchagent() -> None:
    matches: list[tuple[str, Path]] = []
    for path in _plist_paths():
        plist = _load_plist(path)
        arguments = plist.get("ProgramArguments") or []
        if any(str(arg).endswith("services/intelligence/daily_brief.py") for arg in arguments):
            matches.append((plist.get("Label", ""), path))

    assert matches == [
        ("com.sapphire.morning-brief", INFRA_LAUNCHAGENTS / "com.sapphire.morning-brief.plist")
    ]


def test_routine_health_tracks_canonical_morning_brief() -> None:
    launchagents = {routine.launchagent for routine in check_routines.ROUTINES}
    routine_names = {routine.name for routine in check_routines.ROUTINES}

    assert "com.sapphire.morning-brief" in launchagents
    assert "morning-brief" in routine_names
    assert "com.sapphire.daily-brief" not in launchagents
    assert "daily-brief" not in routine_names


def test_content_publisher_keeps_telegram_summary_explicit() -> None:
    plist = _load_plist(INFRA_LAUNCHAGENTS / "com.sapphire.content-publisher.plist")
    env = plist["EnvironmentVariables"]

    assert env["SAPPHIRE_PUBLISH_LIVE"] == "0"
    assert env["SAPPHIRE_CONTENT_TELEGRAM_SUMMARY"] == "1"
