"""Tests for the Sapphire test inventory helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "test_inventory.py"

SPEC = importlib.util.spec_from_file_location("test_inventory", SCRIPT)
assert SPEC and SPEC.loader
test_inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = test_inventory
SPEC.loader.exec_module(test_inventory)


def test_parse_collect_output_sums_pytest_quiet_file_counts() -> None:
    output = "\n".join(
        [
            "tests/unit/test_alpha.py: 3",
            "tests/unit/test_beta.py: 4",
            "",
        ]
    )

    assert test_inventory.parse_collect_output(output) == (7, 2)


def test_parse_collect_output_falls_back_to_summary() -> None:
    assert test_inventory.parse_collect_output("3420 tests collected in 2.02s") == (3420, 0)


def test_readme_inventory_check_allows_small_undercount(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "[![Tests](https://img.shields.io/badge/tests-3%2C550%2B%20passing-2ea44f)](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml)",
                "- 3,550+ passing tests across 185 files",
            ]
        ),
        encoding="utf-8",
    )
    inventory = test_inventory.Inventory(
        schema_version=1,
        generated_at="2026-04-28T00:00:00+00:00",
        suites=[
            test_inventory.SuiteInventory("unit", ["tests/unit"], 3421, 171, 1),
            test_inventory.SuiteInventory("plugin", ["plugins/claw-sapphire/tests"], 130, 17, 1),
        ],
    )

    result = test_inventory.check_readme_inventory(inventory, readme_path=readme, max_drift=50)

    assert result["ok"] is True
    assert result["deltas"]["total"] == 1
    assert result["deltas"]["badge_total"] == 1
    assert result["deltas"]["files"] == 3


def test_readme_inventory_check_rejects_overclaim(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "[![Tests](https://img.shields.io/badge/tests-3%2C550%2B%20passing-2ea44f)](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml)",
                "- 3,600+ passing tests across 185 files",
            ]
        ),
        encoding="utf-8",
    )
    inventory = test_inventory.Inventory(
        schema_version=1,
        generated_at="2026-04-28T00:00:00+00:00",
        suites=[
            test_inventory.SuiteInventory("unit", ["tests/unit"], 3420, 170, 1),
            test_inventory.SuiteInventory("plugin", ["plugins/claw-sapphire/tests"], 130, 17, 1),
        ],
    )

    result = test_inventory.check_readme_inventory(inventory, readme_path=readme, max_drift=50)

    assert result["ok"] is False
    assert result["overclaims"] == {"total": -50}


def test_readme_inventory_check_rejects_file_count_overclaim(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "[![Tests](https://img.shields.io/badge/tests-3%2C550%2B%20passing-2ea44f)](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml)",
                "- 3,550+ passing tests across 200 files",
            ]
        ),
        encoding="utf-8",
    )
    inventory = test_inventory.Inventory(
        schema_version=1,
        generated_at="2026-04-28T00:00:00+00:00",
        suites=[
            test_inventory.SuiteInventory("unit", ["tests/unit"], 3420, 170, 1),
            test_inventory.SuiteInventory("plugin", ["plugins/claw-sapphire/tests"], 130, 17, 1),
        ],
    )

    result = test_inventory.check_readme_inventory(inventory, readme_path=readme, max_drift=50)

    assert result["ok"] is False
    assert result["overclaims"] == {"files": -13}


def test_readme_inventory_check_rejects_badge_overclaim(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "[![Tests](https://img.shields.io/badge/tests-3%2C600%2B%20passing-2ea44f)](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml)",
                "- 3,550+ passing tests across 185 files",
            ]
        ),
        encoding="utf-8",
    )
    inventory = test_inventory.Inventory(
        schema_version=1,
        generated_at="2026-04-28T00:00:00+00:00",
        suites=[
            test_inventory.SuiteInventory("unit", ["tests/unit"], 3420, 170, 1),
            test_inventory.SuiteInventory("plugin", ["plugins/claw-sapphire/tests"], 130, 17, 1),
        ],
    )

    result = test_inventory.check_readme_inventory(inventory, readme_path=readme, max_drift=50)

    assert result["ok"] is False
    assert result["overclaims"] == {"badge_total": -50}
