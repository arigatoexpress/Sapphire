from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lib.core.provenance import sidecar_path, verify
from services.telegram_intel.history_export import (
    GENERATOR,
    discover_export_files,
    flatten_telegram_text,
    import_history_export,
)
from services.telegram_intel.run import main as telegram_intel_main

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "telegram_export" / "result.json"
ROOT = Path(__file__).resolve().parents[2]


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_discover_export_files_accepts_file_and_directory() -> None:
    assert discover_export_files(FIXTURE) == (FIXTURE,)
    assert discover_export_files(FIXTURE.parent) == (FIXTURE,)


def test_flatten_telegram_text_handles_rich_text_arrays() -> None:
    text = flatten_telegram_text(["Alpha ", {"type": "bold", "text": "decision"}, 7])
    assert text == "Alpha decision7"


def test_import_history_export_writes_sanitized_messages_and_context(tmp_path: Path) -> None:
    result = import_history_export(FIXTURE, data_dir=tmp_path / "history")

    assert result.stats.export_files == 1
    assert result.stats.chats == 1
    assert result.stats.raw_messages == 4
    assert result.stats.parsed_messages == 3
    assert result.stats.skipped_messages == 1
    assert result.stats.written_messages == 3
    assert result.stats.open_loops == 1
    assert result.stats.commitments >= 1
    assert result.stats.decisions == 1

    rows = _jsonl(result.messages_path)
    assert len(rows) == 3
    assert all(verify(row) for row in rows)
    assert rows[0]["provenance"]["generator"] == GENERATOR
    assert sidecar_path(result.messages_path).exists()

    context = json.loads(result.context_path.read_text(encoding="utf-8"))
    assert verify(context) is True
    assert context["summary"]["messages"] == 3
    assert context["summary"]["open_loops"] == 1
    assert context["summary"]["decisions"] == 1
    assert context["open_loops"][0]["canonical_id"] == rows[0]["canonical_id"]
    assert sidecar_path(result.context_path).exists()


def test_import_history_export_deduplicates_on_rerun(tmp_path: Path) -> None:
    first = import_history_export(FIXTURE, data_dir=tmp_path / "history")
    second = import_history_export(FIXTURE, data_dir=tmp_path / "history")

    assert first.stats.written_messages == 3
    assert second.stats.written_messages == 0
    assert second.stats.duplicate_messages == 3
    assert len(_jsonl(second.messages_path)) == 3


def test_import_history_export_does_not_persist_raw_private_identifiers(
    tmp_path: Path,
) -> None:
    result = import_history_export(FIXTURE, data_dir=tmp_path / "history")
    blob = result.messages_path.read_text(encoding="utf-8") + result.context_path.read_text(
        encoding="utf-8"
    )

    for raw in (
        "analyst@example.invalid",
        "202-555-0198",
        "Operator Alpha",
        "Research Partner",
        "Client Research Room",
        "@privatealpha",
        "0x1234567890abcdef1234567890abcdef12345678",
        "https://example.com",
        "result.json",
    ):
        assert raw not in blob

    assert "[redacted-email]" in blob
    assert "[redacted-phone]" in blob
    assert "[redacted-handle]" in blob
    assert "[redacted-wallet]" in blob
    assert "hxxps://example.com" in blob


def test_import_history_cli_success(tmp_path: Path, capsys) -> None:
    rc = telegram_intel_main(
        [
            "import-history",
            "--export-path",
            str(FIXTURE),
            "--data-dir",
            str(tmp_path / "history"),
        ]
    )
    captured = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert captured["ok"] is True
    assert captured["stats"]["written_messages"] == 3


def test_import_history_cli_requires_export_path(capsys) -> None:
    rc = telegram_intel_main(["import-history"])
    captured = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert captured["error"] == "--export-path is required"


def test_import_history_script_entrypoint_success(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "services" / "telegram_intel" / "run.py"),
            "import-history",
            "--export-path",
            str(FIXTURE),
            "--data-dir",
            str(tmp_path / "history"),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["stats"]["written_messages"] == 3
