"""Golden tests for the hash-addressed Grok web import boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

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
        (
            "2026-08-08_bad-timestamp.md",
            "---\nsource: grok-web\ndate: 2026-99-99\ntype: note\ntitle: Bad date\n---\n",
            "invalid_yaml",
        ),
        ("2026-08-08_missing.md", "# no frontmatter\n", "missing_frontmatter"),
        (
            "2026-08-08_secret.md",
            _frontmatter(body="api_key: sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n"),
            "secret_detected",
        ),
        (
            "2026-08-08_encrypted-key.md",
            _frontmatter(body="-----BEGIN ENCRYPTED PRIVATE KEY-----\nFAKE\n"),
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


@pytest.mark.parametrize("field", ["source", "date", "type", "title"])
def test_non_scalar_provenance_is_rejected_before_copy(tmp_path: Path, field: str):
    mod = _load()
    provenance = {
        "source": "grok-web",
        "date": "2026-08-08",
        "type": "note",
        "title": "Structured provenance",
    }
    provenance[field] = []
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_bad-provenance.json": json.dumps(provenance)},
    )
    config = _config(mod, tmp_path, repo)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == f"invalid_{field}"
    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()


@pytest.mark.parametrize(
    "token",
    [
        "github_pat_11ABCDEFGHIJKLMNOP_abcdefghijklmnopqrstuvwxyz0123456789",
        "AIza" + "A" * 35,
        "ya29." + "A" * 40,
        "123456789:" + "A" * 35,
        "sk_live_" + "A" * 24,
        "rk_live_" + "A" * 24,
    ],
)
def test_bare_known_token_is_rejected_without_persisting_secret(
    tmp_path: Path,
    token: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_secret.md": _frontmatter(body=f"{token}\n")},
    )
    config = _config(mod, tmp_path, repo)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "secret_detected"
    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()
    serialized = b"".join(
        path.read_bytes() for path in config.state_root.rglob("*") if path.is_file()
    )
    assert token.encode() not in serialized


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        (
            "2026-08-08_deep.md",
            "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\n"
            'title: "Deep"\nx: ' + "[" * 600 + "0" + "]" * 600 + "\n---\n",
            "invalid_yaml",
        ),
        (
            "2026-08-08_deep.json",
            '{"source":"grok-web","date":"2026-08-08","type":"note",'
            '"title":"Deep","x":' + "[" * 1200 + "0" + "]" * 1200 + "}",
            "invalid_json",
        ),
    ],
)
def test_deeply_nested_input_is_structurally_rejected(
    tmp_path: Path,
    name: str,
    content: str,
    code: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {name: content})
    config = _config(mod, tmp_path, repo)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == code
    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()


def test_yaml_aliases_are_rejected_before_traversal_amplification(tmp_path: Path):
    mod = _load()
    content = (
        "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\n"
        'title: "Aliases"\nbase: &base [0]\naliases: [*base, *base]\n---\n'
    )
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_aliases.md": content})
    config = _config(mod, tmp_path, repo)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "invalid_yaml"
    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_constants_are_rejected(tmp_path: Path, constant: str):
    mod = _load()
    content = (
        '{"source":"grok-web","date":"2026-08-08","type":"note",'
        f'"title":"Constants","value":{constant}}}'
    )
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_constant.json": content})
    config = _config(mod, tmp_path, repo)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "invalid_json"
    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()


def test_excessive_structured_nodes_are_rejected(tmp_path: Path):
    mod = _load()
    content = json.dumps(
        {
            "source": "grok-web",
            "date": "2026-08-08",
            "type": "note",
            "title": "Wide",
            "values": [0] * 10_001,
        }
    )
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_wide.json": content})
    config = _config(mod, tmp_path, repo)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "invalid_json"
    assert not config.destination.exists()
    assert not (config.state_root / "CURRENT.json").exists()


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


def test_current_receipt_rejects_reused_state_root_with_new_destination(tmp_path: Path):
    mod = _load()
    content = _frontmatter(body="BOUND\n")
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": content})
    config = _config(mod, tmp_path, repo)
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    new_destination = tmp_path / "Knowledge" / "other-inbox"
    new_destination.mkdir(parents=True)
    new_target = new_destination / "2026-08-08_note.md"
    new_target.write_text(content)
    rebound = mod.ImportConfig(
        repo=repo,
        destination=new_destination,
        state_root=config.state_root,
    )

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(rebound)

    assert caught.value.code == "destination_mismatch"
    assert new_target.read_text() == content
    assert (config.destination / "2026-08-08_note.md").read_text() == content
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before


def test_import_preserves_existing_restrictive_destination_mode(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)
    config.destination.mkdir(parents=True)
    config.destination.chmod(0o700)

    mod.import_exports(config)

    assert stat.S_IMODE(config.destination.stat().st_mode) == 0o700


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


def test_atomic_write_uses_bounded_temporary_name_for_long_destination(tmp_path: Path):
    mod = _load()
    target = tmp_path / f"{'x' * 240}.md"

    mod._atomic_write(target, b"bounded\n", 0o600)

    assert target.read_bytes() == b"bounded\n"
    assert list(tmp_path.iterdir()) == [target]


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

    repeated = mod.import_exports(config)
    assert repeated.status == "imported"
    assert not (config.destination / "2026-08-08_retire.md").exists()

    pointer_before_failed_rollback = (config.state_root / "CURRENT.json").read_bytes()

    def fail_before_pointer(stage: str) -> None:
        if stage == "before_pointer":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        mod.rollback_import(
            config,
            first.receipt_sha256,
            fault_injector=fail_before_pointer,
        )

    assert not (config.destination / "2026-08-08_retire.md").exists()
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before_failed_rollback
    final_rollback = mod.rollback_import(config, first.receipt_sha256)
    assert final_rollback.status == "rolled_back"
    assert (config.destination / "2026-08-08_retire.md").exists()


def test_edit_during_quarantine_setup_blocks_retirement(tmp_path: Path, monkeypatch):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_keep.md": _frontmatter("Keep"),
            "2026-08-08_retire.md": _frontmatter("Retire"),
        },
    )
    config = _config(mod, tmp_path, repo)
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_retire.md"
    (seed / "data/grok-web-exports/2026-08-08_retire.md").unlink()
    _git(seed, "add", "data/grok-web-exports/2026-08-08_retire.md")
    _git(seed, "commit", "-m", "retire export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    manual_edit = _frontmatter("Manual", body="MANUAL\n").encode()
    quarantine_root = config.state_root / "quarantine"
    real_ensure_dir = mod._ensure_dir
    edited = False

    def edit_during_quarantine_setup(path, mode, **kwargs):
        nonlocal edited
        result = real_ensure_dir(path, mode, **kwargs)
        if not edited and quarantine_root in path.parents:
            target.write_bytes(manual_edit)
            edited = True
        return result

    monkeypatch.setattr(mod, "_ensure_dir", edit_during_quarantine_setup)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "managed_drift"
    assert target.read_bytes() == manual_edit
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert not list(quarantine_root.rglob("2026-08-08_retire.md"))
    assert (config.state_root / "RECOVERY.json").exists()


def test_cross_device_retirement_is_rejected_before_mutation(tmp_path: Path, monkeypatch):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_keep.md": _frontmatter("Keep"),
            "2026-08-08_retire.md": _frontmatter("Retire"),
        },
    )
    config = _config(mod, tmp_path, repo)
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_retire.md"
    target_before = target.read_bytes()
    (seed / "data/grok-web-exports/2026-08-08_retire.md").unlink()
    _git(seed, "add", "data/grok-web-exports/2026-08-08_retire.md")
    _git(seed, "commit", "-m", "retire export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")

    def different_devices(path: Path) -> int:
        return 1 if path == config.destination else 2

    monkeypatch.setattr(mod, "_device_id", different_devices, raising=False)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "cross_device_quarantine"
    assert target.read_bytes() == target_before
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert not (config.state_root / "RECOVERY.json").exists()
    assert not (config.state_root / "quarantine").exists()


def test_cross_device_rollback_retirement_is_rejected_before_mutation(
    tmp_path: Path,
    monkeypatch,
):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_keep.md": _frontmatter("Keep")},
    )
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    _write_exports(seed, {"2026-08-08_extra.md": _frontmatter("Extra")})
    _git(seed, "add", "data/grok-web-exports/2026-08-08_extra.md")
    _git(seed, "commit", "-m", "add export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_extra.md"
    target_before = target.read_bytes()

    def different_devices(path: Path) -> int:
        return 1 if path == config.destination else 2

    monkeypatch.setattr(mod, "_device_id", different_devices)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.rollback_import(config, first.receipt_sha256)

    assert caught.value.code == "cross_device_quarantine"
    assert target.read_bytes() == target_before
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert not (config.state_root / "RECOVERY.json").exists()
    assert not (config.state_root / "quarantine").exists()


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


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Note.md", "note.md"),
        ("caf\u00e9.md", "cafe\u0301.md"),
    ],
)
def test_destination_aliases_are_rejected_before_materialization(left: str, right: str):
    mod = _load()

    def candidate(name: str, digest: str):
        return mod.Candidate(
            source_relpath=f"data/grok-web-exports/{name}",
            destination_relpath=name,
            git_blob_oid="a" * 40,
            sha256=digest,
            size=1,
            media_type="text/markdown",
            data=b"x",
        )

    with pytest.raises(mod.ImportRejected) as caught:
        mod._validate_destination_aliases([candidate(left, "1" * 64), candidate(right, "2" * 64)])

    assert caught.value.code == "destination_alias"


def test_case_only_rename_of_managed_file_is_rejected_before_write(tmp_path: Path):
    mod = _load()
    original_name = "2026-08-08_Note.md"
    renamed_name = "2026-08-08_note.md"
    _, seed, repo = _fixture_repo(tmp_path, {original_name: _frontmatter()})
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    original_target = config.destination / original_name
    before = original_target.read_bytes()
    temporary_name = "2026-08-08_case-temp.md"
    _git(
        seed,
        "mv",
        f"data/grok-web-exports/{original_name}",
        f"data/grok-web-exports/{temporary_name}",
    )
    _git(
        seed,
        "mv",
        f"data/grok-web-exports/{temporary_name}",
        f"data/grok-web-exports/{renamed_name}",
    )
    _git(seed, "commit", "-m", "case-only rename")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "destination_alias_current"
    assert original_target.read_bytes() == before
    current = json.loads((config.state_root / "CURRENT.json").read_text())
    assert current["receipt_sha256"] == first.receipt_sha256


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
    assert not (config.destination / "2026-08-08_note.md").exists()


def test_pointer_failure_restores_previous_managed_state(tmp_path: Path):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_note.md": _frontmatter("Before", body="BEFORE\n")},
    )
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_note.md"
    content_before = target.read_bytes()

    _write_exports(
        seed,
        {"2026-08-08_note.md": _frontmatter("After", body="AFTER\n")},
    )
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "replace export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")

    def fail_before_pointer(stage: str) -> None:
        if stage == "before_pointer":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        mod.import_exports(config, fault_injector=fail_before_pointer)

    assert target.read_bytes() == content_before
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    retry = mod.import_exports(config)
    assert retry.status == "imported"
    assert retry.receipt_sha256 != first.receipt_sha256


def test_edit_after_planning_blocks_managed_replacement(tmp_path: Path, monkeypatch):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_note.md": _frontmatter("Before", body="BEFORE\n")},
    )
    config = _config(mod, tmp_path, repo)
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_note.md"
    _write_exports(
        seed,
        {"2026-08-08_note.md": _frontmatter("After", body="AFTER\n")},
    )
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "replace export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    manual_edit = _frontmatter("Manual", body="MANUAL\n").encode()
    real_store_blob = mod._store_blob
    edited = False

    def edit_after_plan(*args, **kwargs):
        nonlocal edited
        if not edited:
            target.write_bytes(manual_edit)
            edited = True
        return real_store_blob(*args, **kwargs)

    monkeypatch.setattr(mod, "_store_blob", edit_after_plan)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "managed_drift"
    assert target.read_bytes() == manual_edit
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert not (config.state_root / "RECOVERY.json").exists()


def test_edit_during_atomic_write_blocks_managed_replacement(tmp_path: Path, monkeypatch):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_note.md": _frontmatter("Before", body="BEFORE\n")},
    )
    config = _config(mod, tmp_path, repo)
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_note.md"
    _write_exports(
        seed,
        {"2026-08-08_note.md": _frontmatter("After", body="AFTER\n")},
    )
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "replace export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    manual_edit = _frontmatter("Manual", body="MANUAL\n").encode()
    real_atomic_write = mod._atomic_write

    def edit_before_swap(path, data, mode, **kwargs):
        if path == target:
            target.write_bytes(manual_edit)
        return real_atomic_write(path, data, mode, **kwargs)

    monkeypatch.setattr(mod, "_atomic_write", edit_before_swap)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "managed_drift"
    assert target.read_bytes() == manual_edit
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert (config.state_root / "RECOVERY.json").exists()


def test_edit_before_pointer_swap_blocks_activation(tmp_path: Path, monkeypatch):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_note.md": _frontmatter("Before", body="BEFORE\n")},
    )
    config = _config(mod, tmp_path, repo)
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_note.md"
    _write_exports(
        seed,
        {"2026-08-08_note.md": _frontmatter("After", body="AFTER\n")},
    )
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "replace export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    manual_edit = _frontmatter("Manual", body="MANUAL\n").encode()
    real_atomic_write = mod._atomic_write

    def edit_before_pointer(path, data, mode, **kwargs):
        if path == config.state_root / "CURRENT.json":
            target.write_bytes(manual_edit)
        return real_atomic_write(path, data, mode, **kwargs)

    monkeypatch.setattr(mod, "_atomic_write", edit_before_pointer)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "managed_drift"
    assert target.read_bytes() == manual_edit
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert (config.state_root / "RECOVERY.json").exists()


def test_recreated_retired_name_before_pointer_swap_blocks_activation(
    tmp_path: Path,
    monkeypatch,
):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_keep.md": _frontmatter("Keep"),
            "2026-08-08_retire.md": _frontmatter("Retire"),
        },
    )
    config = _config(mod, tmp_path, repo)
    mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    retired_target = config.destination / "2026-08-08_retire.md"
    (seed / "data/grok-web-exports/2026-08-08_retire.md").unlink()
    _git(seed, "add", "data/grok-web-exports/2026-08-08_retire.md")
    _git(seed, "commit", "-m", "retire export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    manual_edit = _frontmatter("Manual", body="MANUAL\n").encode()
    real_atomic_write = mod._atomic_write

    def recreate_before_pointer(path, data, mode, **kwargs):
        if path == config.state_root / "CURRENT.json":
            retired_target.write_bytes(manual_edit)
        return real_atomic_write(path, data, mode, **kwargs)

    monkeypatch.setattr(mod, "_atomic_write", recreate_before_pointer)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "managed_drift"
    assert retired_target.read_bytes() == manual_edit
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert (config.state_root / "RECOVERY.json").exists()


def test_recovery_journal_repairs_simulated_uncatchable_interruption(tmp_path: Path):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_note.md": _frontmatter("Before", body="BEFORE\n")},
    )
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    target = config.destination / "2026-08-08_note.md"
    before = target.read_bytes()
    _write_exports(
        seed,
        {"2026-08-08_note.md": _frontmatter("After", body="AFTER\n")},
    )
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "replace export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    replacement_commit = _git(repo, "rev-parse", "origin/main^{commit}")

    class SimulatedCrash(BaseException):
        pass

    def crash_after_materialize(stage: str) -> None:
        if stage == "after_materialize":
            raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        mod.import_exports(config, fault_injector=crash_after_materialize)

    assert target.read_bytes() != before
    assert (config.state_root / "RECOVERY.json").exists()
    current = json.loads((config.state_root / "CURRENT.json").read_text())
    assert current["receipt_sha256"] == first.receipt_sha256

    _git(repo, "update-ref", "refs/remotes/origin/main", first.source_commit)
    recovered = mod.import_exports(config)

    assert recovered.status == "unchanged"
    assert target.read_bytes() == before
    assert not (config.state_root / "RECOVERY.json").exists()
    _git(repo, "update-ref", "refs/remotes/origin/main", replacement_commit)
    retry = mod.import_exports(config)
    assert retry.status == "imported"


def test_recovery_journal_refuses_to_overwrite_post_crash_edit(tmp_path: Path):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_note.md": _frontmatter("Before", body="BEFORE\n")},
    )
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    pointer_before = (config.state_root / "CURRENT.json").read_bytes()
    target = config.destination / "2026-08-08_note.md"
    _write_exports(
        seed,
        {"2026-08-08_note.md": _frontmatter("After", body="AFTER\n")},
    )
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "replace export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")

    class SimulatedCrash(BaseException):
        pass

    def crash_after_materialize(stage: str) -> None:
        if stage == "after_materialize":
            raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        mod.import_exports(config, fault_injector=crash_after_materialize)

    manual_edit = _frontmatter("Manual", body="MANUAL\n").encode()
    target.write_bytes(manual_edit)

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(config)

    assert caught.value.code == "managed_drift"
    assert target.read_bytes() == manual_edit
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before
    assert (config.state_root / "RECOVERY.json").exists()
    current = json.loads(pointer_before)
    assert current["receipt_sha256"] == first.receipt_sha256


def test_recovery_journal_accepts_activation_completed_before_interruption(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)

    class SimulatedCrash(BaseException):
        pass

    def crash_after_pointer(stage: str) -> None:
        if stage == "after_pointer":
            raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        mod.import_exports(config, fault_injector=crash_after_pointer)

    pointer_before_recovery = (config.state_root / "CURRENT.json").read_bytes()
    target_before_recovery = (config.destination / "2026-08-08_note.md").read_bytes()
    assert (config.state_root / "RECOVERY.json").exists()

    recovered = mod.import_exports(config)

    assert recovered.status == "unchanged"
    assert not (config.state_root / "RECOVERY.json").exists()
    assert (config.state_root / "CURRENT.json").read_bytes() == pointer_before_recovery
    assert (config.destination / "2026-08-08_note.md").read_bytes() == target_before_recovery


def test_recovery_journal_rejects_retry_with_different_destination(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)

    class SimulatedCrash(BaseException):
        pass

    def crash_after_materialize(stage: str) -> None:
        if stage == "after_materialize":
            raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        mod.import_exports(config, fault_injector=crash_after_materialize)

    original_target = config.destination / "2026-08-08_note.md"
    original_bytes = original_target.read_bytes()
    rebound = mod.ImportConfig(
        repo=repo,
        destination=tmp_path / "Knowledge" / "other-inbox",
        state_root=config.state_root,
    )

    with pytest.raises(mod.ImportRejected) as caught:
        mod.import_exports(rebound)

    assert caught.value.code == "recovery_destination_mismatch"
    assert original_target.read_bytes() == original_bytes
    assert not rebound.destination.exists()
    assert (config.state_root / "RECOVERY.json").exists()
    assert not (config.state_root / "CURRENT.json").exists()


def test_publisher_runs_only_after_material_change(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)
    calls: list[str] = []

    mod.import_exports(config, publisher=lambda: calls.append("publish"))
    mod.import_exports(config, publisher=lambda: calls.append("publish"))

    assert calls == ["publish"]


def test_failed_publisher_retries_for_unchanged_receipt(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    config = _config(mod, tmp_path, repo)
    calls: list[str] = []

    def flaky_publisher() -> None:
        calls.append("publish")
        if len(calls) == 1:
            raise mod.ImportRejected("publisher_failed")

    with pytest.raises(mod.ImportRejected, match="publisher_failed"):
        mod.import_exports(config, publisher=flaky_publisher)

    pointer = json.loads((config.state_root / "CURRENT.json").read_text())
    receipt_sha = pointer["receipt_sha256"]
    result = mod.import_exports(config, publisher=flaky_publisher)
    mod.import_exports(config, publisher=flaky_publisher)

    assert result.status == "unchanged"
    assert result.receipt_sha256 == receipt_sha
    assert calls == ["publish", "publish"]


def test_failed_rollback_publisher_retries_for_activated_receipt(tmp_path: Path):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_note.md": _frontmatter("Before")},
    )
    config = _config(mod, tmp_path, repo)
    first = mod.import_exports(config)
    _write_exports(seed, {"2026-08-08_note.md": _frontmatter("After")})
    _git(seed, "add", "data/grok-web-exports/2026-08-08_note.md")
    _git(seed, "commit", "-m", "replace export")
    _git(seed, "push", "origin", "main")
    _git(repo, "fetch", "origin", "main:refs/remotes/origin/main")
    mod.import_exports(config)
    calls: list[str] = []

    def flaky_publisher() -> None:
        calls.append("publish")
        if len(calls) == 1:
            raise mod.ImportRejected("publisher_failed")

    with pytest.raises(mod.ImportRejected, match="publisher_failed"):
        mod.rollback_import(config, first.receipt_sha256, publisher=flaky_publisher)

    current = json.loads((config.state_root / "CURRENT.json").read_text())
    activated_receipt_sha = current["receipt_sha256"]
    result = mod.rollback_import(config, first.receipt_sha256, publisher=flaky_publisher)
    mod.rollback_import(config, first.receipt_sha256, publisher=flaky_publisher)

    assert result.status == "unchanged"
    assert result.receipt_sha256 == activated_receipt_sha
    assert calls == ["publish", "publish"]


def test_missing_operator_publisher_is_retryable(tmp_path: Path):
    mod = _load()

    with pytest.raises(mod.ImportRejected) as caught:
        mod._publish_operator_feeds(tmp_path / "missing-publisher.py")

    assert caught.value.code == "publisher_unavailable"


def test_live_importer_declares_yaml_runtime_dependency():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pyyaml==6.0.3" in [
        dependency.casefold() for dependency in metadata["project"]["dependencies"]
    ]


def test_importer_is_registered_with_operational_consumers():
    registry = yaml.safe_load((ROOT / "infra" / "tool-registry.yaml").read_text())
    entry = next(
        (item for item in registry["tools"] if item.get("name") == "grok_web_import"),
        None,
    )

    assert entry is not None
    assert entry["path"] == "scripts/ops/grok_web_import.py"
    assert entry["status"] == "internal"
    assert entry["owner"] == "sapphire"
    assert {
        "launchagent.com.sapphire.grok-web-bridge",
        "ops-state.finish-line.sync-grok-web-exports",
    }.issubset(entry["consumers"])


def test_shell_wrapper_resolves_python_from_path(tmp_path: Path):
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_note.md": _frontmatter()})
    fake_bin = tmp_path / "fake bin"
    fake_bin.mkdir()
    marker = tmp_path / "python-invoked"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        f'#!/bin/sh\n: > "{marker}"\nexec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env.pop("GROK_IMPORT_PYTHON", None)
    env["PATH"] = f"{fake_bin}:/opt/homebrew/bin:/usr/bin:/bin"
    legacy_destination = tmp_path / "legacy-destination"
    legacy_log_dir = tmp_path / "legacy-logs"
    env["SAPPHIRE_DIR"] = str(repo)
    env["KNOWLEDGE_INBOX"] = str(legacy_destination)
    env["SAPPHIRE_BRIDGE_LOG_DIR"] = str(legacy_log_dir)
    env["HOME"] = str(tmp_path / "home")

    subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/ops/sync_grok_web_exports.sh"),
            "--no-publish",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert marker.exists()
    assert (legacy_destination / "2026-08-08_note.md").exists()
    destination_key = hashlib.sha256(str(legacy_destination.absolute()).encode()).hexdigest()
    derived_state = (
        Path(env["HOME"]) / "ops-state" / "grok-web-import" / "by-destination" / destination_key
    )
    assert (derived_state / "CURRENT.json").exists()
    bridge_log = legacy_log_dir / "grok-web-bridge.log"
    assert '"ok": true' in bridge_log.read_text(encoding="utf-8")
