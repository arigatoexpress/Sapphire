"""Static coverage for fresh-mac Makefile entrypoints."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_fresh_mac_make_targets_are_present() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    expected = {
        "sapphire-on-fresh-mac": "bash scripts/ops/bootstrap_fresh_mac.sh",
        "sapphire-demo-up": "sapphire-on-fresh-mac",
        "sapphire-demo-down": "bash scripts/ops/teardown_fresh_mac.sh",
        "sapphire-demo-reset": "SAPPHIRE_BOOTSTRAP_RESET_SECRETS=1 bash scripts/ops/teardown_fresh_mac.sh",
    }
    for target, command in expected.items():
        assert f"{target}:" in makefile
        assert command in makefile


def test_fresh_mac_targets_are_phony() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    phony_line = next(
        line for line in makefile.splitlines() if line.startswith(".PHONY: install")
    )
    for target in (
        "sapphire-on-fresh-mac",
        "sapphire-demo-up",
        "sapphire-demo-down",
        "sapphire-demo-reset",
    ):
        assert target in phony_line
