"""Unit tests for the Zama/FHEVM privacy mock used by Sapphire Sentinel."""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib.hackathon.privacy_mock import (
    FhevmClient,
    HiddenBasket,
    default_demo_basket,
)


def _basket(weights: dict[str, Decimal], entropy: bytes = b"\x00" * 32) -> HiddenBasket:
    return HiddenBasket(weights=weights, entropy=entropy)


def test_compute_basket_aggregate_is_deterministic_for_same_input():
    client = FhevmClient()
    weights = {"TSLA": Decimal("0.4"), "AMZN": Decimal("0.6")}
    salt = b"sapphire-test-salt-0001"

    out_a = client.compute_basket_aggregate(weights, salt)
    out_b = client.compute_basket_aggregate(weights, salt)

    assert out_a == out_b
    assert isinstance(out_a, bytes)
    assert len(out_a) == 32


def test_compute_basket_aggregate_differs_for_different_weights():
    client = FhevmClient()
    salt = b"sapphire-test-salt-0001"

    out_a = client.compute_basket_aggregate({"TSLA": Decimal("0.4"), "AMZN": Decimal("0.6")}, salt)
    out_b = client.compute_basket_aggregate({"TSLA": Decimal("0.5"), "AMZN": Decimal("0.5")}, salt)

    assert out_a != out_b


def test_compute_basket_aggregate_differs_for_different_salts():
    client = FhevmClient()
    weights = {"TSLA": Decimal("0.4"), "AMZN": Decimal("0.6")}

    out_a = client.compute_basket_aggregate(weights, b"salt-alpha-pad-padpad")
    out_b = client.compute_basket_aggregate(weights, b"salt-bravo-pad-padpad")

    assert out_a != out_b


def test_compute_basket_aggregate_rejects_empty_salt():
    client = FhevmClient()
    with pytest.raises(ValueError):
        client.compute_basket_aggregate({"TSLA": Decimal("1.0")}, b"")


def test_compute_basket_aggregate_rejects_non_bytes_salt():
    client = FhevmClient()
    with pytest.raises(TypeError):
        client.compute_basket_aggregate({"TSLA": Decimal("1.0")}, "not-bytes")  # type: ignore[arg-type]


def test_hidden_basket_compute_hashes_returns_distinct_result_and_risk():
    client = FhevmClient()
    basket = _basket({"TSLA": Decimal("0.4"), "AMZN": Decimal("0.35"), "PLTR": Decimal("0.25")})

    result_hash, risk_hash = basket.compute_hashes(client)

    assert result_hash.startswith("0x")
    assert risk_hash.startswith("0x")
    # 32 bytes -> 64 hex chars + 0x prefix.
    assert len(result_hash) == 66
    assert len(risk_hash) == 66
    assert result_hash != risk_hash


def test_hidden_basket_compute_hashes_is_deterministic_per_basket():
    client = FhevmClient()
    weights = {"TSLA": Decimal("0.4"), "AMZN": Decimal("0.35"), "PLTR": Decimal("0.25")}
    entropy = b"\xab" * 32

    a_result, a_risk = _basket(weights, entropy).compute_hashes(client)
    b_result, b_risk = _basket(weights, entropy).compute_hashes(client)

    assert a_result == b_result
    assert a_risk == b_risk


def test_hidden_basket_compute_hashes_differs_with_entropy():
    client = FhevmClient()
    weights = {"TSLA": Decimal("0.5"), "AMZN": Decimal("0.5")}

    a_result, a_risk = _basket(weights, b"\x01" * 32).compute_hashes(client)
    b_result, b_risk = _basket(weights, b"\x02" * 32).compute_hashes(client)

    assert a_result != b_result
    assert a_risk != b_risk


def test_default_demo_basket_is_deterministic():
    client = FhevmClient()
    a_result, a_risk = default_demo_basket().compute_hashes(client)
    b_result, b_risk = default_demo_basket().compute_hashes(client)

    assert a_result == b_result
    assert a_risk == b_risk
    assert a_result != a_risk


def test_default_demo_basket_weights_match_robinhood_allow_list():
    basket = default_demo_basket()

    assert set(basket.weights.keys()) == {"TSLA", "AMZN", "PLTR", "NFLX", "AMD"}
    assert sum(basket.weights.values()) == Decimal("1.00")
