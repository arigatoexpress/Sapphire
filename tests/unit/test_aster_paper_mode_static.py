"""Safety tests for Aster paper-trading mode without importing stale service deps."""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASTER_MAIN = ROOT / "services" / "aster" / "src" / "main.py"


def _load_paper_mode_helper():
    tree = ast.parse(ASTER_MAIN.read_text())
    constants = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id.startswith("_PAPER_TRADING_")
            for target in node.targets
        )
    ]
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_paper_trading_env_enabled"
    )
    module = ast.Module(body=[*constants, helper], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "os": os,
        "logger": logging.getLogger("test_aster_paper_mode_static"),
    }
    exec(compile(module, str(ASTER_MAIN), "exec"), namespace)
    return namespace["_paper_trading_env_enabled"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("off", False),
        ("typo", True),
    ],
)
def test_aster_paper_trading_env_defaults_fail_closed(monkeypatch, value, expected):
    helper = _load_paper_mode_helper()
    if value is None:
        monkeypatch.delenv("PAPER_TRADING", raising=False)
    else:
        monkeypatch.setenv("PAPER_TRADING", value)

    assert helper() is expected
