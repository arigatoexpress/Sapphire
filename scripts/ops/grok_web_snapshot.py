#!/usr/bin/env python3
"""Apply bounded policy checks to immutable Grok web exports and emit a receipt.

This boundary reads only the configured remote-tracking Git tree. It never reads the
checkout, mutates the Knowledge vault, activates a pointer, publishes, or rolls back.
The receipt records source identity and known-policy results; it does not certify
secret-free content or grant admission, projection, or execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

SCHEMA_NAME = "sapphire.grok-web-snapshot.receipt/v1"
VALIDATOR_NAME = "grok_web_snapshot"
VALIDATOR_VERSION = "17"
POLICY_PROFILE = "grok-export-v17"
SECRET_POLICY_REVISION = 14
DEFAULT_SOURCE_REF = "refs/remotes/origin/main"
DEFAULT_SOURCE_PREFIX = "data/grok-web-exports"
FETCH_REFSPEC = "+refs/heads/main:refs/remotes/origin/main"
MAX_STRUCTURED_DEPTH = 100
MAX_STRUCTURED_NODES = 10_000
OBJECT_READ_CHUNK_BYTES = 64 * 1024
MAX_COMMIT_OBJECT_BYTES = 1024 * 1024
MAX_TREE_OBJECT_BYTES = 4 * 1024 * 1024
EXCLUDED_NAMES = frozenset({"README.md", "MANIFEST.json", ".gitkeep"})
ALLOWED_SUFFIXES = frozenset({".md", ".json"})
REQUIRED_PROVENANCE = ("source", "date", "type", "title")
SECRET_PATH_REDACTION = "[secret-path-redacted]"
SECRET_PATH_NAMES = frozenset(
    {"auth", "credential", "credentials", "secret", "secrets", "private-key", ".env"}
)
STRUCTURED_SECRET_KEY_NAMES = frozenset(
    {
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
    }
)
STRUCTURED_SECRET_KEY_SUFFIXES = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "authorization",
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
    }
)
CREDENTIAL_LABEL_PATTERN = (
    rb"(?:[A-Za-z][A-Za-z0-9]*[_-])*(?:api[_-]?key|"
    rb"(?:access|auth|bearer|id|refresh|session)[_-]?token|client[_-]?secret|"
    rb"password|private[_-]?key|secret(?:[_-]?key)?|authorization|credential(?:s)?)"
)
GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)
JSON_SIMPLE_ESCAPES = {
    ord('"'): b'"',
    ord("\\"): b"\\",
    ord("/"): b"/",
    ord("b"): b"\b",
    ord("f"): b"\f",
    ord("n"): b"\n",
    ord("r"): b"\r",
    ord("t"): b"\t",
}
SECRET_DECODE_TRANSFORMS = (
    "json_escape_view_v1",
    "yaml_hex_escape_view_v1",
)
SECRET_DECODE_SURFACES = ("markdown_body", "excluded_text", "structured_scalar")
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "private_key_block",
        re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "known_token_prefix",
        re.compile(
            rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            rb"gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
            rb"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|"
            rb"ya29\.[A-Za-z0-9._/-]{12,}|"
            rb"(?<![0-9])[0-9]{8,12}:[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_-])|"
            rb"[sr]k_(?:live|test)_[A-Za-z0-9]{16,})"
        ),
    ),
    (
        "quoted_credential_assignment",
        re.compile(
            rb"(?im)\b" + CREDENTIAL_LABEL_PATTERN + rb"\b\s*['\"]?\s*[:=]\s*"
            rb"(?P<quote>['\"])[ \t]*"
            rb"(?!(?:<redacted>|redacted|placeholder|example|none|null|unset)"
            rb"[ \t]*(?P=quote))(?!\$\{)[^'\"\r\n]+(?P=quote)"
        ),
    ),
    (
        "unquoted_credential_assignment",
        re.compile(
            rb"(?im)\b" + CREDENTIAL_LABEL_PATTERN + rb"\b\s*['\"]?\s*[:=]"
            rb"(?![ \t]*['\"\[{|>])"
            rb"(?![ \t]*(?:<redacted>|redacted|placeholder|example|none|null|unset)"
            rb"[ \t]*$)(?![ \t]*\$\{)[ \t]*\S[^\r\n]*$"
        ),
    ),
    (
        "aws_secret_assignment",
        re.compile(
            rb"(?im)\baws[_-]?secret(?:[_-]?access)?[_-]?key\b\s*['\"]?\s*[:=]"
            rb"\s*['\"]?"
            rb"(?!<redacted>|redacted|placeholder|example|none|null|unset|\$\{)"
            rb"[A-Za-z0-9/+=]{40}"
        ),
    ),
    (
        "mnemonic_assignment",
        re.compile(
            rb"(?im)\b(?:mnemonic|seed[_-]?phrase|recovery[_-]?phrase)\b"
            rb"\s*['\"]?\s*[:=]\s*['\"]?"
            rb"(?!<redacted>|redacted|placeholder|example|none|null|unset|\$\{)"
            rb"(?:[a-z]{2,}\s+){11,23}[a-z]{2,}\b"
        ),
    ),
)
UNSTRUCTURED_TEXT_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "yaml_block_credential_assignment",
        re.compile(
            rb"(?im)\b" + CREDENTIAL_LABEL_PATTERN + rb"\b\s*['\"]?\s*[:=][ \t]*"
            rb"(?:[>|](?:[+-][1-9]?|[1-9][+-]?)?[ \t]*)?"
            rb"(?:#[^\r\n]*)?\r?\n"
            rb"(?:(?:[ \t]*\r?\n)|(?:[ \t]+(?:<redacted>|redacted|placeholder|"
            rb"example|none|null|unset|\$\{[A-Za-z_][A-Za-z0-9_]*\})[ \t]*\r?\n))*"
            rb"(?![ \t]+(?:<redacted>|redacted|placeholder|example|"
            rb"none|null|unset)[ \t]*$)(?![ \t]+\$\{)[ \t]+\S[^\r\n]*$"
        ),
    ),
    (
        "credential_container_assignment",
        re.compile(rb"(?im)\b" + CREDENTIAL_LABEL_PATTERN + rb"\b\s*['\"]?\s*[:=][ \t]*[\[{]"),
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
    "max_structured_depth": MAX_STRUCTURED_DEPTH,
    "max_structured_nodes": MAX_STRUCTURED_NODES,
    "object_read_chunk_bytes": OBJECT_READ_CHUNK_BYTES,
    "max_commit_object_bytes": MAX_COMMIT_OBJECT_BYTES,
    "max_tree_object_bytes": MAX_TREE_OBJECT_BYTES,
    "git_object_identity": "verify_bounded_commit_tree_blob_chain_v2",
    "regular_blob_mode": "100644",
    "json_duplicate_keys": "reject",
    "yaml_duplicate_keys": "reject",
    "policy_profile": POLICY_PROFILE,
    "secret_policy": {
        "revision": SECRET_POLICY_REVISION,
        "decode_transforms": list(SECRET_DECODE_TRANSFORMS),
        "decode_surfaces": list(SECRET_DECODE_SURFACES),
        "inventory_path_redaction": SECRET_PATH_REDACTION,
        "path_names": sorted(SECRET_PATH_NAMES),
        "scan_filenames": True,
        "structured_scalar_scans": [
            "unstructured_text_rules",
            "decoded_escape_views_unstructured_text_rules",
        ],
        "structured_key_names": sorted(STRUCTURED_SECRET_KEY_NAMES),
        "structured_key_suffixes": sorted(STRUCTURED_SECRET_KEY_SUFFIXES),
        "rules": [
            {
                "id": rule_id,
                "pattern": pattern.pattern.decode("ascii"),
                "flags": int(pattern.flags),
            }
            for rule_id, pattern in SECRET_PATTERNS
        ],
        "unstructured_text_rules": [
            {
                "id": rule_id,
                "pattern": pattern.pattern.decode("ascii"),
                "flags": int(pattern.flags),
            }
            for rule_id, pattern in UNSTRUCTURED_TEXT_SECRET_PATTERNS
        ],
    },
}


class SnapshotRejected(RuntimeError):
    """Stable, content-blind bounded-policy refusal."""

    def __init__(self, code: str, path: str | None = None):
        self.code = code
        self.path = path
        super().__init__(f"{code}:{path}" if path else code)


@dataclass(frozen=True)
class SnapshotConfig:
    repo: Path
    remote: str = "origin"
    source_ref: str = DEFAULT_SOURCE_REF
    source_prefix: str = DEFAULT_SOURCE_PREFIX
    max_files: int = 500
    max_file_bytes: int = 4 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    git_bin: str = "git"


@dataclass(frozen=True)
class TreeEntry:
    source_relpath: str
    relative_path: str
    mode: str
    kind: str
    git_blob_oid: str
    size: int | None


@dataclass(frozen=True)
class GitTreeRecord:
    mode: bytes
    name: bytes
    oid: str


@dataclass(frozen=True)
class PolicyCheckedFile:
    source_relpath: str
    relative_path: str
    git_blob_oid: str
    sha256: str
    size: int
    media_type: str


@dataclass(frozen=True)
class SnapshotResult:
    source_commit: str
    source_tree: str
    receipt_sha256: str
    receipt: dict[str, Any]


@dataclass(frozen=True)
class Rejection:
    path: str
    code: str


@dataclass(frozen=True)
class InventoryResult:
    source_commit: str
    source_tree: str
    total: int
    policy_passed: int
    rejected: list[Rejection]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_receipt(receipt: dict[str, Any]) -> bytes:
    """Return the canonical bytes whose SHA-256 addresses a receipt."""
    return _canonical_json(receipt)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _policy_sha256(config: SnapshotConfig) -> str:
    return _sha256(
        _canonical_json(
            {
                **POLICY,
                "max_files": config.max_files,
                "max_file_bytes": config.max_file_bytes,
                "max_total_bytes": config.max_total_bytes,
            }
        )
    )


def _run_git(config: SnapshotConfig, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        [config.git_bin, "--no-replace-objects", "-C", str(config.repo), *args],
        check=False,
        capture_output=True,
        text=not binary,
    )
    if result.returncode != 0:
        raise SnapshotRejected("git_command_failed")
    return result.stdout


def _fetch(config: SnapshotConfig) -> None:
    result = subprocess.run(
        [
            config.git_bin,
            "--no-replace-objects",
            "-C",
            str(config.repo),
            "fetch",
            "--no-tags",
            "--no-write-fetch-head",
            config.remote,
            FETCH_REFSPEC,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SnapshotRejected("fetch_failed")


def _validate_source_contract(config: SnapshotConfig) -> None:
    if (
        config.remote != "origin"
        or config.source_ref != DEFAULT_SOURCE_REF
        or config.source_prefix != DEFAULT_SOURCE_PREFIX
    ):
        raise SnapshotRejected("source_contract")


def _git_object_oid(kind: str, content: bytes, recorded_oid: str) -> str:
    object_bytes = f"{kind} {len(content)}\0".encode("ascii") + content
    if len(recorded_oid) == 40:
        return hashlib.sha1(object_bytes, usedforsecurity=False).hexdigest()
    if len(recorded_oid) == 64:
        return hashlib.sha256(object_bytes).hexdigest()
    raise SnapshotRejected(f"invalid_{kind}_oid")


def _read_git_object_bounded(
    config: SnapshotConfig,
    kind: str,
    recorded_oid: str,
    *,
    max_bytes: int,
) -> bytes:
    try:
        process = subprocess.Popen(
            [
                config.git_bin,
                "--no-replace-objects",
                "-C",
                str(config.repo),
                "cat-file",
                kind,
                recorded_oid,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise SnapshotRejected("git_command_failed")
    if process.stdout is None:
        process.wait()
        raise SnapshotRejected("git_command_failed")

    content = bytearray()
    too_large = False
    try:
        while chunk := process.stdout.read(
            min(OBJECT_READ_CHUNK_BYTES, max_bytes + 1 - len(content))
        ):
            content.extend(chunk)
            if len(content) > max_bytes:
                too_large = True
                break
    finally:
        process.stdout.close()
        return_code = process.wait()
    if too_large:
        raise SnapshotRejected(f"{kind}_too_large")
    if return_code != 0:
        raise SnapshotRejected("git_command_failed")
    return bytes(content)


def _read_verified_git_object(
    config: SnapshotConfig,
    kind: str,
    recorded_oid: str,
) -> bytes:
    max_bytes = {
        "commit": MAX_COMMIT_OBJECT_BYTES,
        "tree": MAX_TREE_OBJECT_BYTES,
    }.get(kind)
    if max_bytes is None:
        raise SnapshotRejected("invalid_object_kind")
    content = _read_git_object_bounded(
        config,
        kind,
        recorded_oid,
        max_bytes=max_bytes,
    )
    if _git_object_oid(kind, content, recorded_oid) != recorded_oid:
        raise SnapshotRejected(f"{kind}_oid_mismatch")
    return content


def _commit_root_tree_oid(commit: bytes, commit_oid: str) -> str:
    first_line, delimiter, _ = commit.partition(b"\n")
    if delimiter != b"\n" or not first_line.startswith(b"tree "):
        raise SnapshotRejected("invalid_commit_object")
    try:
        tree_oid = first_line.removeprefix(b"tree ").decode("ascii")
    except UnicodeDecodeError:
        raise SnapshotRejected("invalid_commit_object")
    if len(tree_oid) != len(commit_oid) or not GIT_OID_RE.fullmatch(tree_oid):
        raise SnapshotRejected("invalid_commit_object")
    return tree_oid


def _parse_git_tree(tree: bytes, tree_oid: str) -> list[GitTreeRecord]:
    if not GIT_OID_RE.fullmatch(tree_oid):
        raise SnapshotRejected("invalid_tree_oid")
    raw_oid_bytes = len(tree_oid) // 2
    records: list[GitTreeRecord] = []
    cursor = 0
    while cursor < len(tree):
        mode_end = tree.find(b" ", cursor)
        name_end = tree.find(b"\0", mode_end + 1)
        oid_start = name_end + 1
        oid_end = oid_start + raw_oid_bytes
        if mode_end <= cursor or name_end <= mode_end + 1 or oid_end > len(tree):
            raise SnapshotRejected("invalid_tree_object")
        records.append(
            GitTreeRecord(
                mode=tree[cursor:mode_end],
                name=tree[mode_end + 1 : name_end],
                oid=tree[oid_start:oid_end].hex(),
            )
        )
        cursor = oid_end
    if cursor != len(tree):
        raise SnapshotRejected("invalid_tree_object")
    return records


def _tree_child_oid(tree: bytes, tree_oid: str, component: str) -> str:
    wanted = component.encode("utf-8")
    matches = [record for record in _parse_git_tree(tree, tree_oid) if record.name == wanted]
    if len(matches) != 1 or matches[0].mode not in {b"40000", b"040000"}:
        raise SnapshotRejected("source_tree_missing")
    return matches[0].oid


def _resolve_source(config: SnapshotConfig, *, fetch: bool) -> tuple[str, str, bytes]:
    _validate_source_contract(config)
    if fetch:
        _fetch(config)
    commit = str(_run_git(config, "rev-parse", "--verify", config.source_ref)).strip()
    if not GIT_OID_RE.fullmatch(commit):
        raise SnapshotRejected("invalid_commit_oid")
    commit_content = _read_verified_git_object(config, "commit", commit)
    tree = _commit_root_tree_oid(commit_content, commit)
    for component in PurePosixPath(config.source_prefix).parts:
        tree_content = _read_verified_git_object(config, "tree", tree)
        tree = _tree_child_oid(tree_content, tree, component)
    tree_content = _read_verified_git_object(config, "tree", tree)
    return commit, tree, tree_content


def _git_object_size(config: SnapshotConfig, oid: str) -> int:
    raw_size = str(_run_git(config, "cat-file", "-s", oid)).strip()
    if len(raw_size) > 20 or not raw_size.isdecimal():
        raise SnapshotRejected("invalid_object_size")
    return int(raw_size)


def _tree_entries(
    config: SnapshotConfig,
    tree_oid: str,
    tree_content: bytes,
) -> list[TreeEntry]:
    entries: list[TreeEntry] = []
    prefix = f"{config.source_prefix}/"
    records = _parse_git_tree(tree_content, tree_oid)
    if len(records) > config.max_files:
        raise SnapshotRejected("too_many_files")
    for record in records:
        try:
            relative = record.name.decode("utf-8")
            mode = record.mode.decode("ascii")
        except UnicodeDecodeError:
            raise SnapshotRejected("invalid_tree_path")
        if record.mode in {b"40000", b"040000"}:
            kind = "tree"
        elif record.mode == b"160000":
            kind = "commit"
        else:
            kind = "blob"
        entries.append(
            TreeEntry(
                source_relpath=f"{prefix}{relative}",
                relative_path=relative,
                mode=mode,
                kind=kind,
                git_blob_oid=record.oid,
                size=_git_object_size(config, record.oid) if kind == "blob" else None,
            )
        )
    entries.sort(key=lambda entry: entry.source_relpath)
    return entries


def _secret_path(path: str) -> bool:
    candidate = PurePosixPath(path)
    return (
        candidate.stem.casefold() in SECRET_PATH_NAMES
        or candidate.name.casefold() in SECRET_PATH_NAMES
    )


def _validate_entry(config: SnapshotConfig, entry: TreeEntry) -> None:
    path = entry.relative_path
    if _detect_secret(path.encode("utf-8")):
        raise SnapshotRejected("secret_path")
    if not path or "/" in path or "\\" in path or path in {".", ".."}:
        raise SnapshotRejected("nested_path", path)
    if entry.kind == "tree":
        raise SnapshotRejected("nested_path", path)
    if entry.mode != "100644" or entry.kind != "blob":
        raise SnapshotRejected("forbidden_tree_entry", path)
    if PurePosixPath(path).suffix.casefold() not in ALLOWED_SUFFIXES:
        raise SnapshotRejected("unsupported_extension", path)
    if entry.size is None:
        raise SnapshotRejected("missing_blob_size", path)
    if entry.size > config.max_file_bytes:
        raise SnapshotRejected("file_too_large", path)
    if _secret_path(path):
        raise SnapshotRejected("secret_path", path)


def _detect_secret(data: bytes) -> str | None:
    for rule_id, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            return rule_id
    return None


def _detect_unstructured_text_secret(data: bytes) -> str | None:
    if rule_id := _detect_secret(data):
        return rule_id
    for rule_id, pattern in UNSTRUCTURED_TEXT_SECRET_PATTERNS:
        if pattern.search(data):
            return rule_id
    return None


def _json_escape_view(data: bytes) -> bytes:
    decoded = bytearray()
    index = 0
    while index < len(data):
        if data[index] != ord("\\") or index + 1 >= len(data):
            decoded.append(data[index])
            index += 1
            continue
        marker = data[index + 1]
        if marker in JSON_SIMPLE_ESCAPES:
            decoded.extend(JSON_SIMPLE_ESCAPES[marker])
            index += 2
            continue
        if marker != ord("u") or index + 6 > len(data):
            decoded.append(data[index])
            index += 1
            continue
        try:
            codepoint = int(data[index + 2 : index + 6], 16)
        except ValueError:
            decoded.append(data[index])
            index += 1
            continue
        consumed = 6
        if 0xD800 <= codepoint <= 0xDBFF and index + 12 <= len(data):
            following = data[index + 6 : index + 12]
            if following[:2] == b"\\u":
                try:
                    low = int(following[2:], 16)
                except ValueError:
                    low = -1
                if 0xDC00 <= low <= 0xDFFF:
                    codepoint = 0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00)
                    consumed = 12
        if 0xD800 <= codepoint <= 0xDFFF:
            decoded.extend(data[index : index + consumed])
        else:
            decoded.extend(chr(codepoint).encode("utf-8"))
        index += consumed
    return bytes(decoded)


def _yaml_hex_escape_view(data: bytes) -> bytes:
    decoded = bytearray()
    widths = {ord("x"): 2, ord("u"): 4, ord("U"): 8}
    index = 0
    while index < len(data):
        if data[index] != ord("\\") or index + 1 >= len(data):
            decoded.append(data[index])
            index += 1
            continue
        width = widths.get(data[index + 1])
        if width is None or index + 2 + width > len(data):
            decoded.append(data[index])
            index += 1
            continue
        end = index + 2 + width
        try:
            codepoint = int(data[index + 2 : end], 16)
        except ValueError:
            decoded.append(data[index])
            index += 1
            continue
        if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            decoded.extend(data[index:end])
        else:
            decoded.extend(chr(codepoint).encode("utf-8"))
        index = end
    return bytes(decoded)


def _detect_decoded_escape_secret(data: bytes) -> str | None:
    for view in (_json_escape_view, _yaml_hex_escape_view):
        if rule_id := _detect_unstructured_text_secret(view(data)):
            return rule_id
    return None


def _decode_utf8(data: bytes, path: str) -> str:
    if b"\0" in data:
        raise SnapshotRejected("binary_content", path)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise SnapshotRejected("invalid_utf8", path)


def _read_verified_blob(config: SnapshotConfig, entry: TreeEntry) -> bytes:
    blob = _read_git_object_bounded(
        config,
        "blob",
        entry.git_blob_oid,
        max_bytes=config.max_file_bytes,
    )
    if entry.size is None or len(blob) != entry.size:
        raise SnapshotRejected("blob_size_mismatch", entry.relative_path)
    if _git_object_oid("blob", blob, entry.git_blob_oid) != entry.git_blob_oid:
        raise SnapshotRejected("blob_oid_mismatch", entry.relative_path)
    return blob


def _normalized_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _structured_secret_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return normalized is not None and (
        normalized in STRUCTURED_SECRET_KEY_NAMES
        or any(normalized.endswith(suffix) for suffix in STRUCTURED_SECRET_KEY_SUFFIXES)
    )


def _validate_structure(
    value: Any,
    path: str,
    code: str,
    *,
    reject_aliases: bool = False,
) -> None:
    stack = [(value, 1)]
    seen_containers: set[int] = set()
    visited = 0
    while stack:
        current, depth = stack.pop()
        visited += 1
        if visited > MAX_STRUCTURED_NODES or depth > MAX_STRUCTURED_DEPTH:
            raise SnapshotRejected(code, path)
        if isinstance(current, dict | list):
            identity = id(current)
            if identity in seen_containers:
                if reject_aliases:
                    raise SnapshotRejected(code, path)
                continue
            seen_containers.add(identity)
        if isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str):
                    raise SnapshotRejected(code, path)
                if _structured_secret_key(key):
                    raise SnapshotRejected("structured_secret_key", path)
                try:
                    encoded_key = key.encode("utf-8")
                except UnicodeEncodeError:
                    raise SnapshotRejected(code, path)
                if _detect_secret(encoded_key):
                    raise SnapshotRejected("secret_detected", path)
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            try:
                encoded = current.encode("utf-8")
            except UnicodeEncodeError:
                raise SnapshotRejected(code, path)
            if _detect_unstructured_text_secret(encoded) or _detect_decoded_escape_secret(encoded):
                raise SnapshotRejected("secret_detected", path)
        elif isinstance(current, bytes):
            if _detect_secret(current):
                raise SnapshotRejected("secret_detected", path)
            raise SnapshotRejected(code, path)
        elif (
            current is None
            or type(current) in {bool, int, date}
            or (isinstance(current, float) and math.isfinite(current))
        ):
            continue
        else:
            raise SnapshotRejected(code, path)


def _validate_provenance(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise SnapshotRejected("frontmatter_not_mapping", path)
    for key in REQUIRED_PROVENANCE:
        field = value.get(key)
        if field is None or (isinstance(field, str) and not field.strip()):
            raise SnapshotRejected(f"missing_{key}", path)
        if key == "date":
            if isinstance(field, str):
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", field):
                    raise SnapshotRejected("invalid_date", path)
                try:
                    date.fromisoformat(field)
                except ValueError:
                    raise SnapshotRejected("invalid_date", path)
            elif type(field) is not date:
                raise SnapshotRejected("invalid_date", path)
        elif not isinstance(field, str):
            raise SnapshotRejected(f"invalid_{key}", path)


def _reject_json_constant(_: str) -> Any:
    raise ValueError


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        self.flatten_mapping(node)
        result: dict[Any, Any] = {}
        for key, value in self.construct_pairs(node, deep=deep):
            try:
                duplicate = key in result
            except TypeError as exc:
                raise ValueError from exc
            if duplicate:
                raise ValueError
            result[key] = value
        return result


def _validate_content(path: str, data: bytes) -> str:
    if _detect_secret(data):
        raise SnapshotRejected("secret_detected", path)
    text = _decode_utf8(data, path)
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix == ".md":
        match = FRONTMATTER_RE.match(text)
        if not match:
            raise SnapshotRejected("missing_frontmatter", path)
        if _detect_decoded_escape_secret(text[match.end() :].encode("utf-8")):
            raise SnapshotRejected("secret_detected", path)
        try:
            value = yaml.load(match.group("body"), Loader=_UniqueKeySafeLoader)
        except (yaml.YAMLError, ValueError, RecursionError):
            raise SnapshotRejected("invalid_yaml", path)
        _validate_structure(value, path, "invalid_yaml", reject_aliases=True)
        _validate_provenance(value, path)
        return "text/markdown"
    if suffix == ".json":
        try:
            value = json.loads(
                text,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_reject_duplicate_json_pairs,
            )
        except (json.JSONDecodeError, ValueError, RecursionError):
            raise SnapshotRejected("invalid_json", path)
        _validate_structure(value, path, "invalid_json")
        _validate_provenance(value, path)
        return "application/json"
    raise SnapshotRejected("unsupported_extension", path)


def _read_policy_checked_file(config: SnapshotConfig, entry: TreeEntry) -> PolicyCheckedFile:
    _validate_entry(config, entry)
    blob = _read_verified_blob(config, entry)
    media_type = _validate_content(entry.relative_path, blob)
    return PolicyCheckedFile(
        source_relpath=entry.source_relpath,
        relative_path=entry.relative_path,
        git_blob_oid=entry.git_blob_oid,
        sha256=_sha256(blob),
        size=len(blob),
        media_type=media_type,
    )


def _validate_excluded_metadata(config: SnapshotConfig, entry: TreeEntry) -> None:
    path = entry.relative_path
    if path not in EXCLUDED_NAMES:
        raise SnapshotRejected("metadata_contract", path)
    if entry.mode != "100644" or entry.kind != "blob":
        raise SnapshotRejected("forbidden_tree_entry", path)
    if entry.size is None:
        raise SnapshotRejected("missing_blob_size", path)
    if entry.size > config.max_file_bytes:
        raise SnapshotRejected("file_too_large", path)
    blob = _read_verified_blob(config, entry)
    if _detect_secret(blob):
        raise SnapshotRejected("secret_detected", path)
    text = _decode_utf8(blob, path)
    if _detect_decoded_escape_secret(text.encode("utf-8")):
        raise SnapshotRejected("secret_detected", path)
    if PurePosixPath(path).suffix.casefold() == ".json":
        try:
            value = json.loads(
                text,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_reject_duplicate_json_pairs,
            )
        except (json.JSONDecodeError, ValueError, RecursionError):
            raise SnapshotRejected("invalid_json", path)
        _validate_structure(value, path, "invalid_json")
    elif match := FRONTMATTER_RE.match(text):
        try:
            value = yaml.load(match.group("body"), Loader=_UniqueKeySafeLoader)
        except (yaml.YAMLError, ValueError, RecursionError):
            raise SnapshotRejected("invalid_yaml", path)
        _validate_structure(value, path, "invalid_yaml", reject_aliases=True)


def _validate_aliases(files: list[PolicyCheckedFile]) -> None:
    seen: dict[str, str] = {}
    for item in files:
        key = unicodedata.normalize("NFC", item.relative_path).casefold()
        if key in seen:
            raise SnapshotRejected("path_alias", item.relative_path)
        seen[key] = item.relative_path


def _validate_limits(config: SnapshotConfig, entries: list[TreeEntry]) -> None:
    if len(entries) > config.max_files:
        raise SnapshotRejected("too_many_files")
    total = sum(entry.size or 0 for entry in entries)
    if total > config.max_total_bytes:
        raise SnapshotRejected("source_too_large")


def _policy_checked_files(
    config: SnapshotConfig,
    tree_oid: str,
    tree_content: bytes,
) -> list[PolicyCheckedFile]:
    entries = _tree_entries(config, tree_oid, tree_content)
    if not entries:
        raise SnapshotRejected("empty_source")
    _validate_limits(config, entries)
    metadata = [entry for entry in entries if entry.relative_path in EXCLUDED_NAMES]
    exports = [entry for entry in entries if entry.relative_path not in EXCLUDED_NAMES]
    for entry in metadata:
        _validate_excluded_metadata(config, entry)
    if not exports:
        raise SnapshotRejected("empty_source")
    files = [_read_policy_checked_file(config, entry) for entry in exports]
    _validate_aliases(files)
    return files


def _file_receipt(item: PolicyCheckedFile) -> dict[str, Any]:
    return {
        "source_relpath": item.source_relpath,
        "git_blob_oid": item.git_blob_oid,
        "sha256": item.sha256,
        "bytes": item.size,
        "media_type": item.media_type,
        "policy_profile": POLICY_PROFILE,
    }


def _build_receipt(
    config: SnapshotConfig,
    commit: str,
    tree: str,
    files: list[PolicyCheckedFile],
) -> dict[str, Any]:
    receipt_files = [_file_receipt(item) for item in files]
    manifest_sha = _sha256(_canonical_json(receipt_files))
    return {
        "schema": SCHEMA_NAME,
        "validator": {
            "name": VALIDATOR_NAME,
            "version": VALIDATOR_VERSION,
            "policy_profile": POLICY_PROFILE,
            "policy_sha256": _policy_sha256(config),
        },
        "source": {
            "remote": config.remote,
            "requested_ref": config.source_ref,
            "commit_oid": commit,
            "tree_oid": tree,
            "tree_prefix": config.source_prefix,
        },
        "content_manifest_sha256": manifest_sha,
        "files": receipt_files,
        "summary": {
            "files": len(receipt_files),
            "bytes": sum(item.size for item in files),
        },
    }


def snapshot_exports(
    config: SnapshotConfig,
    *,
    fetch: bool = False,
) -> SnapshotResult:
    """Apply the bounded policy to one immutable source and return its receipt."""
    commit, tree, tree_content = _resolve_source(config, fetch=fetch)
    files = _policy_checked_files(config, tree, tree_content)
    receipt = _build_receipt(config, commit, tree, files)
    receipt_bytes = canonical_receipt(receipt)
    receipt_sha = _sha256(receipt_bytes)
    return SnapshotResult(
        source_commit=commit,
        source_tree=tree,
        receipt_sha256=receipt_sha,
        receipt=receipt,
    )


def inventory_exports(config: SnapshotConfig, *, fetch: bool = False) -> InventoryResult:
    """Return only paths and stable rejection codes; never content or content hashes."""
    commit, tree, tree_content = _resolve_source(config, fetch=fetch)
    entries = _tree_entries(config, tree, tree_content)
    if not entries:
        raise SnapshotRejected("empty_source")
    _validate_limits(config, entries)
    metadata = [entry for entry in entries if entry.relative_path in EXCLUDED_NAMES]
    entries = [entry for entry in entries if entry.relative_path not in EXCLUDED_NAMES]
    for entry in metadata:
        _validate_excluded_metadata(config, entry)
    if not entries:
        raise SnapshotRejected("empty_source")
    policy_checked: list[PolicyCheckedFile] = []
    rejected: list[Rejection] = []
    for entry in entries:
        try:
            policy_checked.append(_read_policy_checked_file(config, entry))
        except SnapshotRejected as exc:
            rejected.append(Rejection(path=exc.path or SECRET_PATH_REDACTION, code=exc.code))

    by_alias: dict[str, list[PolicyCheckedFile]] = {}
    for item in policy_checked:
        key = unicodedata.normalize("NFC", item.relative_path).casefold()
        by_alias.setdefault(key, []).append(item)
    policy_passed = 0
    for items in by_alias.values():
        if len(items) == 1:
            policy_passed += 1
        else:
            rejected.extend(Rejection(path=item.relative_path, code="path_alias") for item in items)
    rejected.sort(key=lambda item: (item.path, item.code))
    return InventoryResult(
        source_commit=commit,
        source_tree=tree,
        total=len(entries),
        policy_passed=policy_passed,
        rejected=rejected,
    )


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=root)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--inventory", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = SnapshotConfig(repo=args.repo)
    try:
        if args.inventory:
            inventory = inventory_exports(config, fetch=args.fetch)
            payload = {"policy_ok": not inventory.rejected, **asdict(inventory)}
        else:
            result = snapshot_exports(config, fetch=args.fetch)
            payload = {
                "policy_ok": True,
                "source_commit": result.source_commit,
                "source_tree": result.source_tree,
                "receipt_sha256": result.receipt_sha256,
                "receipt": result.receipt,
            }
    except SnapshotRejected as exc:
        print(
            json.dumps(
                {"policy_ok": False, "error": exc.code, "path": exc.path},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 3 if args.inventory and payload["rejected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
