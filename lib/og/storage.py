"""0G Storage facade — content-addressed blob upload/download.

Subprocess bridge to `lib/og/_ts/og_storage.mjs`, which wraps the official
`@0gfoundation/0g-ts-sdk`. We do not reimplement the merkle/tree protocol in
Python; we delegate to the SDK that the 0G team maintains.

Why a subprocess and not pyo3/grpc? The 0G TypeScript SDK is the canonical
client. A 30-line Node bridge that prints one JSON line is the cheapest way
to track upstream changes without forking a Python port.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from lib.og.config import ENV_PRIVATE_KEY, network_config

_HELPER_DIR = Path(__file__).parent / "_ts"
_HELPER_SCRIPT = _HELPER_DIR / "og_storage.mjs"


class OGStorageError(RuntimeError):
    """Anything that goes wrong inside the Node bridge."""


@dataclass(frozen=True)
class UploadResult:
    root_hash: str
    tx_hash: str

    def explorer_url(self, network: str | None = None) -> str:
        cfg = network_config(network)
        return f"{cfg.explorer_url}/tx/{self.tx_hash}"


def _run_helper(subcommand: str, payload: dict, *, network: str | None = None) -> dict:
    cfg = network_config(network)
    if not _HELPER_SCRIPT.exists():
        raise OGStorageError(
            f"0G helper not found at {_HELPER_SCRIPT}. "
            "Did you run `cd lib/og/_ts && npm install` and ensure the file is checked in?"
        )

    env = os.environ.copy()
    env["OG_RPC_URL"] = cfg.rpc_url
    env["OG_INDEXER_URL"] = cfg.indexer_url

    if subcommand in {"upload", "uploadMem"} and ENV_PRIVATE_KEY not in env:
        raise OGStorageError(
            f"{ENV_PRIVATE_KEY} must be set in the environment to upload to 0G Storage"
        )

    proc = subprocess.run(
        ["node", str(_HELPER_SCRIPT), subcommand, json.dumps(payload)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
    )

    out = proc.stdout.strip().splitlines()
    last_line = out[-1] if out else ""
    try:
        result = json.loads(last_line) if last_line else {}
    except json.JSONDecodeError as exc:
        raise OGStorageError(
            f"could not parse helper output: {exc}\nstdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
        ) from exc

    if proc.returncode != 0 or "error" in result:
        msg = result.get("error") or proc.stderr or "unknown helper error"
        raise OGStorageError(msg)

    return result


def upload_file(path: str | Path, *, network: str | None = None) -> UploadResult:
    """Upload a file from disk; return the merkle root and tx hash."""
    abs_path = str(Path(path).expanduser().resolve())
    result = _run_helper("upload", {"path": abs_path}, network=network)
    return UploadResult(root_hash=result["rootHash"], tx_hash=result.get("txHash", ""))


def upload_bytes(data: bytes | str, *, network: str | None = None) -> UploadResult:
    """Upload an in-memory blob. `data` may be bytes or str (utf-8)."""
    payload = data.decode("utf-8") if isinstance(data, bytes) else data
    result = _run_helper("uploadMem", {"data": payload}, network=network)
    return UploadResult(root_hash=result["rootHash"], tx_hash=result.get("txHash", ""))


def upload_json(obj: object, *, network: str | None = None) -> UploadResult:
    """Convenience: serialize a Python object to JSON and upload."""
    return upload_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":")), network=network)


def download(
    root_hash: str, output_path: str | Path, *, verify: bool = True, network: str | None = None
) -> Path:
    """Download a file by merkle root, optionally verifying with merkle proof."""
    abs_out = Path(output_path).expanduser().resolve()
    abs_out.parent.mkdir(parents=True, exist_ok=True)
    _run_helper(
        "download",
        {"rootHash": root_hash, "outputPath": str(abs_out), "verify": verify},
        network=network,
    )
    return abs_out
