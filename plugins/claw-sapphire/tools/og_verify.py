"""og_verify — verify a Sapphire signal end-to-end against 0G state.

stdin JSON (one of):
    {"signal_id": 42}                    // look up by on-chain id
    {"root_hash": "0x..."}               // verify by storage root only

stdout JSON:
    {
        "ok": true,
        "on_chain": { ... }              // SapphireSignalVerifier.signals(id)
        "blob": { ... }                  // decoded envelope
        "verified": {
            "merkle_proof": true,        // 0G Storage download with verify=true succeeded
            "envelope_hash_matches_chain": true   // proofHash == merkle root
        }
    }

Behavior:
- Only requires read access to 0G; no signing key needed.
- Caller is responsible for the optional TEE chatID re-verify, since that
  needs the operator's broker session. We surface the chatID in the output
  so a follow-up tool can call broker.inference.processResponse().
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lib.og.chain import get_signal  # noqa: E402
from lib.og.storage import download  # noqa: E402


def _read_request() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("og_verify: empty stdin; expected a JSON payload")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"og_verify: invalid JSON on stdin: {exc}") from exc


def main() -> None:
    try:
        req = _read_request()
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

    network = req.get("network")
    on_chain: dict | None = None
    target_root: str | None = None

    if "signal_id" in req and req["signal_id"] is not None:
        try:
            on_chain = get_signal(int(req["signal_id"]), network=network)
            target_root = on_chain["proof_root_hash"]
        except Exception as exc:
            print(json.dumps({"ok": False, "stage": "chain_read", "error": str(exc)}))
            sys.exit(2)
    elif req.get("root_hash"):
        target_root = str(req["root_hash"])
    else:
        print(json.dumps({"ok": False, "error": "must provide signal_id or root_hash"}))
        sys.exit(1)

    if not target_root or not target_root.startswith("0x") or len(target_root) != 66:
        print(json.dumps({"ok": False, "error": f"invalid root hash: {target_root}"}))
        sys.exit(1)

    # The 0G SDK's `indexer.download()` refuses any output path that already
    # exists ("Wrong path, provide a file path which does not exist."). So
    # we hand it a fresh subpath inside a tmp directory rather than a
    # NamedTemporaryFile (which materialises the file on creation). The
    # TemporaryDirectory cleans up the whole directory tree on exit.
    with tempfile.TemporaryDirectory(prefix="og_verify_") as tmpdir:
        tmp_path = Path(tmpdir) / "blob"
        try:
            download(target_root, tmp_path, verify=True, network=network)
            merkle_ok = True
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "stage": "storage_download",
                        "root_hash": target_root,
                        "error": str(exc),
                    }
                )
            )
            sys.exit(3)

        try:
            envelope = json.loads(tmp_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "stage": "blob_decode",
                        "root_hash": target_root,
                        "error": str(exc),
                    }
                )
            )
            sys.exit(4)

    output: dict = {
        "ok": True,
        "blob": envelope,
        "verified": {
            "merkle_proof": merkle_ok,
            "envelope_hash_matches_chain": on_chain is not None,
        },
    }
    if on_chain is not None:
        output["on_chain"] = on_chain
    print(json.dumps(output))


if __name__ == "__main__":
    main()
