"""Tests for the MegaETH protocol registry."""

from __future__ import annotations

import pathlib

import pytest
import yaml

from lib.chains.megaeth.registry import ProtocolEntry, ProtocolRegistry


def test_default_registry_loads_aave_v3() -> None:
    reg = ProtocolRegistry.from_yaml()
    assert "aave_v3" in reg
    e = reg.get("aave_v3")
    assert e.category == "lending"
    assert e.priority == 1
    assert e.status == "active"
    assert e.address("pool") == "0x7e324AbC5De01d112AfC03a584966ff199741C28"
    assert e.address("ui_pool_data_provider") == "0x1aB55bBdD5DF0782BBCf73553Af93BC6B29A286B"
    assert e.address("oracle") == "0x421117D7319E96d831972b3F7e970bbfe29C4F21"
    assert e.address("pool_addresses_provider") == "0x46Dcd5F4600319b02649Fd76B55aA6c1035CA478"


def test_registry_iter_and_len() -> None:
    reg = ProtocolRegistry.from_yaml()
    assert len(reg) >= 1
    assert all(isinstance(e, ProtocolEntry) for e in reg)


def test_registry_list_protocols_sorted_by_priority(tmp_path: pathlib.Path) -> None:
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "low_pri": {
                    "name": "Low",
                    "category": "dex_spot",
                    "priority": 3,
                    "status": "active",
                    "docs_url": "",
                    "addresses": {"router": "0x" + "1" * 40},
                    "abi_paths": {"router": "x/y.json"},
                },
                "high_pri": {
                    "name": "High",
                    "category": "lending",
                    "priority": 1,
                    "status": "active",
                    "docs_url": "",
                    "addresses": {"pool": "0x" + "2" * 40},
                    "abi_paths": {"pool": "a/b.json"},
                },
            }
        )
    )
    reg = ProtocolRegistry.from_yaml(yaml_path)
    keys_in_order = [e.key for e in reg.list_protocols()]
    assert keys_in_order == ["high_pri", "low_pri"]


def test_registry_by_category() -> None:
    reg = ProtocolRegistry.from_yaml()
    lending = reg.by_category("lending")
    assert any(e.key == "aave_v3" for e in lending)
    assert reg.by_category("does_not_exist") == []


def test_registry_unknown_protocol_raises() -> None:
    reg = ProtocolRegistry.from_yaml()
    with pytest.raises(KeyError, match="unknown protocol"):
        reg.get("does_not_exist")


def test_protocol_entry_unknown_role_raises() -> None:
    reg = ProtocolRegistry.from_yaml()
    e = reg.get("aave_v3")
    with pytest.raises(KeyError, match="no address for role"):
        e.address("not_a_real_role")
    with pytest.raises(KeyError, match="no ABI path for role"):
        e.abi_path("not_a_real_role")


def test_registry_missing_file_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(FileNotFoundError):
        ProtocolRegistry.from_yaml(tmp_path / "no_such.yaml")


def test_registry_non_mapping_root_rejected(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        ProtocolRegistry.from_yaml(p)


def test_registry_constructor_with_explicit_entries() -> None:
    e = ProtocolEntry(
        key="x",
        name="X",
        category="lending",
        priority=1,
        status="active",
        docs_url="",
        addresses={"pool": "0x" + "0" * 40},
        abi_paths={"pool": "x.json"},
    )
    reg = ProtocolRegistry({"x": e})
    assert reg.get("x") is e
    assert "x" in reg
