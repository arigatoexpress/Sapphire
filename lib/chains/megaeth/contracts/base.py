"""Generic typed contract base for read-only MegaETH calls.

Encodes/decodes via ``eth_abi`` and dispatches through the existing
``MegaETHClient.eth_call``-style helper from PR #529. We intentionally
do NOT depend on web3.py's contract layer to keep the dependency
footprint small (eth_abi is already pulled in by web3.py and is the
right level of abstraction).

Read-only on purpose: there is no ``send_transaction`` here, no nonce
helper, no signer. Write paths live in Wave C's ``megaeth_executor``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import function_signature_to_4byte_selector


class _MegaETHCallable(Protocol):
    """Minimal slice of ``MegaETHClient`` we use here.

    Defined as a Protocol so tests can pass a duck-typed fake without
    constructing a real client. The real ``MegaETHClient`` from
    ``plugins/claw-sapphire/tools/internal/megaeth.py`` satisfies this.
    """

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:  # pragma: no cover
        ...


@dataclass(frozen=True)
class _AbiFunction:
    name: str
    inputs: tuple[dict[str, Any], ...]
    outputs: tuple[dict[str, Any], ...]
    state_mutability: str
    selector: bytes
    input_signature: str
    output_types: tuple[str, ...]


def _canonicalize_type(item: dict[str, Any]) -> str:
    """Resolve a function-input descriptor into a canonical ABI type string.

    Tuples (structs) are rendered as ``(t1,t2,...)``; arrays preserve
    their suffix (e.g. ``(t1,t2)[]``).
    """
    base = item.get("type", "")
    if base.startswith("tuple"):
        components = item.get("components") or []
        rendered = "(" + ",".join(_canonicalize_type(c) for c in components) + ")"
        # base may be "tuple", "tuple[]", "tuple[3]" — preserve the suffix.
        suffix = base[len("tuple") :]
        return rendered + suffix
    return base


def _index_abi(abi: Sequence[dict[str, Any]]) -> dict[str, _AbiFunction]:
    out: dict[str, _AbiFunction] = {}
    for entry in abi:
        if entry.get("type") != "function":
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        inputs = tuple(entry.get("inputs") or [])
        outputs = tuple(entry.get("outputs") or [])
        input_types = tuple(_canonicalize_type(i) for i in inputs)
        output_types = tuple(_canonicalize_type(o) for o in outputs)
        signature = f"{name}({','.join(input_types)})"
        selector = function_signature_to_4byte_selector(signature)
        out[name] = _AbiFunction(
            name=name,
            inputs=inputs,
            outputs=outputs,
            state_mutability=str(entry.get("stateMutability") or ""),
            selector=selector,
            input_signature=signature,
            output_types=output_types,
        )
    return out


class TypedContract:
    """Read-only typed contract, backed by a ``MegaETHClient``.

    Usage::

        client = MegaETHClient()
        async with client:
            ui = TypedContract(client, "0x1aB55b...286B", abi)
            reserves, base_currency = await ui.call("getReservesData", PROVIDER)

    The ``call(name, *args)`` method:
      1. Looks up the function entry in the indexed ABI.
      2. Encodes the input args via ``eth_abi.encode``.
      3. Issues ``eth_call`` against ``self.address``.
      4. Decodes the return value(s).

    Returns a single Python value when the function has 1 output, a
    tuple of values when it has multiple. Tuples (structs) are returned
    as plain Python tuples; the typed wrappers above (``aave_v3.py``)
    convert them into dataclasses.

    Multicall behavior: :meth:`multicall` falls back to sequential
    ``eth_call`` if no Multicall3 address is configured. The Wave A
    use-case (one ``getReservesData`` call) doesn't actually need
    multicall — included for symmetry with future protocols.
    """

    def __init__(
        self,
        client: _MegaETHCallable,
        address: str,
        abi: Sequence[dict[str, Any]] | str,
        *,
        multicall_address: str | None = None,
    ) -> None:
        if isinstance(abi, str):
            abi = json.loads(abi)
        if not isinstance(abi, Sequence):  # pragma: no cover — defensive
            raise TypeError(f"abi must be a JSON array or list, got {type(abi).__name__}")
        if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
            raise ValueError(f"invalid address: {address!r}")
        self._client = client
        self.address = address
        self.abi = list(abi)
        self._fns = _index_abi(self.abi)
        self.multicall_address = multicall_address

    def has_function(self, name: str) -> bool:
        return name in self._fns

    def encode_call(self, function_name: str, *args: Any) -> str:
        fn = self._fns.get(function_name)
        if fn is None:
            raise KeyError(f"function {function_name!r} not in ABI; known: {sorted(self._fns)}")
        input_types = tuple(_canonicalize_type(i) for i in fn.inputs)
        if len(args) != len(input_types):
            raise ValueError(
                f"{function_name}: expected {len(input_types)} args ({input_types}), got {len(args)}"
            )
        try:
            payload = abi_encode(list(input_types), list(args))
        except Exception as exc:
            raise ValueError(f"{function_name}: arg encoding failed: {exc}") from exc
        return "0x" + (fn.selector + payload).hex()

    def decode_result(self, function_name: str, raw_hex: str) -> Any:
        fn = self._fns.get(function_name)
        if fn is None:
            raise KeyError(f"function {function_name!r} not in ABI")
        if not raw_hex or raw_hex == "0x":
            return None
        if raw_hex.startswith(("0x", "0X")):
            raw_bytes = bytes.fromhex(raw_hex[2:])
        else:
            raw_bytes = bytes.fromhex(raw_hex)
        decoded = abi_decode(list(fn.output_types), raw_bytes)
        if len(decoded) == 1:
            return decoded[0]
        return tuple(decoded)

    async def call(
        self,
        function_name: str,
        *args: Any,
        block: str = "latest",
    ) -> Any:
        data = self.encode_call(function_name, *args)
        params = [{"to": self.address, "data": data}, block]
        result = await self._client._call("eth_call", params)
        return self.decode_result(function_name, result if isinstance(result, str) else "0x")

    async def multicall(
        self,
        calls: list[tuple[str, tuple[Any, ...]]],
        *,
        block: str = "latest",
    ) -> list[Any]:
        """Execute several reads. Falls back to sequential when no Multicall3 known.

        ``calls`` is a list of ``(function_name, args)`` tuples bound to
        ``self`` (same contract). For cross-contract multicall we'd
        accept ``(target, function_name, args)`` — Wave A doesn't need it.
        """
        # Sequential fallback — Multicall3 wiring deferred until Wave B.
        results: list[Any] = []
        for name, args in calls:
            results.append(await self.call(name, *args, block=block))
        return results
