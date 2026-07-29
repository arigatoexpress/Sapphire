"""Owner-private, content-addressed incident envelopes for Foundry sync.

This module is deliberately transport-free.  It records a bounded failure
class, configuration generation, and lifecycle transition without persisting
raw exception text, credentials, URLs, or caller-authored notification prose.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

_CONFIG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_ERROR_CLASSES = {
    "foundry_auth_401",
    "foundry_auth_403",
    "foundry_target_404",
    "foundry_timeout",
    "foundry_dns",
    "foundry_server_5xx",
    "foundry_other",
}
_IDENTITY_SCHEMA = "sapphire.foundry_incident_identity.v1"
_ENVELOPE_SCHEMA = "sapphire.foundry_incident.v1"
_STATE_SCHEMA = "sapphire.foundry_incident_state.v1"
_MAX_FILE_BYTES = 1024 * 1024
_MAX_TIMESTAMP_BYTES = 64


class FoundryIncidentError(RuntimeError):
    """The local incident boundary could not be maintained safely."""


def _canonical(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count < 1:
            raise FoundryIncidentError("incident file write was incomplete")
        written += count


def _valid_timestamp(value: str) -> str:
    if (
        type(value) is not str
        or len(value.encode("utf-8")) > _MAX_TIMESTAMP_BYTES
    ):
        raise FoundryIncidentError("incident timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FoundryIncidentError("incident timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FoundryIncidentError("incident timestamp must be timezone-aware")
    return value


def _owner_private_bytes(root: Path, path: Path) -> bytes:
    """Read one direct child through stable, owner-private descriptors."""

    if path.parent != root:
        raise FoundryIncidentError("incident file path is invalid")
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise FoundryIncidentError("incident file primitives are unavailable")
    root_fd: int | None = None
    file_fd: int | None = None
    try:
        root_fd = os.open(
            root,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        root_info = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_uid != os.getuid()
            or root_info.st_mode & 0o077
        ):
            raise FoundryIncidentError("incident outbox is not owner-private")
        file_fd = os.open(
            path.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=root_fd,
        )
        before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_mode & 0o077
            or before.st_nlink != 1
            or before.st_size > _MAX_FILE_BYTES
        ):
            raise FoundryIncidentError("incident file is not owner-private")
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(file_fd, min(65536, _MAX_FILE_BYTES + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > _MAX_FILE_BYTES:
                raise FoundryIncidentError("incident file is too large")
        after = os.fstat(file_fd)
        identity = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(getattr(before, field) != getattr(after, field) for field in identity):
            raise FoundryIncidentError("incident file changed during read")
        return b"".join(chunks)
    except FoundryIncidentError:
        raise
    except (OSError, AttributeError) as exc:
        raise FoundryIncidentError("incident file is unavailable") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if root_fd is not None:
            os.close(root_fd)


def classify_failure(errors: list[str]) -> str:
    """Map raw failures to one bounded class; raw text is never persisted."""

    if type(errors) is not list or not all(type(item) is str for item in errors):
        raise FoundryIncidentError("incident errors are invalid")
    text = " ".join(errors).lower()
    if re.search(r"(?:returned|status|http)?\s*401\b|unauthori[sz]ed", text):
        return "foundry_auth_401"
    if re.search(r"(?:returned|status|http)?\s*403\b|forbidden", text):
        return "foundry_auth_403"
    if re.search(r"(?:returned|status|http)?\s*404\b|not found|missing", text):
        return "foundry_target_404"
    if "timed out" in text or "timeout" in text:
        return "foundry_timeout"
    if any(
        marker in text
        for marker in (
            "nodename nor servname",
            "name or service not known",
            "temporary failure in name resolution",
            "dns",
        )
    ):
        return "foundry_dns"
    if re.search(r"(?:returned|status|http)?\s*5\d\d\b", text):
        return "foundry_server_5xx"
    return "foundry_other"


class FoundryIncidentOutbox:
    """Maintain one deduplicated incident lifecycle in an owner-private outbox."""

    __slots__ = ("root", "_config_generation", "_state_path")

    def __init__(self, *, root: Path, config_generation: str) -> None:
        if (
            not isinstance(root, Path)
            or type(config_generation) is not str
            or _CONFIG_RE.fullmatch(config_generation) is None
        ):
            raise FoundryIncidentError("incident outbox configuration is invalid")
        self.root = root.expanduser().absolute()
        self._config_generation = config_generation
        self._state_path = self.root / "state.json"
        self._prepare_root()

    def _prepare_root(self) -> None:
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = self.root.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                raise FoundryIncidentError("incident outbox is not owner-private")
        except FoundryIncidentError:
            raise
        except (OSError, AttributeError) as exc:
            raise FoundryIncidentError("incident outbox is unavailable") from exc

    def _read_state(self) -> dict[str, Any] | None:
        if not self._state_path.exists() and not self._state_path.is_symlink():
            return None
        try:
            raw = _owner_private_bytes(self.root, self._state_path)
            state = json.loads(raw.decode("utf-8"))
        except FoundryIncidentError:
            raise
        except Exception as exc:
            raise FoundryIncidentError("incident state is invalid") from exc
        if type(state) is not dict or state.get("schema_version") != _STATE_SCHEMA:
            raise FoundryIncidentError("incident state schema is invalid")
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        temporary = self.root / f".state.{os.getpid()}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = os.open(temporary, flags, 0o600)
            raw = _canonical(state)
            _write_all(descriptor, raw)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            temporary.replace(self._state_path)
        except Exception as exc:
            raise FoundryIncidentError("incident state could not be committed") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _incident_identity(self, error_class: str) -> str:
        identity = {
            "config_generation": self._config_generation,
            "error_class": error_class,
            "schema_version": _IDENTITY_SCHEMA,
            "subsystem": "foundry_sync",
        }
        return hashlib.sha256(_canonical(identity).rstrip(b"\n")).hexdigest()

    def _write_envelope(self, envelope: dict[str, Any]) -> Path:
        raw = _canonical(envelope)
        digest = hashlib.sha256(raw).hexdigest()
        path = self.root / f"{digest}.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            if _owner_private_bytes(self.root, path) != raw:
                raise FoundryIncidentError("incident digest collision")
            return path
        except OSError as exc:
            raise FoundryIncidentError("incident envelope could not be created") from exc
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
        except OSError as exc:
            raise FoundryIncidentError("incident envelope could not be committed") from exc
        finally:
            os.close(descriptor)
        return path

    def observe_failure(self, errors: list[str], *, observed_at: str) -> Path | None:
        """Open a new incident or increment the current matching incident."""

        observed_at = _valid_timestamp(observed_at)
        error_class = classify_failure(errors)
        if error_class not in _ERROR_CLASSES:
            raise FoundryIncidentError("incident class is invalid")
        incident_id = self._incident_identity(error_class)
        state = self._read_state()
        if (
            state is not None
            and state.get("status") == "open"
            and state.get("incident_id") == incident_id
        ):
            occurrences = state.get("occurrences")
            if type(occurrences) is not int or occurrences < 1:
                raise FoundryIncidentError("incident occurrence state is invalid")
            state["occurrences"] = occurrences + 1
            state["last_observed_at"] = observed_at
            self._write_state(state)
            return None

        envelope = {
            "config_generation": self._config_generation,
            "error_class": error_class,
            "event": "opened",
            "incident_id": incident_id,
            "observed_at": observed_at,
            "schema_version": _ENVELOPE_SCHEMA,
            "subsystem": "foundry_sync",
        }
        path = self._write_envelope(envelope)
        self._write_state(
            {
                "config_generation": self._config_generation,
                "error_class": error_class,
                "first_observed_at": observed_at,
                "incident_id": incident_id,
                "last_observed_at": observed_at,
                "occurrences": 1,
                "schema_version": _STATE_SCHEMA,
                "status": "open",
            }
        )
        return path

    def observe_recovery(self, *, observed_at: str) -> Path | None:
        """Close the current incident once; a healthy state emits nothing."""

        observed_at = _valid_timestamp(observed_at)
        state = self._read_state()
        if state is None or state.get("status") != "open":
            return None
        incident_id = state.get("incident_id")
        error_class = state.get("error_class")
        occurrences = state.get("occurrences")
        config_generation = state.get("config_generation")
        if (
            type(incident_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", incident_id) is None
            or error_class not in _ERROR_CLASSES
            or type(occurrences) is not int
            or occurrences < 1
            or type(config_generation) is not str
            or _CONFIG_RE.fullmatch(config_generation) is None
        ):
            raise FoundryIncidentError("open incident state is invalid")
        envelope = {
            "config_generation": config_generation,
            "error_class": error_class,
            "event": "recovered",
            "incident_id": incident_id,
            "observed_at": observed_at,
            "occurrences": occurrences,
            "schema_version": _ENVELOPE_SCHEMA,
            "subsystem": "foundry_sync",
        }
        path = self._write_envelope(envelope)
        state["last_observed_at"] = observed_at
        state["status"] = "healthy"
        self._write_state(state)
        return path


__all__ = [
    "FoundryIncidentError",
    "FoundryIncidentOutbox",
    "classify_failure",
]
