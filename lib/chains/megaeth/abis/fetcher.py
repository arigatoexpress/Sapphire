"""Blockscout v2 ABI fetcher with on-disk cache + EIP-1967 proxy follow.

The MegaETH Blockscout instance is at https://megaeth.blockscout.com.
The smart-contracts endpoint is::

    GET https://megaeth.blockscout.com/api/v2/smart-contracts/{address}

Response shape (verified live 2026-04-30):

    {
      "abi": [...],                       # JSON ABI array (may be empty if unverified)
      "is_verified": true,
      "verified_at": "2026-01-27T03:48:29Z",
      "compiler_version": "v0.8.27+...",
      "name": "PoolAddressesProvider",
      "proxy_type": "eip1967" | null,
      "implementations": [
        {"address_hash": "0xc74c...44da4D", "name": null}
      ],
      ... (many more fields)
    }

For EIP-1967 proxies, Blockscout returns the proxy's own thin ABI
(`admin`, `implementation`, `upgradeTo`, ...) plus an `implementations`
list pointing at the real impl. The fetcher follows the link and merges
the impl ABI on top of the proxy ABI when ``follow_proxy=True`` (default).

ABIs are cached at ``lib/chains/megaeth/abis/_cache/<lowercased>.json``
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

CHAIN_ID = 4326
DEFAULT_BLOCKSCOUT_API = os.getenv(
    "SAPPHIRE_MEGAETH_BLOCKSCOUT_API",
    "https://megaeth.blockscout.com/api/v2",
)

#: Anyone wanting a different on-disk cache root can pass `cache_dir=`
#: to :func:`fetch_abi` directly; the default keeps everything inside
#: the package so checked-in ABIs travel with the source.
DEFAULT_CACHE_DIR = pathlib.Path(__file__).parent / "_cache"


class AbiFetchError(RuntimeError):
    """Raised when Blockscout returns no ABI for a given address."""


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

    `http_client` may be:
      * an ``httpx.Client`` (sync) — the production path
      * a callable ``url -> dict`` — the test injection path
      * ``None`` — late-import httpx and use it
    """
    if callable(http_client) and not hasattr(http_client, "get"):
        return http_client(url)  # type: ignore[no-any-return]

    if http_client is None:
        import httpx  # late import — keep httpx optional for non-fetch users

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


def fetch_abi(
    address: str,
    *,
    api_base: str = DEFAULT_BLOCKSCOUT_API,
    follow_proxy: bool = True,
    force: bool = False,
    cache_dir: pathlib.Path = DEFAULT_CACHE_DIR,
    http_client: Any | None = None,
) -> dict[str, Any]:
    """Return the ABI + provenance metadata for ``address``.

    Returns a dict shaped::

        {
            "abi": [<json abi>],
            "meta": {
                "chain_id": 4326,
                "address": "0x..." (lowercased),
                "is_proxy": bool,
                "implementation_address": "0x..." | None,
                "blockscout_verified_at": str | None,
                "compiler_version": str | None,
                "contract_name": str | None,
                "abi_hash_sha256": str,
                "fetched_at": "<iso>",
                "source": "blockscout" | "blockscout+impl",
            },
        }

    Behavior:
      * If a cached file exists and ``force=False``, returns the cache.
      * Otherwise hits Blockscout, optionally follows EIP-1967 proxies,
        writes both files, and returns the fresh result.

    :raises AbiFetchError: if the address isn't verified on Blockscout
        and no usable ABI can be assembled.
    """
    addr = _normalize_address(address)

    if not force:
        cached = _load_cached(addr, cache_dir)
        if cached is not None and cached["abi"]:
            return cached

    url = f"{api_base.rstrip('/')}/smart-contracts/{addr}"
    body = _http_get_json(url, http_client=http_client)

    abi: list[dict[str, Any]] = list(body.get("abi") or [])
    is_proxy = body.get("proxy_type") is not None
    implementations = body.get("implementations") or []
    impl_address: str | None = None
    source = "blockscout"

    if follow_proxy and is_proxy and implementations:
        impl_raw = implementations[0].get("address_hash")
        if isinstance(impl_raw, str):
            impl_address = impl_raw.lower()
            try:
                impl_url = f"{api_base.rstrip('/')}/smart-contracts/{impl_address}"
                impl_body = _http_get_json(impl_url, http_client=http_client)
                impl_abi = list(impl_body.get("abi") or [])
                if impl_abi:
                    # Merge: union by (type, name) — impl entries win.
                    seen: set[tuple[str, str]] = set()
                    merged: list[dict[str, Any]] = []
                    for entry in impl_abi + abi:
                        key = (str(entry.get("type", "")), str(entry.get("name", "")))
                        if key in seen and entry.get("type") == "function":
                            continue
                        seen.add(key)
                        merged.append(entry)
                    abi = merged
                    source = "blockscout+impl"
            except AbiFetchError:
                # Impl unverified is a known case (e.g. Aave V3 Pool impl
                # 0xc74c...). Caller falls back to a hand-curated ABI.
                pass

    if not abi:
        raise AbiFetchError(
            f"no ABI available for {addr} (is_verified={body.get('is_verified')}, "
            f"proxy={is_proxy}, impl={impl_address}). "
            "Use a hand-curated ABI under abis/<protocol>/<role>.json."
        )

    meta = {
        "chain_id": CHAIN_ID,
        "address": addr,
        "is_proxy": is_proxy,
        "implementation_address": impl_address,
        "blockscout_verified_at": body.get("verified_at"),
        "compiler_version": body.get("compiler_version"),
        "contract_name": body.get("name"),
        "abi_hash_sha256": _abi_hash(abi),
        "fetched_at": _utcnow(),
        "source": source,
    }

    abi_path, meta_path = _cache_paths(addr, cache_dir)
    abi_path.write_text(json.dumps(abi, indent=2) + "\n")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    return {"abi": abi, "meta": meta}


def fetch_abi_to_disk(
    address: str,
    target_path: pathlib.Path | str,
    *,
    api_base: str = DEFAULT_BLOCKSCOUT_API,
    follow_proxy: bool = True,
    http_client: Any | None = None,
) -> dict[str, Any]:
    """Fetch an ABI and write it to a specific path (registry pin workflow).

    The caller chooses ``target_path`` (e.g.
    ``lib/chains/megaeth/abis/aave_v3/Pool.json``); a sibling
    ``<name>.meta.json`` is written alongside.
    """
    target = pathlib.Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    result = fetch_abi(
        address,
        api_base=api_base,
        follow_proxy=follow_proxy,
        force=True,
        cache_dir=target.parent,  # write cache files in the target dir
        http_client=http_client,
    )

    target.write_text(json.dumps(result["abi"], indent=2) + "\n")
    meta_path = target.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(result["meta"], indent=2) + "\n")
    return result


def load_pinned_abi(rel_path: str, *, base_dir: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Load a checked-in ABI by path relative to ``lib/chains/megaeth/abis/``.

    Used by registry / contracts wrappers — they don't need network.
    """
    root = base_dir or pathlib.Path(__file__).parent
    target = root / rel_path
    if not target.exists():
        raise AbiFetchError(f"pinned ABI missing: {target}")
    return json.loads(target.read_text(encoding="utf-8"))
