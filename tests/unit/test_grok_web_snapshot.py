"""Goldens for the immutable Grok web snapshot boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path, PureWindowsPath

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "ops" / "grok_web_snapshot.py"
SCHEMA_PATH = ROOT / "projects" / "grok" / "schemas" / "grok-web-snapshot-v1.schema.json"


def _load():
    spec = importlib.util.spec_from_file_location("grok_web_snapshot", MOD_PATH)
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


def _frontmatter(title: str = "Validated snapshot", body: str = "# Body\n") -> str:
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


def _config(mod, repo: Path):
    return mod.SnapshotConfig(repo=repo)


def test_snapshot_reads_pinned_remote_tree_not_dirty_checkout(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_clean.md": _frontmatter(body="REMOTE\n")},
    )
    _write_exports(
        repo,
        {
            "2026-08-08_clean.md": _frontmatter(body="DIRTY\n"),
            "2026-08-08_untracked.md": _frontmatter(body="UNTRACKED\n"),
        },
    )

    result = mod.snapshot_exports(_config(mod, repo))

    assert result.source_commit == _git(repo, "rev-parse", "origin/main^{commit}")
    assert [item["source_relpath"] for item in result.receipt["files"]] == [
        "data/grok-web-exports/2026-08-08_clean.md"
    ]
    assert (
        result.receipt["files"][0]["sha256"]
        == hashlib.sha256(_frontmatter(body="REMOTE\n").encode()).hexdigest()
    )
    assert "DIRTY" not in json.dumps(result.receipt)


def test_snapshot_ignores_local_git_blob_replacement_refs(tmp_path: Path):
    mod = _load()
    original = _frontmatter(body="ORIGINAL\n")
    replacement = _frontmatter(body="REPLACED\n")
    assert len(original.encode()) == len(replacement.encode())
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_clean.md": original},
    )
    original_oid = _git(
        repo,
        "rev-parse",
        "origin/main:data/grok-web-exports/2026-08-08_clean.md",
    )
    replacement_path = repo / "replacement.tmp"
    replacement_path.write_text(replacement, encoding="utf-8")
    replacement_oid = _git(repo, "hash-object", "-w", str(replacement_path))
    _git(repo, "replace", original_oid, replacement_oid)

    result = mod.snapshot_exports(_config(mod, repo))

    assert result.receipt["files"][0]["git_blob_oid"] == original_oid
    assert result.receipt["files"][0]["sha256"] == hashlib.sha256(original.encode()).hexdigest()


def test_fetch_uses_exact_refspec_and_never_pull_or_checkout(tmp_path: Path, monkeypatch):
    mod = _load()
    _, seed, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_one.md": _frontmatter("One")},
    )
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
    fetch_head = repo / ".git" / "FETCH_HEAD"
    fetch_head.write_text("operator-owned\n", encoding="utf-8")
    result = mod.snapshot_exports(_config(mod, repo), fetch=True)

    assert result.receipt["summary"]["files"] == 2
    assert fetch_head.read_text(encoding="utf-8") == "operator-owned\n"
    assert [
        "git",
        "--no-replace-objects",
        "-C",
        str(repo),
        "fetch",
        "--no-tags",
        "--no-write-fetch-head",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
    ] in seen
    forbidden = {"pull", "merge", "checkout", "switch", "reset", "clean", "push"}
    assert not any(forbidden.intersection(command) for command in seen)


@pytest.mark.parametrize(
    "overrides",
    [
        {"remote": "upstream"},
        {"source_ref": "refs/remotes/origin/dev"},
        {"source_prefix": "data/other"},
    ],
)
def test_source_contract_is_fixed_to_origin_main_exports(
    tmp_path: Path,
    overrides: dict[str, str],
):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_clean.md": _frontmatter()},
    )
    config = mod.SnapshotConfig(repo=repo, **overrides)

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(config)

    assert caught.value.code == "source_contract"


def test_tree_row_parser_rejects_unconsumed_trailing_newline(
    tmp_path: Path,
    monkeypatch,
):
    mod = _load()
    oid = "a" * 40
    raw_row = (f"100644 blob {oid} 1\tdata/grok-web-exports/2026-08-08_bad.md\n\0").encode()

    monkeypatch.setattr(mod, "_run_git", lambda *_args, **_kwargs: raw_row)

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod._tree_entries(mod.SnapshotConfig(repo=tmp_path), oid)

    assert caught.value.code == "invalid_tree_row"


def test_receipt_is_deterministic_content_addressed_and_has_no_projection_state(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_clean.md": _frontmatter()},
    )

    first = mod.snapshot_exports(_config(mod, repo))
    second = mod.snapshot_exports(_config(mod, repo))

    assert first.receipt == second.receipt
    assert first.receipt_sha256 == second.receipt_sha256
    assert hashlib.sha256(mod.canonical_receipt(first.receipt)).hexdigest() == first.receipt_sha256
    assert set(first.receipt) == {
        "schema",
        "validator",
        "source",
        "content_manifest_sha256",
        "files",
        "summary",
    }
    serialized = json.dumps(first.receipt).casefold()
    assert "destination" not in serialized
    assert "current" not in serialized
    assert "rollback" not in serialized
    assert "publisher" not in serialized


def test_snapshot_cli_emits_the_content_addressed_receipt(capsys, tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_clean.md": _frontmatter()},
    )

    exit_code = mod.main(["--repo", str(repo)])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0
    assert output.err == ""
    assert payload["ok"] is True
    assert payload["receipt"]["schema"] == mod.SCHEMA_NAME
    assert (
        hashlib.sha256(mod.canonical_receipt(payload["receipt"])).hexdigest()
        == payload["receipt_sha256"]
    )
    assert not (tmp_path / "receipts").exists()


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
        ("credentials.md", _frontmatter(), "secret_path"),
        ("nested/note.md", _frontmatter(), "nested_path"),
    ],
)
def test_strict_rejection_never_writes_state(
    tmp_path: Path,
    name: str,
    content: str,
    code: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {name: content})
    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == code
    assert not (tmp_path / "receipts").exists()


def test_backslash_git_path_is_rejected_consistently(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"folder\\credentials.md": _frontmatter()},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "nested_path"


def test_git_filename_semantics_stay_posix_when_host_path_rules_are_windows(
    tmp_path: Path,
    monkeypatch,
):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"C:credentials.md": _frontmatter()},
    )
    monkeypatch.setattr(mod, "Path", PureWindowsPath)

    result = mod.snapshot_exports(_config(mod, repo))

    assert result.receipt["files"][0]["source_relpath"].endswith("C:credentials.md")


def test_excluded_metadata_is_still_scanned_for_secrets(tmp_path: Path):
    mod = _load()
    label = "AWS_" + "SECRET_ACCESS_KEY"
    _, _, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_clean.md": _frontmatter(),
            "README.md": f"{label}={'A' * 40}\n",
        },
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert caught.value.path == "README.md"


def test_excluded_metadata_is_still_subject_to_byte_limits(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_clean.md": _frontmatter(),
            "README.md": "metadata\n" * 100,
        },
    )
    config = mod.SnapshotConfig(repo=repo, max_file_bytes=512)

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(config)

    assert caught.value.code == "file_too_large"
    assert caught.value.path == "README.md"


@pytest.mark.parametrize("field", ["source", "date", "type", "title"])
def test_non_scalar_provenance_is_rejected(tmp_path: Path, field: str):
    mod = _load()
    payload: dict[str, object] = {
        "source": "grok-web",
        "date": "2026-08-08",
        "type": "note",
        "title": "Provenance",
    }
    payload[field] = []
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_bad.json": json.dumps(payload)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == f"invalid_{field}"


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        (
            "2026-08-08_alias.md",
            "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\ntitle: Alias\n"
            "left: &shared [1, 2]\nright: *shared\n---\n",
            "invalid_yaml",
        ),
        (
            "2026-08-08_constant.json",
            '{"source":"grok-web","date":"2026-08-08","type":"note",'
            '"title":"Constant","value":NaN}',
            "invalid_json",
        ),
        (
            "2026-08-08_nodes.json",
            json.dumps(
                {
                    "source": "grok-web",
                    "date": "2026-08-08",
                    "type": "note",
                    "title": "Nodes",
                    "values": list(range(10_001)),
                }
            ),
            "invalid_json",
        ),
    ],
)
def test_structured_parsers_are_bounded(
    tmp_path: Path,
    name: str,
    content: str,
    code: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {name: content})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == code


@pytest.mark.parametrize(
    "label", ["AWS_SECRET_ACCESS_KEY", "aws_secret_key", "secret", "secretKey"]
)
def test_secret_assignments_are_rejected_without_writes(tmp_path: Path, label: str):
    mod = _load()
    token = "AbCdEf01" * 5
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_secret.md": _frontmatter(body=f"{label}: {token}\n")},
    )
    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


@pytest.mark.parametrize("label", ["mnemonic", "seed_phrase", "recoveryPhrase"])
def test_mnemonic_assignments_are_rejected_without_writes(tmp_path: Path, label: str):
    mod = _load()
    words = " ".join(["abandon"] * 11 + ["about"])
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_mnemonic.md": _frontmatter(body=f"{label}: {words}\n")},
    )
    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


@pytest.mark.parametrize(
    "key",
    [
        "privateKey",
        "secretKey",
        "mnemonic",
        "seedPhrase",
        "recovery_phrase",
        "refreshToken",
    ],
)
def test_structured_secret_keys_reject_scalar_or_container_without_writes(
    tmp_path: Path,
    key: str,
):
    mod = _load()
    payload = {
        "source": "grok-web",
        "date": "2026-08-08",
        "type": "note",
        "title": "Structured secret",
        key: list(range(64)),
    }
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_structured.json": json.dumps(payload)},
    )
    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "structured_secret_key"
    assert not (tmp_path / "receipts").exists()


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "accessToken",
        "client-secret",
        "password",
        "secret",
        "aws_secret_key",
        "AWS_SECRET_ACCESS_KEY",
        "refresh_token",
    ],
)
def test_quoted_json_generic_credential_keys_are_rejected(tmp_path: Path, key: str):
    mod = _load()
    payload = {
        "source": "grok-web",
        "date": "2026-08-08",
        "type": "note",
        "title": "Quoted credential",
        key: "AbCdEf01" * 5,
    }
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_quoted.json": json.dumps(payload)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"


def test_folded_yaml_generic_credential_key_is_rejected(tmp_path: Path):
    mod = _load()
    content = (
        "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\n"
        "title: Folded credential\npassword: >-\n  AbCdEf01AbCdEf01AbCdEf01\n"
        "---\n"
    )
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_folded.md": content})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "structured_secret_key"


@pytest.mark.parametrize("suffix", ["json", "md"])
def test_decoded_escaped_scalar_secrets_are_rejected(tmp_path: Path, suffix: str):
    mod = _load()
    encoded_token = "sk-" + "proj-" + "AAAA" + r"\u0041" + "A" * 20
    if suffix == "json":
        content = (
            '{"source":"grok-web","date":"2026-08-08","type":"note",'
            f'"title":"Escaped scalar","note":"{encoded_token}"}}'
        )
    else:
        content = (
            "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\n"
            f'title: Escaped scalar\nnote: "{encoded_token}"\n---\n'
        )
    _, _, repo = _fixture_repo(tmp_path, {f"2026-08-08_escaped.{suffix}": content})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"


def test_duplicate_json_keys_cannot_hide_a_decoded_secret(tmp_path: Path):
    mod = _load()
    encoded_token = "sk" + r"\u002d" + "proj-" + "A" * 24
    content = (
        '{"source":"grok-web","date":"2026-08-08","type":"note",'
        f'"title":"Duplicate","note":"{encoded_token}","note":"safe"}}'
    )
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_duplicate.json": content})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "invalid_json"
    assert not (tmp_path / "receipts").exists()


def test_duplicate_yaml_keys_cannot_hide_a_decoded_secret(tmp_path: Path):
    mod = _load()
    encoded_token = "sk" + r"\u002d" + "proj-" + "A" * 24
    content = (
        "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\n"
        f'title: Duplicate\nnote: "{encoded_token}"\nnote: safe\n---\n'
    )
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_duplicate.md": content})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "invalid_yaml"
    assert not (tmp_path / "receipts").exists()


def test_quoted_credential_label_in_markdown_body_is_rejected(tmp_path: Path):
    mod = _load()
    token = "AbCdEf01" * 5
    body = '```json\n{"api_key": "' + token + '"}\n```\n'
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_body.md": _frontmatter(body=body)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"


def test_escaped_credential_label_in_markdown_json_body_is_rejected_without_writes(
    tmp_path: Path,
):
    mod = _load()
    token = "AbCdEf01" * 5
    body = '```json\n{"api\\u005fkey": "' + token + '"}\n```\n'
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_escaped-label.md": _frontmatter(body=body)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


def test_escaped_solidus_in_markdown_json_secret_is_rejected_without_writes(
    tmp_path: Path,
):
    mod = _load()
    body = '```json\n{"api_key": "AbCdEf01AbCdEf01\\/AbCdEf01AbCdEf01"}\n```\n'
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_escaped-solidus.md": _frontmatter(body=body)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


def test_punctuated_quoted_password_in_markdown_body_is_rejected_without_writes(
    tmp_path: Path,
):
    mod = _load()
    password = "Abcd!Efgh@Ijkl#Mnop$Qrst%Uvwx"
    body = f'```json\n{{"password": "{password}"}}\n```\n'
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_punctuated.md": _frontmatter(body=body)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


@pytest.mark.parametrize(
    "password",
    ["Abcd!Efgh@Ijkl#Mnop$Qrst%Uvwx", "shortsecret"],
)
def test_unquoted_password_in_markdown_body_is_rejected_without_writes(
    tmp_path: Path,
    password: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_punctuated.md": _frontmatter(body=f"password: {password}\n")},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


@pytest.mark.parametrize("prefix", ["", "  <redacted>\n", "  ${PASSWORD}\n"])
def test_multiline_yaml_password_in_markdown_body_is_rejected_without_writes(
    tmp_path: Path,
    prefix: str,
):
    mod = _load()
    password = "Abcd!Efgh@Ijkl#Mnop$Qrst%Uvwx"
    body = f"```yaml\npassword: >\n{prefix}  {password}\n```\n"
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_multiline.md": _frontmatter(body=body)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


@pytest.mark.parametrize(
    "body",
    [
        '```json\n{"password":["Abcd!Efgh@Ijkl#Mnop$Qrst%Uvwx"]}\n```\n',
        "```yaml\npassword:\n  - Abcd!Efgh@Ijkl#Mnop$Qrst%Uvwx\n```\n",
    ],
)
def test_container_or_continuation_credentials_in_markdown_body_are_rejected(
    tmp_path: Path,
    body: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_container.md": _frontmatter(body=body)},
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


def test_redacted_quoted_credential_in_markdown_body_remains_allowed(tmp_path: Path):
    mod = _load()
    body = '```json\n{"api_key": "<redacted>"}\n```\n'
    _, _, repo = _fixture_repo(
        tmp_path,
        {"2026-08-08_redacted.md": _frontmatter(body=body)},
    )

    result = mod.snapshot_exports(_config(mod, repo))

    assert result.receipt["summary"]["files"] == 1


def test_unsupported_yaml_set_container_is_rejected(tmp_path: Path):
    mod = _load()
    encoded_token = "sk-" + "proj-" + "AAAA" + r"\u0041" + "A" * 20
    content = (
        "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\n"
        f'title: Set\npayload: !!set {{"{encoded_token}": null}}\n---\n'
    )
    _, _, repo = _fixture_repo(tmp_path, {"2026-08-08_set.md": content})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "invalid_yaml"


@pytest.mark.parametrize(
    ("suffix", "content", "code"),
    [
        (
            "json",
            '{"source":"grok-web","date":"2026-08-08","type":"note",'
            '"title":"Surrogate","note":"\\ud800"}',
            "invalid_json",
        ),
        (
            "md",
            "---\nsource: grok-web\ndate: 2026-08-08\ntype: note\n"
            'title: Surrogate\nnote: "\\uD800"\n---\n',
            "invalid_yaml",
        ),
    ],
)
def test_unpaired_surrogate_is_a_stable_content_rejection(
    capsys,
    tmp_path: Path,
    suffix: str,
    content: str,
    code: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {f"2026-08-08_surrogate.{suffix}": content})

    exit_code = mod.main(["--repo", str(repo)])
    output = capsys.readouterr()

    assert exit_code == 2
    assert output.out == ""
    assert json.loads(output.err)["error"] == code
    assert "Traceback" not in output.err


@pytest.mark.parametrize(
    ("name", "content"),
    [
        (
            "2026-08-08_bad-date.json",
            json.dumps(
                {
                    "source": "grok-web",
                    "date": "not-a-date",
                    "type": "note",
                    "title": "Bad date",
                }
            ),
        ),
        (
            "2026-08-08_bad-date.md",
            "---\nsource: grok-web\ndate: '2026-99-99'\ntype: note\ntitle: Bad date\n---\n",
        ),
    ],
)
def test_string_provenance_dates_must_be_valid_iso_dates(
    tmp_path: Path,
    name: str,
    content: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {name: content})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "invalid_date"


def test_inventory_rejects_an_empty_export_tree(tmp_path: Path):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {"README.md": "metadata only\n"})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.inventory_exports(_config(mod, repo))

    assert caught.value.code == "empty_source"


def test_content_blind_inventory_reports_paths_and_codes_only(tmp_path: Path):
    mod = _load()
    token = "AbCdEf01" * 5
    _, _, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_clean.md": _frontmatter("Clean"),
            "2026-08-08_secret.md": _frontmatter(body=f"secret_key: {token}\n"),
        },
    )

    inventory = mod.inventory_exports(_config(mod, repo))
    serialized = json.dumps(asdict(inventory), sort_keys=True)

    assert inventory.total == 2
    assert inventory.accepted == 1
    assert inventory.rejected == [
        mod.Rejection(path="2026-08-08_secret.md", code="secret_detected")
    ]
    assert token not in serialized
    assert "sha256" not in serialized
    assert "git_blob_oid" not in serialized


@pytest.mark.parametrize(
    "secret_name",
    [
        "sk-proj-" + "A" * 24 + ".md",
        "sk-proj-" + "A" * 24 + ".txt",
        "nested/sk-proj-" + "A" * 24 + ".md",
    ],
)
def test_secret_shaped_filename_is_rejected_and_redacted_from_inventory(
    tmp_path: Path,
    secret_name: str,
):
    mod = _load()
    _, _, repo = _fixture_repo(tmp_path, {secret_name: _frontmatter()})

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_path"
    assert caught.value.path is None
    inventory = mod.inventory_exports(_config(mod, repo))
    serialized = json.dumps(asdict(inventory), sort_keys=True)
    assert secret_name not in serialized
    assert inventory.rejected == [mod.Rejection(path="[secret-path-redacted]", code="secret_path")]


def test_escaped_secret_in_gitkeep_metadata_is_rejected_without_writes(tmp_path: Path):
    mod = _load()
    encoded_token = "sk" + r"\u002d" + "proj-" + "A" * 24
    _, _, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_clean.md": _frontmatter(),
            ".gitkeep": encoded_token,
        },
    )

    with pytest.raises(mod.SnapshotRejected) as caught:
        mod.snapshot_exports(_config(mod, repo))

    assert caught.value.code == "secret_detected"
    assert not (tmp_path / "receipts").exists()


def test_inventory_cli_fails_closed_without_writing(capsys, tmp_path: Path):
    mod = _load()
    token = "AbCdEf01" * 5
    _, _, repo = _fixture_repo(
        tmp_path,
        {
            "2026-08-08_clean.md": _frontmatter("Clean"),
            "2026-08-08_secret.md": _frontmatter(body=f"secret_key: {token}\n"),
        },
    )

    exit_code = mod.main(["--repo", str(repo), "--inventory"])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 3
    assert payload["ok"] is False
    assert payload["accepted"] == 1
    assert payload["rejected"] == [{"path": "2026-08-08_secret.md", "code": "secret_detected"}]
    assert token not in output.out
    assert output.err == ""


def test_policy_and_schema_bind_secret_rules_and_runtime_revisions():
    mod = _load()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    rule_ids = [rule["id"] for rule in mod.POLICY["secret_policy"]["rules"]]
    text_rule_ids = [rule["id"] for rule in mod.POLICY["secret_policy"]["unstructured_text_rules"]]
    assert "mnemonic_assignment" in rule_ids
    assert "aws_secret_assignment" in rule_ids
    assert "quoted_credential_assignment" in rule_ids
    assert "unquoted_credential_assignment" in rule_ids
    assert "yaml_block_credential_assignment" in text_rule_ids
    assert "credential_container_assignment" in text_rule_ids
    assert mod.POLICY["json_duplicate_keys"] == "reject"
    assert mod.POLICY["yaml_duplicate_keys"] == "reject"
    assert mod.POLICY["secret_policy"]["decode_transforms"] == [
        "markdown_body_json_escape_view_v1",
        "excluded_text_json_escape_view_v1",
    ]
    assert mod.POLICY["secret_policy"]["scan_filenames"] is True
    assert mod.POLICY["secret_policy"]["inventory_path_redaction"] == mod.SECRET_PATH_REDACTION
    assert mod.POLICY["secret_policy"]["structured_key_names"] == [
        "accesstoken",
        "apikey",
        "awssecretaccesskey",
        "awssecretkey",
        "clientsecret",
        "mnemonic",
        "password",
        "privatekey",
        "recoveryphrase",
        "secret",
        "secretkey",
        "seedphrase",
    ]
    assert mod.POLICY["secret_policy"]["structured_key_suffixes"] == [
        "accesskey",
        "accesstoken",
        "apikey",
        "authtoken",
        "bearertoken",
        "bottoken",
        "clientsecret",
        "credential",
        "credentials",
        "idtoken",
        "mnemonic",
        "password",
        "privatekey",
        "recoveryphrase",
        "refreshtoken",
        "secret",
        "secretkey",
        "seedphrase",
        "sessiontoken",
    ]
    validator_schema = schema["properties"]["validator"]["properties"]
    file_schema = schema["$defs"]["file"]["properties"]
    assert validator_schema["version"]["const"] == mod.VALIDATOR_VERSION
    assert file_schema["validation_profile"]["const"] == mod.VALIDATION_PROFILE


def test_receipt_schema_accepts_only_sha1_or_sha256_git_oid_lengths():
    mod = _load()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    pattern = schema["$defs"]["gitOid"]["pattern"]

    assert re.fullmatch(pattern, "a" * 40)
    assert re.fullmatch(pattern, "b" * 64)
    assert mod.GIT_OID_RE.fullmatch("a" * 40)
    assert mod.GIT_OID_RE.fullmatch("b" * 64)
    for length in (39, 41, 63, 65):
        assert re.fullmatch(pattern, "c" * length) is None
        assert mod.GIT_OID_RE.fullmatch("c" * length) is None


def test_cli_has_no_live_projection_or_rollback_options():
    mod = _load()
    help_text = mod.build_parser().format_help()

    assert "--inventory" in help_text
    assert "--receipt-root" not in help_text
    assert "--destination" not in help_text
    assert "--state-root" not in help_text
    assert "--rollback" not in help_text
    assert "--publish" not in help_text


def test_runtime_dependency_and_registry_contracts():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    assert any(dependency.casefold().startswith("pyyaml") for dependency in dependencies)

    registry = yaml.safe_load((ROOT / "infra" / "tool-registry.yaml").read_text())
    entry = next(tool for tool in registry["tools"] if tool["name"] == "grok_web_snapshot")
    assert entry["path"] == "scripts/ops/grok_web_snapshot.py"
    assert entry["status"] == "internal"
    assert entry["consumers"] == ["claude-code.manual", "codex.manual"]
    assert "Knowledge" not in entry["description"]
    assert "LaunchAgent" not in entry["description"]
