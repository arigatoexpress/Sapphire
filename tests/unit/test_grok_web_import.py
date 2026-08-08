"""Golden tests for the hash-addressed Grok web import boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "ops" / "grok_web_import.py"


def _load():
    spec = importlib.util.spec_from_file_location("grok_web_import", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _frontmatter(title: str = "Clean import", body: str = "# Body\n") -> str:
    return (
        "---\n"
        "source: grok-web\n"
        "date: 2026-08-08\n"
        "type: architecture\n"
        f'title: "{title}"\n'
        "---\n\n"
        f"{body}"
    )


def _write_exports(repo: Path, files: dict[str, str | bytes]) -> None:
    export_dir = repo / "data" / "grok-web-exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = export_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")


def _fixture_repo(tmp_path: Path, files: dict[str, str | bytes]) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))
    _git(tmp_path, "init", "--initial-branch=main", str(seed))
    _git(seed, "config", "user.name", "Codex Test")
    _git(seed, "config", "user.email", "codex-test@example.invalid")
    _write_exports(seed, files)
    _git(seed, "add", "data/grok-web-exports")
    _git(seed, "commit", "-m", "fixture exports")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "main")
    _git(tmp_path, "clone", str(origin), str(work))
    return origin, seed, work


def _config(mod, tmp_path: Path, repo: Path):
    return mod.ImportConfig(
        repo=repo,
        destination=tmp_path / "Knowledge" / "0-Inbox" / "grok-web",
        state_root=tmp_path / "ops-state" / "grok-web-import",
    )


def _receipt(config, digest: str) -> dict:
    path = config.state_root / "receipts" / "sha256" / digest[:2] / f"{digest}.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    return json.loads(raw)


def test_import_reads_pinned_remote_tree_not_dirty_checkout(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_clean.md": _frontmatter(body="REMOTE\n")})
    config = _config(mod, tmp_path, repo)

    _write_exports(
        repo,
        {
            "2026-08-08_clean.md": _frontmatter(body="DIRTY\n"),
            "2026-08-08_untracked.md": _frontmatter(body="UNTRACKED\n"),
        },
    )

    result = mod.import_exports(config)

    assert (config.destination / "2026-08-08_clean.md").read_text().endswith("REMOTE\n")
    assert not (config.destination / "2026-08-08_untracked.md").exists()
    receipt = _receipt(config, result.receipt_sha256)
    assert receipt["source"]["commit_oid"] == _git(repo, "rev-parse", "origin/main^{commit}")
    assert receipt["files"][0]["git_blob_oid"]


def test_fetch_uses_exact_refspec_and_never_pull_or_checkout(tmp_path: Path, monkeypatch):
    mod = _load()
    _, seed, repo = _fixture_repo(tmp_path, {"2026-08-08_one.md": _frontmatter("One")})
    config = _config(mod, tmp_path, repo)
    _write_exports(seed, {"2026-08-08_two.md": _frontmatter("Two")})
    _git(seed, "add", "data/grok-web-exports/2026-08-08_two.md")
    _git(seed, "commit", "-m", "second export")
    _git(seed, "push", "origin", "main")

    seen: list[list[str]] = []
    real_run = mod.subprocess.run

    def recording_run(command, **kwargs):
        seen.append([str(part) for part in command])
        return real_run(command, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", recording_run)
    mod.import_exports(config, fetch=True)

    assert (config.destination / "2026-08-08_two.md").exists()
    assert [
        "git",
        "-C",
        str(repo),
        "fetch",
        "--no-tags",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
    ] in seen
    forbidden = {"pull", "merge", "checkout", "switch", "reset", "clean", "push"}
    assert not any(forbidden.intersection(command) for command in seen)


def test_fetch_failure_is_non_mutating(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_one.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)
    _git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))

    with pytest.raises(mod.ImportRejected, match="fetch_failed"):
        mod.import_exports(config, fetch=True)

    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()
    assert not list(config.state_root.glob("receipts/**/*.json"))


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        (
            "2026-08-08_bad-yaml.md",
            "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\ntitle: local-export: bad\n---\n",
            "invalid_yaml",
        ),
        ("2026-08-08_missing.md", "# no frontmatter\n", "missing_frontmatter"),
        (
            "2026-08-08_secret.md",
            _frontmatter(body="api_key: sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n"),
            "secret_detected",
        ),
        ("credentials.md", _frontmatter(), "secret_path"),
    ],
)
def test_strict_validation_rejects_before_copy(tmp_path: Path, name: str, content: str, code: str):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {name: content})
    config = _config(mod, tmp_path, repo)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == code
    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()
    serialized = "".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in config.state_root.rglob("*")
        if path.is_file()
    )
    assert "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456" not in serialized


def test_idempotent_import_adopts_identical_and_preserves_unmanaged_files(tmp_path: Path):
    mod = _load()
    content = _frontmatter(body="SAME\n")
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_same.md": content})
    config = _config(mod, tmp_path, repo)
    config.destination.mkdir(parents=True)
    managed = config.destination / "2026-08-08_same.md"
    unmanaged = config.destination / "manual-note.md"
    managed.write_text(content)
    unmanaged.write_text("manual\n")

    first = mod.import_exports(config)
    before_mtime = managed.stat().st_mtime_ns
    second = mod.import_exports(config)

    assert first.changed is True
    assert second.changed is False
    assert second.receipt_sha256 == first.receipt_sha256
    assert managed.stat().st_mtime_ns == before_mtime
    assert unmanaged.read_text() == "manual\n"
    assert len(list(config.state_root.glob("receipts/sha256/*/*.json"))) == 1


def test_unmanaged_collision_aborts_without_overwrite(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_same.md": _frontmatter(body="SOURCE\n")})
    config = _config(mod, tmp_path, repo)
    config.destination.mkdir(parents=True)
    target = config.destination / "2026-08-08_same.md"
    target.write_text("UNMANAGED\n")

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "unmanaged_collision"
    assert target.read_text() == "UNMANAGED\n"
    assert not (config.state_root / "CURRENT.json").exists()


def test_update_writes_content_addressed_blob_receipt_and_atomic_pointer(tmp_path: Path):
    mod = _load()
    _, seed, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter("One")})
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)

    _write_exports(seed, {"2026-08-08_note.md": _frontmatter("Two")})
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "update export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    second = mod.import_exports(config)

    pointer = json.loads((config.state_root / "CURRENT.json").read_text())
    receipt = _receipt(config, second.receipt_sha256)
    item = receipt["files"][0]
    blob = config.state_root / "blobs" / "sha256" / item["sha256"][:2] / item["sha256"]
    assert pointer["receipt_sha256"] == second.receipt_sha256
    assert pointer["previous_receipt_sha256"] == first.receipt_sha256
    assert item["action"] == "replaced"
    assert hashlib.sha256(blob.read_bytes()).hexdigest() == item["sha256"]
    assert (config.state_root.stat().st_mode & 0o777) == 0o700
    assert (blob.stat().st_mode & 0o777) == 0o600


def test_removed_managed_file_is_quarantined_and_rollback_restores_it(tmp_path: Path):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_keep.md": _frontmatter("Keep"),
            "2026-08-08_retire.md": _frontmatter("Retire"),
        },
    )
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    (seed / "data/grok-web-exports/2026-08-08_retire.md").unlink()
    _git(seed, "add", "data/grok-web-exports/2026-08-08_retire.md")
    _git(seed, "commit", "-m", "retire export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")

    second = mod.import_exports(config)
    second_receipt = _receipt(config, second.receipt_sha256)
    assert not (config.destination / "2026-08-08_retire.md").exists()
    assert second_receipt["retired"][0]["destination_relpath"] == "2026-08-08_retire.md"

    rollback = mod.rollback_import(config, first.receipt_sha256)
    assert (config.destination / "2026-08-08_retire.md").exists()
    assert rollback.changed is True
    rollback_receipt = _receipt(config, rollback.receipt_sha256)
    assert rollback_receipt["operation"] == "rollback"
    assert rollback_receipt["rollback_of_receipt_sha256"] == second.receipt_sha256


def test_out_of_band_edit_blocks_update_and_rollback(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    target = config.destination / "2026-08-08_note.md"
    target.write_text("OUT OF BAND\n")

    with pytest.raises(mod.ImportRejected) as update_error:
        mod.import_exports(config)
    assert update_error.value.code == "managed_drift"

    with pytest.raises(mod.ImportRejected) as rollback_error:
        mod.rollback_import(config, first.receipt_sha256)
    assert rollback_error.value.code == "managed_drift"
    assert target.read_text() == "OUT OF BAND\n"


def test_tree_boundary_rejects_nested_and_symlink_entries(tmp_path: Path):
    mod = _load()
    _, _, nested_repo = _fixture_repo(
        tmp_path / "nested",
        {"nested/2026-08-08_note.md": _frontmatter()},
    )
    with pytest.raises(mod.ImportRejected) as nested_error:
        mod.import_exports(_config(mod, tmp_path / "nested", nested_repo))
    assert nested_error.value.code == "nested_path"

    _, seed, link_repo = _fixture_repo(
        tmp_path / "link",
        {"2026-08-08_target.md": _frontmatter()},
    )
    link = seed / "data/grok-web-exports/2026-08-08_link.md"
    os.symlink("2026-08-08_target.md", link)
    _git(seed, "add", str(link.relative_to(seed)))
    _git(seed, "commit", "-m", "symlink export")
    _git(seed, "push", "origin", "main")
    _git(link_repo, "fetch", "origin", "main:refs/remotes/origin/main")
    with pytest.raises(mod.ImportRejected) as link_error:
        mod.import_exports(_config(mod, tmp_path / "link", link_repo))
    assert link_error.value.code == "forbidden_tree_entry"


def test_dry_run_and_pointer_failure_leave_current_unchanged(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)

    dry = mod.import_exports(config, dry_run=True)
    assert dry.changed is True
    assert not config.destination.exists()
    assert not config.state_root.exists()

    def fail_before_pointer(stage: str) -> None:
        if stage == "before_pointer":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        mod.import_exports(config, fault_injector=fail_before_pointer)
    assert not (config.state_root / "CURRENT.json").exists()


def test_publisher_runs_only_after_material_change(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)
    calls: list[str] = []

    mod.import_exports(config, publisher=lambda: calls.append("publish"))
    mod.import_exports(config, publisher=lambda: calls.append("publish"))

    assert calls == ["publish"]
