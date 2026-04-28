"""Tests for the local CI verifier helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "local_ci_verify.py"

SPEC = importlib.util.spec_from_file_location("local_ci_verify", SCRIPT)
assert SPEC and SPEC.loader
local_ci_verify = importlib.util.module_from_spec(SPEC)
sys.modules["local_ci_verify"] = local_ci_verify
SPEC.loader.exec_module(local_ci_verify)


def test_changed_paths_for_secret_scan_uses_pr_and_worktree_files(tmp_path, monkeypatch) -> None:
    for rel in ("committed.py", "staged.py", "dirty.py", "new.py"):
        path = tmp_path / rel
        path.write_text("ok", encoding="utf-8")

    responses = {
        ("git", "merge-base", "HEAD", "origin/main"): "base-sha\n",
        ("git", "diff", "--name-only", "--diff-filter=ACMR", "base-sha...HEAD"): "committed.py\n",
        ("git", "diff", "--name-only", "--diff-filter=ACMR", "--cached", "HEAD"): "staged.py\n",
        ("git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"): "dirty.py\ndeleted.py\n",
        ("git", "ls-files", "--others", "--exclude-standard"): "new.py\n../escape.py\n",
    }

    monkeypatch.setattr(local_ci_verify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        local_ci_verify,
        "git_capture_optional",
        lambda cmd: responses.get(tuple(cmd), ""),
    )

    assert [path.as_posix() for path in local_ci_verify.changed_paths_for_secret_scan()] == [
        "committed.py",
        "dirty.py",
        "new.py",
        "staged.py",
    ]


def test_copy_secret_scan_source_preserves_relative_paths(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "file.py").write_text("ok", encoding="utf-8")
    out = tmp_path / "scan"

    monkeypatch.setattr(local_ci_verify, "REPO_ROOT", repo)

    copied = local_ci_verify.copy_secret_scan_source([Path("src/file.py")], out)

    assert copied == 1
    assert (out / "src" / "file.py").read_text(encoding="utf-8") == "ok"


def test_test_inventory_check_uses_readme_gate(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_run_named(name: str, cmd: list[str]) -> dict:
        calls.append((name, cmd))
        return {"name": name, "status": "PASS", "exit_code": 0}

    monkeypatch.setattr(local_ci_verify, "DEFAULT_PYTHON", "/tmp/python")
    monkeypatch.setattr(local_ci_verify, "_run_named", fake_run_named)

    result = local_ci_verify.check_test_inventory()

    assert result["status"] == "PASS"
    assert calls == [
        (
            "README test inventory",
            [
                "/tmp/python",
                "scripts/ops/test_inventory.py",
                "--check-readme",
                "--max-drift",
                "50",
            ],
        )
    ]
