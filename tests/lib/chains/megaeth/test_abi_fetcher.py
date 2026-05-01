"""Unit tests for the Blockscout ABI fetcher.

Network is never invoked — every test injects a fake httpx-shaped client.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from lib.chains.megaeth.abis import fetcher as F
from lib.chains.megaeth.abis.fetcher import (
    AbiFetchError,
    fetch_abi,
    fetch_abi_to_disk,
    load_pinned_abi,
)


class _DummyResponse:
    def __init__(self, body: dict, *, status: int = 200) -> None:
        self._body = body
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")

    def json(self) -> dict:
        return self._body


class _DummyClient:
    """Captures GETs and returns a pre-staged response per URL."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str) -> _DummyResponse:
        self.calls.append(url)
        if url in self.responses:
            return _DummyResponse(self.responses[url])
        return _DummyResponse({}, status=404)


SAMPLE_ABI: list[dict] = [
    {
        "type": "function",
        "name": "balanceOf",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]


PROXY_ABI: list[dict] = [
    {
        "type": "function",
        "name": "implementation",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
    },
]


def test_fetch_abi_basic_success(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "ab" * 20
    body = {
        "abi": SAMPLE_ABI,
        "is_verified": True,
        "verified_at": "2026-01-01T00:00:00Z",
        "compiler_version": "v0.8.20",
        "name": "TestContract",
        "proxy_type": None,
        "implementations": [],
    }
    client = _DummyClient({f"https://x/api/v2/smart-contracts/{addr}": body})
    result = fetch_abi(addr, api_base="https://x/api/v2", cache_dir=tmp_path, http_client=client)
    assert result["abi"] == SAMPLE_ABI
    assert result["meta"]["chain_id"] == 4326
    assert result["meta"]["address"] == addr
    assert result["meta"]["is_proxy"] is False
    assert result["meta"]["source"] == "blockscout"
    # cache files were written
    assert (tmp_path / f"{addr}.json").exists()
    assert (tmp_path / f"{addr}.meta.json").exists()


def test_fetch_abi_cache_hit_skips_network(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "cd" * 20
    # Pre-seed the cache.
    (tmp_path / f"{addr}.json").write_text(json.dumps(SAMPLE_ABI))
    (tmp_path / f"{addr}.meta.json").write_text(json.dumps({"chain_id": 4326, "address": addr}))
    client = _DummyClient({})  # would 404 if hit
    result = fetch_abi(addr, api_base="https://x/api/v2", cache_dir=tmp_path, http_client=client)
    assert result["abi"] == SAMPLE_ABI
    assert client.calls == []  # never went out


def test_fetch_abi_force_refresh(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "ef" * 20
    (tmp_path / f"{addr}.json").write_text(json.dumps([{"type": "function", "name": "stale"}]))
    (tmp_path / f"{addr}.meta.json").write_text("{}")
    body = {"abi": SAMPLE_ABI, "is_verified": True, "name": "Fresh"}
    client = _DummyClient({f"https://x/api/v2/smart-contracts/{addr}": body})
    result = fetch_abi(
        addr, api_base="https://x/api/v2", cache_dir=tmp_path, http_client=client, force=True
    )
    assert result["abi"] == SAMPLE_ABI
    assert client.calls == [f"https://x/api/v2/smart-contracts/{addr}"]


def test_fetch_abi_proxy_follow(tmp_path: pathlib.Path) -> None:
    proxy = "0x" + "11" * 20
    impl = "0x" + "22" * 20
    body_proxy = {
        "abi": PROXY_ABI,
        "is_verified": True,
        "name": "Proxy",
        "proxy_type": "eip1967",
        "implementations": [{"address_hash": impl, "name": None}],
    }
    body_impl = {"abi": SAMPLE_ABI, "is_verified": True, "name": "Impl"}
    client = _DummyClient(
        {
            f"https://x/api/v2/smart-contracts/{proxy}": body_proxy,
            f"https://x/api/v2/smart-contracts/{impl}": body_impl,
        }
    )
    result = fetch_abi(
        proxy, api_base="https://x/api/v2", cache_dir=tmp_path, http_client=client, force=True
    )
    fns = {e.get("name") for e in result["abi"] if e.get("type") == "function"}
    # Both proxy + impl methods are merged
    assert "balanceOf" in fns
    assert "implementation" in fns
    assert result["meta"]["is_proxy"] is True
    assert result["meta"]["implementation_address"] == impl
    assert result["meta"]["source"] == "blockscout+impl"
    assert len(client.calls) == 2


def test_fetch_abi_proxy_impl_unverified_falls_back_to_proxy_abi(tmp_path: pathlib.Path) -> None:
    proxy = "0x" + "33" * 20
    impl = "0x" + "44" * 20
    body_proxy = {
        "abi": PROXY_ABI,
        "is_verified": True,
        "name": "Proxy",
        "proxy_type": "eip1967",
        "implementations": [{"address_hash": impl, "name": None}],
    }
    # Impl returns no abi (unverified case)
    body_impl = {"abi": [], "is_verified": False, "name": None}
    client = _DummyClient(
        {
            f"https://x/api/v2/smart-contracts/{proxy}": body_proxy,
            f"https://x/api/v2/smart-contracts/{impl}": body_impl,
        }
    )
    result = fetch_abi(
        proxy, api_base="https://x/api/v2", cache_dir=tmp_path, http_client=client, force=True
    )
    # Proxy ABI is returned alone, source is just "blockscout"
    fns = {e.get("name") for e in result["abi"] if e.get("type") == "function"}
    assert "implementation" in fns
    assert "balanceOf" not in fns
    assert result["meta"]["source"] == "blockscout"


def test_fetch_abi_unverified_raises(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "55" * 20
    body = {"abi": [], "is_verified": False, "proxy_type": None, "implementations": []}
    client = _DummyClient({f"https://x/api/v2/smart-contracts/{addr}": body})
    with pytest.raises(AbiFetchError, match="no ABI available"):
        fetch_abi(addr, api_base="https://x/api/v2", cache_dir=tmp_path, http_client=client)


def test_fetch_abi_bad_address_rejected(tmp_path: pathlib.Path) -> None:
    with pytest.raises(AbiFetchError, match="invalid address"):
        fetch_abi("not-an-address", cache_dir=tmp_path, http_client=_DummyClient({}))


def test_fetch_abi_to_disk_writes_target(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "66" * 20
    body = {"abi": SAMPLE_ABI, "is_verified": True, "name": "T"}
    client = _DummyClient({f"https://x/api/v2/smart-contracts/{addr}": body})
    target = tmp_path / "aave_v3" / "Pool.json"
    result = fetch_abi_to_disk(
        addr,
        target,
        api_base="https://x/api/v2",
        http_client=client,
    )
    assert target.exists()
    assert target.with_suffix(".meta.json").exists()
    assert result["abi"] == SAMPLE_ABI


def test_load_pinned_abi_finds_checked_in_files() -> None:
    abi = load_pinned_abi("aave_v3/ui_pool_data_provider.json")
    fns = {e.get("name") for e in abi if e.get("type") == "function"}
    assert "getReservesData" in fns


def test_load_pinned_abi_missing_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(AbiFetchError, match="pinned ABI missing"):
        load_pinned_abi("not_a_real_protocol/foo.json")


def test_callable_http_client_path(tmp_path: pathlib.Path) -> None:
    """The fetcher should also accept a callable ``url -> dict``."""
    addr = "0x" + "77" * 20
    body = {"abi": SAMPLE_ABI, "is_verified": True, "name": "Func"}
    captured: list[str] = []

    def dummy(url: str) -> dict:
        captured.append(url)
        return body

    result = fetch_abi(addr, api_base="https://x/api/v2", cache_dir=tmp_path, http_client=dummy)
    assert result["abi"] == SAMPLE_ABI
    assert captured == [f"https://x/api/v2/smart-contracts/{addr}"]


def test_chain_id_constant_is_4326() -> None:
    """Drift guard — Wave A is hard-coded to chain id 4326 (MegaETH mainnet)."""
    assert F.CHAIN_ID == 4326
