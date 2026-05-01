"""Tests for the generic ``TypedContract`` base class.

Uses a fake ``MegaETHClient`` (with the same ``_call(method, params)``
async signature) — never touches the network.
"""

from __future__ import annotations

from typing import Any

import pytest
from eth_abi import encode as abi_encode
from eth_utils import function_signature_to_4byte_selector

from lib.chains.megaeth.contracts.base import TypedContract, _canonicalize_type

ADDR = "0x" + "ab" * 20
USER = "0x" + "cd" * 20

SAMPLE_ABI = [
    {
        "type": "function",
        "name": "balanceOf",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "twoReturns",
        "inputs": [],
        "outputs": [
            {"name": "a", "type": "uint256"},
            {"name": "b", "type": "uint256"},
        ],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "tupleReturn",
        "inputs": [],
        "outputs": [
            {
                "name": "out",
                "type": "tuple",
                "components": [
                    {"name": "x", "type": "uint256"},
                    {"name": "y", "type": "address"},
                ],
            }
        ],
        "stateMutability": "view",
    },
]


class FakeClient:
    def __init__(self, response_hex: str = "0x") -> None:
        self.response_hex = response_hex
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        return self.response_hex


@pytest.mark.asyncio
async def test_call_encodes_selector_and_args() -> None:
    client = FakeClient(response_hex="0x" + abi_encode(["uint256"], [42]).hex())
    tc = TypedContract(client, ADDR, SAMPLE_ABI)
    out = await tc.call("balanceOf", USER)
    assert out == 42
    assert client.calls[0][0] == "eth_call"
    payload = client.calls[0][1][0]
    assert payload["to"] == ADDR
    expected_selector = "0x" + function_signature_to_4byte_selector("balanceOf(address)").hex()
    assert payload["data"].startswith(expected_selector)


@pytest.mark.asyncio
async def test_call_returns_tuple_when_multiple_outputs() -> None:
    client = FakeClient(response_hex="0x" + abi_encode(["uint256", "uint256"], [10, 20]).hex())
    tc = TypedContract(client, ADDR, SAMPLE_ABI)
    out = await tc.call("twoReturns")
    assert out == (10, 20)


@pytest.mark.asyncio
async def test_call_decodes_tuple_struct() -> None:
    target = "0x" + "00" * 20
    encoded = abi_encode(["(uint256,address)"], [(7, target)])
    client = FakeClient(response_hex="0x" + encoded.hex())
    tc = TypedContract(client, ADDR, SAMPLE_ABI)
    out = await tc.call("tupleReturn")
    # Single tuple output is unwrapped to the tuple itself.
    assert out[0] == 7
    assert out[1].lower() == target


@pytest.mark.asyncio
async def test_call_arg_count_mismatch_raises() -> None:
    tc = TypedContract(FakeClient(), ADDR, SAMPLE_ABI)
    with pytest.raises(ValueError, match="expected 1 args"):
        await tc.call("balanceOf")


@pytest.mark.asyncio
async def test_call_unknown_function_raises() -> None:
    tc = TypedContract(FakeClient(), ADDR, SAMPLE_ABI)
    with pytest.raises(KeyError, match="not in ABI"):
        await tc.call("doesNotExist")


def test_invalid_address_rejected() -> None:
    with pytest.raises(ValueError, match="invalid address"):
        TypedContract(FakeClient(), "not-an-address", SAMPLE_ABI)


def test_canonicalize_type_handles_tuple_arrays() -> None:
    descriptor = {
        "type": "tuple[]",
        "components": [
            {"type": "uint256"},
            {
                "type": "tuple",
                "components": [
                    {"type": "address"},
                    {"type": "bool"},
                ],
            },
        ],
    }
    assert _canonicalize_type(descriptor) == "(uint256,(address,bool))[]"


@pytest.mark.asyncio
async def test_multicall_falls_back_to_sequential() -> None:
    # Two queued returns
    expected_a = abi_encode(["uint256"], [1]).hex()
    expected_b = abi_encode(["uint256"], [2]).hex()

    class TwoStepClient:
        def __init__(self) -> None:
            self.responses = [f"0x{expected_a}", f"0x{expected_b}"]
            self.idx = 0
            self.calls: list[Any] = []

        async def _call(self, method: str, params: list[Any] | None = None) -> Any:
            self.calls.append((method, params))
            r = self.responses[self.idx]
            self.idx += 1
            return r

    client = TwoStepClient()
    tc = TypedContract(client, ADDR, SAMPLE_ABI)
    out = await tc.multicall([("balanceOf", (USER,)), ("balanceOf", (ADDR,))])
    assert out == [1, 2]
    assert len(client.calls) == 2


def test_has_function() -> None:
    tc = TypedContract(FakeClient(), ADDR, SAMPLE_ABI)
    assert tc.has_function("balanceOf")
    assert not tc.has_function("noSuch")


def test_decode_result_handles_empty_response() -> None:
    tc = TypedContract(FakeClient(), ADDR, SAMPLE_ABI)
    assert tc.decode_result("balanceOf", "0x") is None
