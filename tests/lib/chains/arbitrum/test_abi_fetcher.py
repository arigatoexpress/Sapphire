"""Tests for the Arbiscan ABI fetcher.

Network is never invoked: every test injects a fake httpx-shaped client.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from lib.chains.arbitrum.abis.fetcher import (
    UNVERIFIED_RESULT,
    AbiFetchError,
    _build_url,
    _normalize_address,
    fetch_abi,
    fetch_abi_to_disk,
    load_pinned_abi,
)


class DummyResponse:
    """Quacks like an ``httpx.Response`` for our two methods of interest."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class DummyClient:
    """Quacks like an ``httpx.Client``: ``.get(url) -> DummyResponse``."""

    def __init__(self, response: DummyResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    def get(self, url: str) -> DummyResponse:
        self.calls.append(url)
        return self.response


SAMPLE_ABI = [
    {
        "type": "function",
        "name": "balanceOf",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    }
]


def _arbiscan_payload(abi: list[dict[str, Any]]) -> dict[str, Any]:
    """Arbiscan packs the ABI as a JSON-encoded *string* in `result`."""
    return {"status": "1", "message": "OK", "result": json.dumps(abi)}


def test_normalize_address_lowercases() -> None:
    addr = "0x" + "AB" * 20
    assert _normalize_address(addr) == addr.lower()


def test_normalize_address_rejects_bad_input() -> None:
    with pytest.raises(AbiFetchError, match="invalid address"):
        _normalize_address("not-an-address")


def test_build_url_includes_apikey_when_provided() -> None:
    url = _build_url("https://api.arbiscan.io/api", "0x" + "ab" * 20, api_key="KEY123")
    assert "module=contract&action=getabi" in url
    assert "apikey=KEY123" in url
    assert url.lower().endswith("apikey=key123") or url.endswith("apikey=KEY123")


def test_build_url_omits_apikey_when_blank() -> None:
    url = _build_url("https://api.arbiscan.io/api", "0x" + "ab" * 20, api_key="")
    assert "apikey=" not in url


def test_fetch_abi_writes_cache_and_returns_meta(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "ab" * 20
    client = DummyClient(DummyResponse(_arbiscan_payload(SAMPLE_ABI)))

    result = fetch_abi(addr, http_client=client, cache_dir=tmp_path)
    assert result["abi"] == SAMPLE_ABI
    meta = result["meta"]
    assert meta["chain_id"] == 42161
    assert meta["address"] == addr.lower()
    assert meta["source"] == "arbiscan"
    assert "abi_hash_sha256" in meta and len(meta["abi_hash_sha256"]) == 64

    abi_file = tmp_path / f"{addr.lower()}.json"
    meta_file = tmp_path / f"{addr.lower()}.meta.json"
    assert abi_file.exists() and meta_file.exists()
    assert json.loads(abi_file.read_text()) == SAMPLE_ABI


def test_fetch_abi_uses_cache_on_second_call(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "cd" * 20
    client = DummyClient(DummyResponse(_arbiscan_payload(SAMPLE_ABI)))

    fetch_abi(addr, http_client=client, cache_dir=tmp_path)
    assert len(client.calls) == 1

    # Second call should NOT touch the (still-mocked) http client.
    cached = fetch_abi(addr, http_client=client, cache_dir=tmp_path)
    assert len(client.calls) == 1
    assert cached["abi"] == SAMPLE_ABI


def test_fetch_abi_force_refreshes(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "ef" * 20
    client = DummyClient(DummyResponse(_arbiscan_payload(SAMPLE_ABI)))

    fetch_abi(addr, http_client=client, cache_dir=tmp_path)
    fetch_abi(addr, http_client=client, cache_dir=tmp_path, force=True)
    assert len(client.calls) == 2


def test_fetch_abi_unverified_raises_clean_error(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "11" * 20
    payload = {"status": "0", "message": "NOTOK", "result": UNVERIFIED_RESULT}
    client = DummyClient(DummyResponse(payload))
    with pytest.raises(AbiFetchError, match="not verified"):
        fetch_abi(addr, http_client=client, cache_dir=tmp_path)


def test_fetch_abi_rate_limit_raises(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "22" * 20
    payload = {"status": "0", "message": "NOTOK", "result": "Max calls per sec rate limit reached"}
    client = DummyClient(DummyResponse(payload))
    with pytest.raises(AbiFetchError, match="status=0"):
        fetch_abi(addr, http_client=client, cache_dir=tmp_path)


def test_fetch_abi_handles_non_string_result(tmp_path: pathlib.Path) -> None:
    """Some Arbiscan-compatible mirrors return the ABI as a list directly."""
    addr = "0x" + "33" * 20
    payload = {"status": "1", "message": "OK", "result": SAMPLE_ABI}
    client = DummyClient(DummyResponse(payload))
    result = fetch_abi(addr, http_client=client, cache_dir=tmp_path)
    assert result["abi"] == SAMPLE_ABI


def test_fetch_abi_to_disk_writes_target_path(tmp_path: pathlib.Path) -> None:
    addr = "0x" + "44" * 20
    target = tmp_path / "aave_v3" / "test.json"
    client = DummyClient(DummyResponse(_arbiscan_payload(SAMPLE_ABI)))

    fetch_abi_to_disk(addr, target, http_client=client)
    assert target.exists()
    assert target.with_suffix(".meta.json").exists()
    assert json.loads(target.read_text()) == SAMPLE_ABI


def test_load_pinned_abi_finds_arbitrum_aave_v3_pool_min() -> None:
    """The checked-in Arbitrum Aave V3 pool ABI must load without network."""
    abi = load_pinned_abi("aave_v3/pool_min.json")
    assert isinstance(abi, list) and len(abi) > 0
    fn_names = {fn.get("name") for fn in abi if fn.get("type") == "function"}
    # Pool ABI must include the load-bearing read methods.
    assert "getUserAccountData" in fn_names
    assert "getReservesList" in fn_names


def test_load_pinned_abi_missing_file_raises() -> None:
    with pytest.raises(AbiFetchError, match="pinned ABI missing"):
        load_pinned_abi("aave_v3/does_not_exist.json")
