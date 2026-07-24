"""Arbiscan v1 ABI fetcher with on-disk cache + EIP-1967 proxy follow.

Arbiscan exposes the Etherscan-compatible v1 API at
``https://api.arbiscan.io/api``. We use the ``contract.getabi`` action::

    GET https://api.arbiscan.io/api?module=contract&action=getabi&address={addr}[&apikey=KEY]

Response shape (verified live 2026-04-30 with the public key-less endpoint):

    {
        "status": "1",                       # "1" = success, "0" = failure
        "message": "OK",                     # or "NOTOK"
        "result": "[{...JSON ABI string...}]"   # ABI is a JSON-encoded STRING
    }

Failure cases we handle gracefully:

    * Unverified contract: ``result == "Contract source code not verified"``
      (note: ``status == "0"`` in this case).
    * Rate-limited: ``status == "0"``, ``result`` is a wordy explanation.
    * Bad address: ``status == "0"``, ``result`` describes the parse error.

For EIP-1967 proxies, Arbiscan returns the proxy's thin ABI (``admin``,
``implementation``, ``upgradeTo``...) and provides no direct
``implementations`` link. Caller resolves the impl by reading the
EIP-1967 implementation slot via ``eth_getStorageAt`` (out of scope for
this module) — for our pinned use we follow the manual-source path:
fetch the impl address out of band and fetch its ABI directly.

ABIs are cached at ``lib/chains/arbitrum/abis/_cache/<lowercased>.json``
with a sidecar ``<lowercased>.meta.json`` describing provenance.

Network is **never** invoked from unit tests — every test injects a
fake httpx-shaped client (``DummyResponse``).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
from typing import Any

CHAIN_ID = 42161  # Arbitrum One
DEFAULT_ARBISCAN_API = os.getenv(
    "SAPPHIRE_ARBITRUM_ARBISCAN_API",
    "https://api.arbiscan.io/api",
)

#: Optional API key. Arbiscan permits ~5 calls/sec key-less; with a key
#: rate limits relax. Sapphire pin workflow is bursty (one-off pin), so
#: key is optional. Reads from env to avoid baking secrets into source.
ARBISCAN_API_KEY = os.getenv("SAPPHIRE_ARBISCAN_API_KEY", "")

#: Anyone wanting a different on-disk cache root can pass `cache_dir=`
#: to :func:`fetch_abi` directly; the default keeps everything inside
#: the package so checked-in ABIs travel with the source.
DEFAULT_CACHE_DIR = pathlib.Path(__file__).parent / "_cache"

#: Sentinel returned by Arbiscan when the address has no verified source.
UNVERIFIED_RESULT = "Contract source code not verified"


class AbiFetchError(RuntimeError):
    """Raised when Arbiscan returns no ABI for a given address."""


def _utcnow() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _abi_hash(abi: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(abi, sort_keys=True).encode()).hexdigest()


def _normalize_address(address: str) -> str:
    if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
        raise AbiFetchError(f"invalid address: {address!r}")
    return address.lower()


def _cache_paths(address: str, cache_dir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    addr = _normalize_address(address)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{addr}.json", cache_dir / f"{addr}.meta.json"


def _load_cached(address: str, cache_dir: pathlib.Path) -> dict[str, Any] | None:
    abi_path, meta_path = _cache_paths(address, cache_dir)
    if not abi_path.exists() or not meta_path.exists():
        return None
    try:
        return {
            "abi": json.loads(abi_path.read_text(encoding="utf-8")),
            "meta": json.loads(meta_path.read_text(encoding="utf-8")),
        }
    except (json.JSONDecodeError, OSError):
        return None


def _http_get_json(url: str, *, http_client: Any | None) -> dict[str, Any]:
    """Issue a GET and return parsed JSON.

    ``http_client`` may be:
      * an ``httpx.Client`` (sync) — the production path
      * a callable ``url -> dict`` — the test injection path
      * ``None`` — late-import httpx and use it
    """
    if callable(http_client) and not hasattr(http_client, "get"):
        return http_client(url)  # type: ignore[no-any-return]

    if http_client is None:
        import httpx  # noqa: PLC0415 — late import — keep httpx optional

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()

    response = http_client.get(url)
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise AbiFetchError(f"non-dict response body: {body!r}")
    return body


def _build_url(api_base: str, address: str, api_key: str = "") -> str:
    addr = _normalize_address(address)
    base = api_base.rstrip("?&/")
    url = f"{base}?module=contract&action=getabi&address={addr}"
    if api_key:
        url += f"&apikey={api_key}"
    return url


def fetch_abi(
    address: str,
    *,
    api_base: str = DEFAULT_ARBISCAN_API,
    api_key: str = ARBISCAN_API_KEY,
    force: bool = False,
    cache_dir: pathlib.Path = DEFAULT_CACHE_DIR,
    http_client: Any | None = None,
) -> dict[str, Any]:
    """Return the ABI + provenance metadata for ``address``.

    Returns a dict shaped::

        {
            "abi": [<json abi>],
            "meta": {
                "chain_id": 42161,
                "address": "0x..." (lowercased),
                "abi_hash_sha256": str,
                "fetched_at": "<iso>",
                "source": "arbiscan",
            },
        }

    Behavior:
      * If a cached file exists and ``force=False``, returns the cache.
      * Otherwise hits Arbiscan, writes both files, and returns fresh.

    :raises AbiFetchError: if the address isn't verified on Arbiscan
        and no usable ABI can be assembled.
    """
    addr = _normalize_address(address)

    if not force:
        cached = _load_cached(addr, cache_dir)
        if cached is not None and cached["abi"]:
            return cached

    url = _build_url(api_base, addr, api_key)
    body = _http_get_json(url, http_client=http_client)

    status = str(body.get("status", ""))
    result = body.get("result", "")
    message = str(body.get("message", ""))

    if status != "1":
        # Arbiscan returns ``"Contract source code not verified"`` for the
        # unverified case AND for plain bad-input cases ("Invalid Address
        # format"). We surface both via ``AbiFetchError`` so the caller
        # can fall back to a hand-curated ABI.
        if isinstance(result, str) and result == UNVERIFIED_RESULT:
            raise AbiFetchError(
                f"address {addr} is not verified on Arbiscan; "
                "fall back to a hand-curated ABI under abis/<protocol>/<role>.json."
            )
        raise AbiFetchError(
            f"Arbiscan refused fetch for {addr}: status={status} message={message!r} result={result!r}"
        )

    # Arbiscan packs the ABI as a JSON-encoded *string* in ``result``,
    # whereas Blockscout returns it as a list directly. Decode it here.
    if isinstance(result, str):
        try:
            abi = json.loads(result)
        except json.JSONDecodeError as exc:
            raise AbiFetchError(
                f"Arbiscan returned non-JSON ABI for {addr}: {result[:120]!r}"
            ) from exc
    elif isinstance(result, list):
        abi = result
    else:
        raise AbiFetchError(
            f"Arbiscan returned unexpected ABI shape for {addr}: {type(result).__name__}"
        )

    if not isinstance(abi, list) or not abi:
        raise AbiFetchError(f"Arbiscan returned empty/non-list ABI for {addr}")

    meta = {
        "chain_id": CHAIN_ID,
        "address": addr,
        "abi_hash_sha256": _abi_hash(abi),
        "fetched_at": _utcnow(),
        "source": "arbiscan",
    }

    abi_path, meta_path = _cache_paths(addr, cache_dir)
    abi_path.write_text(json.dumps(abi, indent=2) + "\n")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    return {"abi": abi, "meta": meta}


def fetch_abi_to_disk(
    address: str,
    target_path: pathlib.Path | str,
    *,
    api_base: str = DEFAULT_ARBISCAN_API,
    api_key: str = ARBISCAN_API_KEY,
    http_client: Any | None = None,
) -> dict[str, Any]:
    """Fetch an ABI and write it to a specific path (registry pin workflow).

    The caller chooses ``target_path`` (e.g.
    ``lib/chains/arbitrum/abis/aave_v3/Pool.json``); a sibling
    ``<name>.meta.json`` is written alongside.
    """
    target = pathlib.Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    result = fetch_abi(
        address,
        api_base=api_base,
        api_key=api_key,
        force=True,
        cache_dir=target.parent,
        http_client=http_client,
    )

    target.write_text(json.dumps(result["abi"], indent=2) + "\n")
    meta_path = target.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(result["meta"], indent=2) + "\n")
    return result


def load_pinned_abi(rel_path: str, *, base_dir: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Load a checked-in ABI by path relative to ``lib/chains/arbitrum/abis/``.

    Used by registry / contracts wrappers — they don't need network.
    """
    root = base_dir or pathlib.Path(__file__).parent
    target = root / rel_path
    if not target.exists():
        raise AbiFetchError(f"pinned ABI missing: {target}")
    return json.loads(target.read_text(encoding="utf-8"))
