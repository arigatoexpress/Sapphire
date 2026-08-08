#!/usr/bin/env python3
"""Import Grok web exports from one immutable Git tree into the raw Knowledge Inbox.

The checked-out working tree is never an input. Successful imports are represented
by content-addressed receipts and an atomic CURRENT pointer under a private state root.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
import unicodedata
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

SCHEMA_NAME = "sapphire.grok-web-import.receipt/v1"
POINTER_SCHEMA = "sapphire.grok-web-import.pointer/v1"
PUBLISH_MARKER_SCHEMA = "sapphire.grok-web-import.published/v1"
RECOVERY_SCHEMA = "sapphire.grok-web-import.recovery/v1"
IMPORTER_NAME = "grok_web_import"
IMPORTER_VERSION = "1"
VALIDATION_PROFILE = "grok-export-v1"
DEFAULT_SOURCE_REF = "refs/remotes/origin/main"
DEFAULT_SOURCE_PREFIX = "data/grok-web-exports"
FETCH_REFSPEC = "+refs/heads/main:refs/remotes/origin/main"
EXCLUDED_NAMES = frozenset({"README.md", "MANIFEST.json", ".gitkeep"})
ALLOWED_SUFFIXES = frozenset({".md", ".json"})
REQUIRED_PROVENANCE = ("source", "date", "type", "title")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40,64}$")
TREE_ROW_RE = re.compile(
    rb"^(?P<mode>[0-9]{6}) (?P<kind>blob|tree|commit) "
    rb"(?P<oid>[0-9a-f]{40,64}) +(?P<size>-|[0-9]+)\t(?P<path>.+)$"
)
FRONTMATTER_RE = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)
SECRET_PATH_NAMES = frozenset(
    {"auth", "credential", "credentials", "secret", "secrets", "private-key", ".env"}
)
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "private_key_block",
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "known_token_prefix",
        re.compile(
            rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
            rb"xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16})"
        ),
    ),
    (
        "credential_assignment",
        re.compile(
            rb"(?im)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|"
            rb"private[_-]?key)\b\s*[:=]\s*['\"]?"
            rb"(?!<redacted>|redacted|placeholder|example|none|null|unset|\$\{)"
            rb"[A-Za-z0-9_./+=-]{20,}"
        ),
    ),
)
POLICY = {
    "schema": 1,
    "source_ref": DEFAULT_SOURCE_REF,
    "source_prefix": DEFAULT_SOURCE_PREFIX,
    "fetch_refspec": FETCH_REFSPEC,
    "allowed_suffixes": sorted(ALLOWED_SUFFIXES),
    "excluded_names": sorted(EXCLUDED_NAMES),
    "required_provenance": list(REQUIRED_PROVENANCE),
    "regular_blob_mode": "100644",
    "validation_profile": VALIDATION_PROFILE,
}


class ImportRejected(RuntimeError):
    """A stable, content-blind import refusal."""

    def __init__(self, code: str, path: str | None = None):
        self.code = code
        self.path = path
        super().__init__(f"{code}:{path}" if path else code)


@dataclass(frozen=True)
class ImportConfig:
    repo: Path
    destination: Path
    state_root: Path
    source_ref: str = DEFAULT_SOURCE_REF
    source_prefix: str = DEFAULT_SOURCE_PREFIX
    remote: str = "origin"
    max_files: int = 500
    max_file_bytes: int = 4 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    lock_timeout_seconds: float = 30.0
    git_bin: str = "git"

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo", Path(self.repo).absolute())
        object.__setattr__(self, "destination", Path(self.destination).absolute())
        object.__setattr__(self, "state_root", Path(self.state_root).absolute())
        if self.remote != "origin":
            raise ValueError("remote must be origin")
        if self.source_ref != DEFAULT_SOURCE_REF:
            raise ValueError(f"source_ref must be {DEFAULT_SOURCE_REF}")
        if self.source_prefix != DEFAULT_SOURCE_PREFIX:
            raise ValueError(f"source_prefix must be {DEFAULT_SOURCE_PREFIX}")


@dataclass(frozen=True)
class ImportResult:
    status: str
    changed: bool
    receipt_sha256: str | None
    content_manifest_sha256: str
    source_commit: str
    source_files: int


@dataclass(frozen=True)
class Candidate:
    source_relpath: str
    destination_relpath: str
    git_blob_oid: str
    sha256: str
    size: int
    media_type: str
    data: bytes


def _destination_alias_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _validate_destination_aliases(candidates: list[Candidate]) -> None:
    seen: dict[str, str] = {}
    for candidate in candidates:
        name = candidate.destination_relpath
        alias_key = _destination_alias_key(name)
        if alias_key in seen:
            raise ImportRejected("destination_alias", name)
        seen[alias_key] = name


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _policy_sha256(config: ImportConfig) -> str:
    policy = {
        **POLICY,
        "max_files": config.max_files,
        "max_file_bytes": config.max_file_bytes,
        "max_total_bytes": config.max_total_bytes,
    }
    return _sha256(_canonical_json(policy))


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _run_git(config: ImportConfig, *args: str, binary: bool = False) -> bytes | str:
    command = [config.git_bin, "-C", str(config.repo), *args]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=not binary,
    )
    if result.returncode != 0:
        raise ImportRejected("git_command_failed")
    return result.stdout


def _fetch(config: ImportConfig) -> None:
    command = [
        config.git_bin,
        "-C",
        str(config.repo),
        "fetch",
        "--no-tags",
        config.remote,
        FETCH_REFSPEC,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ImportRejected("fetch_failed")


def _secret_path(path: str) -> bool:
    stem = Path(path).stem.casefold()
    return stem in SECRET_PATH_NAMES or Path(path).name.casefold() in SECRET_PATH_NAMES


def _detect_secret(data: bytes) -> str | None:
    for rule_id, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            return rule_id
    return None


def _decode_utf8(data: bytes, relative_path: str) -> str:
    if b"\x00" in data:
        raise ImportRejected("binary_content", relative_path)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ImportRejected("invalid_utf8", relative_path)


def _validate_provenance(value: Any, relative_path: str) -> None:
    if not isinstance(value, dict):
        raise ImportRejected("frontmatter_not_mapping", relative_path)
    for key in REQUIRED_PROVENANCE:
        field = value.get(key)
        if field is None or (isinstance(field, str) and not field.strip()):
            raise ImportRejected(f"missing_{key}", relative_path)


def _validate_candidate(path: str, data: bytes) -> str:
    if _secret_path(path):
        raise ImportRejected("secret_path", path)
    rule_id = _detect_secret(data)
    if rule_id:
        raise ImportRejected("secret_detected", path)
    text = _decode_utf8(data, path)
    suffix = Path(path).suffix.casefold()
    if suffix == ".md":
        match = FRONTMATTER_RE.match(text)
        if not match:
            raise ImportRejected("missing_frontmatter", path)
        try:
            frontmatter = yaml.safe_load(match.group("body"))
        except yaml.YAMLError:
            raise ImportRejected("invalid_yaml", path)
        _validate_provenance(frontmatter, path)
        return "text/markdown"
    if suffix == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            raise ImportRejected("invalid_json", path)
        _validate_provenance(value, path)
        return "application/json"
    raise ImportRejected("unsupported_extension", path)


def _source_snapshot(config: ImportConfig, *, fetch: bool) -> tuple[str, str, list[Candidate]]:
    if fetch:
        _fetch(config)
    commit = str(_run_git(config, "rev-parse", "--verify", f"{config.source_ref}^{{commit}}"))
    commit = commit.strip()
    if not GIT_OID_RE.fullmatch(commit):
        raise ImportRejected("invalid_commit_oid")
    tree = str(
        _run_git(
            config,
            "rev-parse",
            "--verify",
            f"{commit}:{config.source_prefix}",
        )
    ).strip()
    if not GIT_OID_RE.fullmatch(tree):
        raise ImportRejected("invalid_tree_oid")
    raw_rows = _run_git(
        config,
        "ls-tree",
        "-r",
        "-z",
        "--long",
        commit,
        "--",
        config.source_prefix,
        binary=True,
    )
    assert isinstance(raw_rows, bytes)
    candidates: list[Candidate] = []
    total_bytes = 0
    prefix = f"{config.source_prefix}/"
    for raw_row in raw_rows.split(b"\x00"):
        if not raw_row:
            continue
        match = TREE_ROW_RE.match(raw_row)
        if not match:
            raise ImportRejected("invalid_tree_row")
        try:
            source_path = match.group("path").decode("utf-8")
        except UnicodeDecodeError:
            raise ImportRejected("invalid_tree_path")
        if not source_path.startswith(prefix):
            raise ImportRejected("path_outside_prefix", source_path)
        relative = source_path[len(prefix) :]
        if not relative or "/" in relative or relative in {".", ".."}:
            raise ImportRejected("nested_path", source_path)
        if relative in EXCLUDED_NAMES:
            continue
        suffix = Path(relative).suffix.casefold()
        if suffix not in ALLOWED_SUFFIXES:
            raise ImportRejected("unsupported_extension", source_path)
        mode = match.group("mode").decode("ascii")
        kind = match.group("kind").decode("ascii")
        if mode != "100644" or kind != "blob":
            raise ImportRejected("forbidden_tree_entry", source_path)
        size_raw = match.group("size")
        if size_raw == b"-":
            raise ImportRejected("missing_blob_size", source_path)
        size = int(size_raw)
        if size > config.max_file_bytes:
            raise ImportRejected("file_too_large", source_path)
        oid = match.group("oid").decode("ascii")
        if _secret_path(relative):
            raise ImportRejected("secret_path", relative)
        blob = _run_git(config, "cat-file", "blob", oid, binary=True)
        assert isinstance(blob, bytes)
        if len(blob) != size:
            raise ImportRejected("blob_size_mismatch", source_path)
        media_type = _validate_candidate(relative, blob)
        digest = _sha256(blob)
        candidates.append(
            Candidate(
                source_relpath=source_path,
                destination_relpath=relative,
                git_blob_oid=oid,
                sha256=digest,
                size=size,
                media_type=media_type,
                data=blob,
            )
        )
        total_bytes += size
        if len(candidates) > config.max_files:
            raise ImportRejected("too_many_files")
        if total_bytes > config.max_total_bytes:
            raise ImportRejected("source_too_large")
    candidates.sort(key=lambda item: item.source_relpath)
    if not candidates:
        raise ImportRejected("empty_source")
    _validate_destination_aliases(candidates)
    return commit, tree, candidates


def _manifest_sha256(candidates: list[Candidate]) -> str:
    manifest = [
        {
            "source_relpath": item.source_relpath,
            "git_blob_oid": item.git_blob_oid,
            "sha256": item.sha256,
            "bytes": item.size,
            "media_type": item.media_type,
            "validation_profile": VALIDATION_PROFILE,
        }
        for item in candidates
    ]
    return _sha256(_canonical_json(manifest))


def _ensure_dir(path: Path, mode: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    _ensure_dir(path.parent, 0o700 if mode == 0o600 else 0o755)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


@contextmanager
def _import_lock(config: ImportConfig):
    _ensure_dir(config.state_root, 0o700)
    lock_path = config.state_root / "import.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    os.chmod(lock_path, 0o600)
    started = time.monotonic()
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - started >= config.lock_timeout_seconds:
                    raise ImportRejected("lock_timeout")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _receipt_path(config: ImportConfig, digest: str) -> Path:
    if not SHA256_RE.fullmatch(digest):
        raise ImportRejected("invalid_receipt_digest")
    return config.state_root / "receipts" / "sha256" / digest[:2] / f"{digest}.json"


def _blob_path(config: ImportConfig, digest: str) -> Path:
    if not SHA256_RE.fullmatch(digest):
        raise ImportRejected("invalid_blob_digest")
    return config.state_root / "blobs" / "sha256" / digest[:2] / digest


def _validate_receipt(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA_NAME:
        raise ImportRejected("invalid_receipt_schema")
    if receipt.get("operation") not in {"import", "rollback"}:
        raise ImportRejected("invalid_receipt_operation")
    if not SHA256_RE.fullmatch(str(receipt.get("content_manifest_sha256", ""))):
        raise ImportRejected("invalid_manifest_digest")
    files = receipt.get("files")
    retired = receipt.get("retired")
    if not isinstance(files, list) or not isinstance(retired, list):
        raise ImportRejected("invalid_receipt_files")
    for item in files:
        if not isinstance(item, dict):
            raise ImportRejected("invalid_receipt_file")
        name = item.get("destination_relpath")
        if not isinstance(name, str) or Path(name).name != name:
            raise ImportRejected("invalid_destination_path")
        if not SHA256_RE.fullmatch(str(item.get("after_sha256", ""))):
            raise ImportRejected("invalid_destination_digest", name)
    return receipt


def _load_receipt(config: ImportConfig, digest: str) -> dict[str, Any]:
    path = _receipt_path(config, digest)
    try:
        raw = path.read_bytes()
    except OSError:
        raise ImportRejected("receipt_missing")
    if _sha256(raw) != digest:
        raise ImportRejected("receipt_digest_mismatch")
    try:
        receipt = json.loads(raw)
    except json.JSONDecodeError:
        raise ImportRejected("receipt_invalid_json")
    return _validate_receipt(receipt)


def _load_current(config: ImportConfig) -> tuple[str, dict[str, Any]] | None:
    pointer_path = config.state_root / "CURRENT.json"
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ImportRejected("current_pointer_invalid")
    if pointer.get("schema") != POINTER_SCHEMA:
        raise ImportRejected("current_pointer_schema")
    digest = pointer.get("receipt_sha256")
    if not isinstance(digest, str):
        raise ImportRejected("current_pointer_digest")
    return digest, _load_receipt(config, digest)


def _hash_file(path: Path, code: str) -> str:
    try:
        metadata = path.lstat()
    except OSError:
        raise ImportRejected(code, path.name)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ImportRejected(code, path.name)
    return _sha256(path.read_bytes())


def _current_files(receipt: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not receipt:
        return {}
    return {item["destination_relpath"]: item for item in receipt["files"]}


def _verify_managed(config: ImportConfig, receipt: dict[str, Any] | None) -> None:
    for name, item in _current_files(receipt).items():
        actual = _hash_file(config.destination / name, "managed_drift")
        if actual != item["after_sha256"]:
            raise ImportRejected("managed_drift", name)


def _plan_files(
    config: ImportConfig,
    candidates: list[Candidate],
    current: dict[str, Any] | None,
    current_receipt_sha: str | None,
    manifest_sha: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current_by_name = _current_files(current)
    current_by_alias = {_destination_alias_key(name): name for name in current_by_name}
    source_names = {candidate.destination_relpath for candidate in candidates}
    planned: list[dict[str, Any]] = []
    for candidate in candidates:
        name = candidate.destination_relpath
        aliased_current = current_by_alias.get(_destination_alias_key(name))
        if aliased_current is not None and aliased_current != name:
            raise ImportRejected("destination_alias_current", name)
        target = config.destination / name
        current_item = current_by_name.get(name)
        before: str | None = None
        if current_item:
            before = current_item["after_sha256"]
            action = "unchanged" if before == candidate.sha256 else "replaced"
        elif target.exists() or target.is_symlink():
            before = _hash_file(target, "unmanaged_collision")
            if before != candidate.sha256:
                raise ImportRejected("unmanaged_collision", name)
            action = "adopted"
        else:
            action = "created"
        planned.append(
            {
                "source_relpath": candidate.source_relpath,
                "destination_relpath": name,
                "git_blob_oid": candidate.git_blob_oid,
                "sha256": candidate.sha256,
                "bytes": candidate.size,
                "media_type": candidate.media_type,
                "validation_profile": VALIDATION_PROFILE,
                "before_sha256": before,
                "after_sha256": candidate.sha256,
                "action": action,
            }
        )
    retired: list[dict[str, Any]] = []
    for name in sorted(set(current_by_name) - source_names):
        if not current_receipt_sha:
            raise ImportRejected("current_receipt_missing")
        item = current_by_name[name]
        retired.append(
            {
                "destination_relpath": name,
                "before_sha256": item["after_sha256"],
                "quarantine_relpath": f"{manifest_sha}/{current_receipt_sha}/{name}",
                "action": "retired-to-quarantine",
            }
        )
    return planned, retired


def _summary(files: list[dict[str, Any]], retired: list[dict[str, Any]]) -> dict[str, int]:
    counts = {action: 0 for action in ("created", "adopted", "replaced", "unchanged")}
    for item in files:
        counts[item["action"]] += 1
    return {
        "source_files": len(files),
        **counts,
        "retired": len(retired),
        "bytes": sum(int(item["bytes"]) for item in files),
    }


def _store_blob(config: ImportConfig, candidate: Candidate) -> None:
    path = _blob_path(config, candidate.sha256)
    if path.exists():
        if _hash_file(path, "blob_store_corrupt") != candidate.sha256:
            raise ImportRejected("blob_store_corrupt", candidate.destination_relpath)
        os.chmod(path, 0o600)
        return
    _atomic_write(path, candidate.data, 0o600)


def _materialize(
    config: ImportConfig,
    candidates: list[Candidate],
    files: list[dict[str, Any]],
    retired: list[dict[str, Any]],
) -> None:
    _ensure_dir(config.destination, 0o755)
    by_name = {candidate.destination_relpath: candidate for candidate in candidates}
    for item in files:
        if item["action"] in {"created", "replaced"}:
            candidate = by_name[item["destination_relpath"]]
            _atomic_write(config.destination / candidate.destination_relpath, candidate.data, 0o644)
    for item in retired:
        source = config.destination / item["destination_relpath"]
        quarantine = config.state_root / "quarantine" / item["quarantine_relpath"]
        _ensure_dir(quarantine.parent, 0o700)
        if quarantine.exists():
            raise ImportRejected("quarantine_collision", item["destination_relpath"])
        os.replace(source, quarantine)
        os.chmod(quarantine, 0o600)
        _fsync_dir(source.parent)
        _fsync_dir(quarantine.parent)
    for item in files:
        actual = _hash_file(config.destination / item["destination_relpath"], "materialize_failed")
        if actual != item["after_sha256"]:
            raise ImportRejected("materialize_failed", item["destination_relpath"])


def _restore_materialization(
    config: ImportConfig,
    files: list[dict[str, Any]],
    retired: list[dict[str, Any]],
) -> None:
    """Restore the pre-attempt managed bytes after activation fails."""
    for item in retired:
        name = item["destination_relpath"]
        destination = config.destination / name
        quarantine = config.state_root / "quarantine" / item["quarantine_relpath"]
        if destination.exists() or destination.is_symlink():
            if _hash_file(destination, "activation_recovery_failed") != item["before_sha256"]:
                raise ImportRejected("activation_recovery_failed", name)
            continue
        if not quarantine.exists():
            raise ImportRejected("activation_recovery_failed", name)
        if _hash_file(quarantine, "activation_recovery_failed") != item["before_sha256"]:
            raise ImportRejected("activation_recovery_failed", name)
        os.replace(quarantine, destination)
        os.chmod(destination, 0o644)
        _fsync_dir(destination.parent)
        _fsync_dir(quarantine.parent)

    for item in files:
        name = item["destination_relpath"]
        destination = config.destination / name
        if item["action"] == "created":
            if not (destination.exists() or destination.is_symlink()):
                continue
            if _hash_file(destination, "activation_recovery_failed") != item["after_sha256"]:
                raise ImportRejected("activation_recovery_failed", name)
            destination.unlink()
            _fsync_dir(destination.parent)
        elif item["action"] == "replaced":
            before = item["before_sha256"]
            if not isinstance(before, str):
                raise ImportRejected("activation_recovery_failed", name)
            blob = _blob_path(config, before)
            data = blob.read_bytes() if blob.exists() else b""
            if _sha256(data) != before:
                raise ImportRejected("activation_recovery_failed", name)
            _atomic_write(destination, data, 0o644)


def _pointer_activates(config: ImportConfig, receipt: dict[str, Any]) -> bool:
    expected = _sha256(_canonical_json(receipt))
    try:
        current = _load_current(config)
    except ImportRejected:
        return False
    return bool(current and current[0] == expected)


def _publish_receipt_once(
    config: ImportConfig,
    receipt_sha: str,
    publisher: Callable[[], None] | None,
) -> None:
    if not publisher:
        return
    marker = config.state_root / "published" / f"{receipt_sha}.json"
    expected = _canonical_json(
        {
            "schema": PUBLISH_MARKER_SCHEMA,
            "receipt_sha256": receipt_sha,
        }
    )
    if marker.exists():
        if marker.read_bytes() != expected:
            raise ImportRejected("publish_marker_invalid")
        return
    publisher()
    _atomic_write(marker, expected, 0o600)


def _recovery_path(config: ImportConfig) -> Path:
    return config.state_root / "RECOVERY.json"


def _validate_recovery_name(name: Any) -> str:
    if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."}:
        raise ImportRejected("recovery_journal_invalid")
    return name


def _validate_recovery_journal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != RECOVERY_SCHEMA:
        raise ImportRejected("recovery_journal_invalid")
    payload = value.get("payload")
    payload_sha = value.get("payload_sha256")
    if not isinstance(payload, dict) or not SHA256_RE.fullmatch(str(payload_sha or "")):
        raise ImportRejected("recovery_journal_invalid")
    if _sha256(_canonical_json(payload)) != payload_sha:
        raise ImportRejected("recovery_journal_digest")
    if payload.get("operation") not in {"import", "rollback"}:
        raise ImportRejected("recovery_journal_invalid")
    for field in ("target_receipt_sha256",):
        if not SHA256_RE.fullmatch(str(payload.get(field, ""))):
            raise ImportRejected("recovery_journal_invalid")
    previous = payload.get("previous_receipt_sha256")
    if previous is not None and not SHA256_RE.fullmatch(str(previous)):
        raise ImportRejected("recovery_journal_invalid")
    files = payload.get("files")
    retired = payload.get("retired")
    if not isinstance(files, list) or not isinstance(retired, list):
        raise ImportRejected("recovery_journal_invalid")
    for item in files:
        if not isinstance(item, dict):
            raise ImportRejected("recovery_journal_invalid")
        _validate_recovery_name(item.get("destination_relpath"))
        if item.get("action") not in {"adopted", "created", "replaced", "unchanged"}:
            raise ImportRejected("recovery_journal_invalid")
        if not SHA256_RE.fullmatch(str(item.get("after_sha256", ""))):
            raise ImportRejected("recovery_journal_invalid")
        before = item.get("before_sha256")
        if before is not None and not SHA256_RE.fullmatch(str(before)):
            raise ImportRejected("recovery_journal_invalid")
    for item in retired:
        if not isinstance(item, dict) or item.get("action") != "retired-to-quarantine":
            raise ImportRejected("recovery_journal_invalid")
        name = _validate_recovery_name(item.get("destination_relpath"))
        if not SHA256_RE.fullmatch(str(item.get("before_sha256", ""))):
            raise ImportRejected("recovery_journal_invalid")
        quarantine = item.get("quarantine_relpath")
        if not isinstance(quarantine, str):
            raise ImportRejected("recovery_journal_invalid")
        quarantine_path = Path(quarantine)
        if (
            quarantine_path.is_absolute()
            or ".." in quarantine_path.parts
            or quarantine_path.name != name
        ):
            raise ImportRejected("recovery_journal_invalid")
    return payload


def _load_recovery_journal(config: ImportConfig) -> dict[str, Any] | None:
    path = _recovery_path(config)
    if not path.exists() and not path.is_symlink():
        return None
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ImportRejected("recovery_journal_invalid")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        raise ImportRejected("recovery_journal_invalid")
    return _validate_recovery_journal(value)


def _begin_recovery_journal(
    config: ImportConfig,
    receipt: dict[str, Any],
    files: list[dict[str, Any]],
    retired: list[dict[str, Any]],
) -> None:
    path = _recovery_path(config)
    if path.exists() or path.is_symlink():
        raise ImportRejected("recovery_pending")
    payload = {
        "operation": receipt["operation"],
        "previous_receipt_sha256": receipt["previous_receipt_sha256"],
        "target_receipt_sha256": _sha256(_canonical_json(receipt)),
        "files": files,
        "retired": retired,
    }
    journal = {
        "schema": RECOVERY_SCHEMA,
        "payload_sha256": _sha256(_canonical_json(payload)),
        "payload": payload,
    }
    _atomic_write(path, _canonical_json(journal), 0o600)


def _clear_recovery_journal(config: ImportConfig) -> None:
    path = _recovery_path(config)
    if not path.exists() and not path.is_symlink():
        return
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ImportRejected("recovery_journal_invalid")
    path.unlink()
    _fsync_dir(path.parent)


def _recover_interrupted(config: ImportConfig) -> None:
    journal = _load_recovery_journal(config)
    if not journal:
        return
    current_pair = _load_current(config)
    current_sha, current = current_pair if current_pair else (None, None)
    if current_sha == journal["target_receipt_sha256"]:
        _verify_managed(config, current)
        _clear_recovery_journal(config)
        return
    if current_sha != journal["previous_receipt_sha256"]:
        raise ImportRejected("recovery_pointer_mismatch")
    _restore_materialization(config, journal["files"], journal["retired"])
    _verify_managed(config, current)
    _clear_recovery_journal(config)


def _write_receipt_and_pointer(
    config: ImportConfig,
    receipt: dict[str, Any],
    *,
    fault_injector: Callable[[str], None] | None,
) -> str:
    _validate_receipt(receipt)
    receipt_bytes = _canonical_json(receipt)
    receipt_digest = _sha256(receipt_bytes)
    receipt_path = _receipt_path(config, receipt_digest)
    if receipt_path.exists():
        if receipt_path.read_bytes() != receipt_bytes:
            raise ImportRejected("receipt_collision")
    else:
        _atomic_write(receipt_path, receipt_bytes, 0o600)
    if fault_injector:
        fault_injector("before_pointer")
    pointer = {
        "schema": POINTER_SCHEMA,
        "receipt_sha256": receipt_digest,
        "content_manifest_sha256": receipt["content_manifest_sha256"],
        "previous_receipt_sha256": receipt["previous_receipt_sha256"],
        "updated_at": receipt["activated_at"],
    }
    _atomic_write(config.state_root / "CURRENT.json", _canonical_json(pointer), 0o600)
    return receipt_digest


def _activate_receipt(
    config: ImportConfig,
    candidates: list[Candidate],
    files: list[dict[str, Any]],
    retired: list[dict[str, Any]],
    receipt: dict[str, Any],
    fault_injector: Callable[[str], None] | None,
) -> str:
    _begin_recovery_journal(config, receipt, files, retired)
    try:
        _materialize(config, candidates, files, retired)
        if fault_injector:
            fault_injector("after_materialize")
    except Exception:
        _restore_materialization(config, files, retired)
        _clear_recovery_journal(config)
        raise
    try:
        receipt_sha = _write_receipt_and_pointer(
            config,
            receipt,
            fault_injector=fault_injector,
        )
    except Exception:
        if not _pointer_activates(config, receipt):
            _restore_materialization(config, files, retired)
            _clear_recovery_journal(config)
            raise
        receipt_sha = _sha256(_canonical_json(receipt))
    if fault_injector:
        fault_injector("after_pointer")
    _clear_recovery_journal(config)
    return receipt_sha


def _build_receipt(
    config: ImportConfig,
    *,
    operation: str,
    commit: str,
    tree: str,
    fetch_attempted: bool,
    manifest_sha: str,
    previous_receipt_sha: str | None,
    rollback_of: str | None,
    files: list[dict[str, Any]],
    retired: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_NAME,
        "operation": operation,
        "activated_at": _utc_now(),
        "importer": {
            "name": IMPORTER_NAME,
            "version": IMPORTER_VERSION,
            "policy_sha256": _policy_sha256(config),
        },
        "source": {
            "repo": str(config.repo),
            "remote": config.remote,
            "requested_ref": config.source_ref,
            "fetch_attempted": fetch_attempted,
            "commit_oid": commit,
            "tree_oid": tree,
            "tree_prefix": config.source_prefix,
        },
        "destination": {
            "root": str(config.destination),
            "admission_class": "raw-unreviewed-inbox",
            "managed_paths_only": True,
        },
        "content_manifest_sha256": manifest_sha,
        "previous_receipt_sha256": previous_receipt_sha,
        "rollback_of_receipt_sha256": rollback_of,
        "files": files,
        "retired": retired,
        "summary": _summary(files, retired),
    }


def _perform_import(
    config: ImportConfig,
    *,
    fetch: bool,
    dry_run: bool,
    publisher: Callable[[], None] | None,
    fault_injector: Callable[[str], None] | None,
) -> ImportResult:
    commit, tree, candidates = _source_snapshot(config, fetch=fetch)
    manifest_sha = _manifest_sha256(candidates)
    current_pair = _load_current(config) if config.state_root.exists() else None
    current_sha, current = current_pair if current_pair else (None, None)
    _verify_managed(config, current)
    if current and current["content_manifest_sha256"] == manifest_sha:
        assert current_sha
        _publish_receipt_once(config, current_sha, publisher)
        return ImportResult(
            status="unchanged",
            changed=False,
            receipt_sha256=current_sha,
            content_manifest_sha256=manifest_sha,
            source_commit=commit,
            source_files=len(candidates),
        )
    files, retired = _plan_files(
        config,
        candidates,
        current,
        current_sha,
        manifest_sha,
    )
    if dry_run:
        return ImportResult(
            status="dry_run",
            changed=True,
            receipt_sha256=None,
            content_manifest_sha256=manifest_sha,
            source_commit=commit,
            source_files=len(candidates),
        )
    for candidate in candidates:
        _store_blob(config, candidate)
    receipt = _build_receipt(
        config,
        operation="import",
        commit=commit,
        tree=tree,
        fetch_attempted=fetch,
        manifest_sha=manifest_sha,
        previous_receipt_sha=current_sha,
        rollback_of=None,
        files=files,
        retired=retired,
    )
    receipt_sha = _activate_receipt(
        config,
        candidates,
        files,
        retired,
        receipt,
        fault_injector,
    )
    _publish_receipt_once(config, receipt_sha, publisher)
    return ImportResult(
        status="imported",
        changed=True,
        receipt_sha256=receipt_sha,
        content_manifest_sha256=manifest_sha,
        source_commit=commit,
        source_files=len(candidates),
    )


def import_exports(
    config: ImportConfig,
    *,
    fetch: bool = False,
    dry_run: bool = False,
    publisher: Callable[[], None] | None = None,
    fault_injector: Callable[[str], None] | None = None,
) -> ImportResult:
    """Import one resolved remote-tree snapshot; never read the checkout."""
    if dry_run:
        if _recovery_path(config).exists() or _recovery_path(config).is_symlink():
            raise ImportRejected("recovery_pending")
        return _perform_import(
            config,
            fetch=fetch,
            dry_run=True,
            publisher=None,
            fault_injector=fault_injector,
        )
    with _import_lock(config):
        _recover_interrupted(config)
        return _perform_import(
            config,
            fetch=fetch,
            dry_run=False,
            publisher=publisher,
            fault_injector=fault_injector,
        )


def _candidate_from_receipt(config: ImportConfig, item: dict[str, Any]) -> Candidate:
    digest = item["sha256"]
    blob_path = _blob_path(config, digest)
    data = blob_path.read_bytes() if blob_path.exists() else b""
    if _sha256(data) != digest:
        raise ImportRejected("blob_store_corrupt", item["destination_relpath"])
    return Candidate(
        source_relpath=item["source_relpath"],
        destination_relpath=item["destination_relpath"],
        git_blob_oid=item["git_blob_oid"],
        sha256=digest,
        size=int(item["bytes"]),
        media_type=item["media_type"],
        data=data,
    )


def rollback_import(
    config: ImportConfig,
    target_receipt_sha256: str,
    *,
    dry_run: bool = False,
    publisher: Callable[[], None] | None = None,
    fault_injector: Callable[[str], None] | None = None,
) -> ImportResult:
    """Restore the managed set described by a prior verified receipt without network I/O."""
    if dry_run and (_recovery_path(config).exists() or _recovery_path(config).is_symlink()):
        raise ImportRejected("recovery_pending")
    with _import_lock(config):
        _recover_interrupted(config)
        current_pair = _load_current(config)
        if not current_pair:
            raise ImportRejected("current_pointer_missing")
        current_sha, current = current_pair
        _verify_managed(config, current)
        target = _load_receipt(config, target_receipt_sha256)
        if (
            current_sha == target_receipt_sha256
            or current["content_manifest_sha256"] == target["content_manifest_sha256"]
        ):
            _publish_receipt_once(config, current_sha, None if dry_run else publisher)
            return ImportResult(
                status="unchanged",
                changed=False,
                receipt_sha256=current_sha,
                content_manifest_sha256=current["content_manifest_sha256"],
                source_commit=current["source"]["commit_oid"],
                source_files=len(current["files"]),
            )
        candidates = [_candidate_from_receipt(config, item) for item in target["files"]]
        _validate_destination_aliases(candidates)
        manifest_sha = target["content_manifest_sha256"]
        files, retired = _plan_files(
            config,
            candidates,
            current,
            current_sha,
            manifest_sha,
        )
        if dry_run:
            return ImportResult(
                status="dry_run",
                changed=True,
                receipt_sha256=None,
                content_manifest_sha256=manifest_sha,
                source_commit=target["source"]["commit_oid"],
                source_files=len(candidates),
            )
        receipt = _build_receipt(
            config,
            operation="rollback",
            commit=target["source"]["commit_oid"],
            tree=target["source"]["tree_oid"],
            fetch_attempted=False,
            manifest_sha=manifest_sha,
            previous_receipt_sha=current_sha,
            rollback_of=current_sha,
            files=files,
            retired=retired,
        )
        receipt_sha = _activate_receipt(
            config,
            candidates,
            files,
            retired,
            receipt,
            fault_injector,
        )
        _publish_receipt_once(config, receipt_sha, publisher)
        return ImportResult(
            status="rolled_back",
            changed=True,
            receipt_sha256=receipt_sha,
            content_manifest_sha256=manifest_sha,
            source_commit=target["source"]["commit_oid"],
            source_files=len(candidates),
        )


def _publish_operator_feeds(publisher: Path | None = None) -> None:
    publisher = publisher or (
        Path.home() / "ops-state" / "finish-line" / "scripts" / "publish_operator_feeds.py"
    )
    if not publisher.is_file():
        raise ImportRejected("publisher_unavailable")
    result = subprocess.run(
        [sys.executable, str(publisher)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ImportRejected("publisher_failed")


def _build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=root)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.home() / "Knowledge" / "0-Inbox" / "grok-web",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path.home() / "ops-state" / "grok-web-import",
    )
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--pull", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--rollback", metavar="RECEIPT_SHA256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = ImportConfig(
        repo=args.repo,
        destination=args.destination,
        state_root=args.state_root,
    )
    try:
        publisher = None if args.no_publish else _publish_operator_feeds
        if args.rollback:
            result = rollback_import(
                config,
                args.rollback,
                dry_run=args.dry_run,
                publisher=publisher,
            )
        else:
            result = import_exports(
                config,
                fetch=args.fetch or args.pull,
                dry_run=args.dry_run,
                publisher=publisher,
            )
    except ImportRejected as exc:
        print(
            json.dumps(
                {"ok": False, "error": exc.code, "path": exc.path},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"ok": True, **asdict(result)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
