"""Optimism protocol registry — typed accessor over ``config/optimism_protocols.yaml``.

Exact same shape as :mod:`lib.chains.arbitrum.registry`. The split is
deliberate so each chain owns its own yaml — adding a protocol to one
chain doesn't touch the other's source of truth.

Wave 1 populates ``aave_v3`` only. Future protocols (e.g. Velodrome,
Synthetix, Beethoven) extend the same yaml in follow-up PRs.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import yaml

#: Default location of the registry yaml. Overridable in tests.
DEFAULT_REGISTRY_PATH = (
    pathlib.Path(__file__).resolve().parents[3] / "config" / "optimism_protocols.yaml"
)


@dataclass(frozen=True)
class ProtocolEntry:
    """One protocol's deployment metadata.

    ``addresses`` and ``abi_paths`` are role-keyed (e.g. ``"pool"``,
    ``"oracle"``) so callers don't need to know about ABI file naming.
    """

    name: str
    key: str
    category: str
    priority: int
    status: str
    docs_url: str
    addresses: dict[str, str] = field(default_factory=dict)
    abi_paths: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def address(self, role: str) -> str:
        try:
            return self.addresses[role]
        except KeyError as exc:
            raise KeyError(
                f"protocol {self.key!r} has no address for role {role!r}; "
                f"known roles: {sorted(self.addresses)}"
            ) from exc

    def abi_path(self, role: str) -> str:
        try:
            return self.abi_paths[role]
        except KeyError as exc:
            raise KeyError(
                f"protocol {self.key!r} has no ABI path for role {role!r}; "
                f"known roles: {sorted(self.abi_paths)}"
            ) from exc


class ProtocolRegistry:
    """In-memory typed view of ``config/optimism_protocols.yaml``."""

    def __init__(self, entries: dict[str, ProtocolEntry]) -> None:
        self._entries: dict[str, ProtocolEntry] = dict(entries)

    @classmethod
    def from_yaml(cls, path: pathlib.Path | str | None = None) -> ProtocolRegistry:
        path = pathlib.Path(path) if path is not None else DEFAULT_REGISTRY_PATH
        if not path.exists():
            raise FileNotFoundError(f"protocol registry not found: {path}")
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"protocol registry root must be a mapping, got {type(raw).__name__}")
        entries: dict[str, ProtocolEntry] = {}
        for key, payload in raw.items():
            entries[key] = cls._entry_from_dict(key, payload)
        return cls(entries)

    @staticmethod
    def _entry_from_dict(key: str, payload: dict[str, Any]) -> ProtocolEntry:
        if not isinstance(payload, dict):
            raise ValueError(f"protocol {key!r} payload must be a mapping")
        return ProtocolEntry(
            key=key,
            name=str(payload.get("name", key)),
            category=str(payload.get("category", "unknown")),
            priority=int(payload.get("priority", 3)),
            status=str(payload.get("status", "active")),
            docs_url=str(payload.get("docs_url", "")),
            addresses={k: str(v) for k, v in (payload.get("addresses") or {}).items()},
            abi_paths={k: str(v) for k, v in (payload.get("abi_paths") or {}).items()},
            notes=str(payload.get("notes") or ""),
        )

    # ---- read API ---------------------------------------------------------

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self._entries

    def __iter__(self) -> Iterator[ProtocolEntry]:
        return iter(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> ProtocolEntry:
        try:
            return self._entries[key]
        except KeyError as exc:
            raise KeyError(
                f"unknown protocol {key!r}; registered: {sorted(self._entries)}"
            ) from exc

    def list_protocols(self) -> list[ProtocolEntry]:
        """Stable-ordered list of all entries (priority asc, then key)."""
        return sorted(self._entries.values(), key=lambda e: (e.priority, e.key))

    def by_category(self, category: str) -> list[ProtocolEntry]:
        return [e for e in self._entries.values() if e.category == category]
