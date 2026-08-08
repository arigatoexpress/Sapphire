"""Unit tests for scripts/ops/grok_bridge_status.py (no plant required)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "ops" / "grok_bridge_status.py"


def _load():
    import sys

    spec = importlib.util.spec_from_file_location("grok_bridge_status", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # required for dataclasses on older Python
    spec.loader.exec_module(mod)
    return mod


def test_parse_frontmatter_basic():
    mod = _load()
    text = """---
source: grok-web
date: 2026-08-06
type: architecture
topics: [bridge, densify]
title: Hello
---

# body
"""
    fm = mod.parse_frontmatter(text)
    assert fm["source"] == "grok-web"
    assert fm["date"] == "2026-08-06"
    assert fm["type"] == "architecture"
    assert "bridge" in fm["topics"]
    assert fm["title"] == "Hello"


def test_parse_frontmatter_missing():
    mod = _load()
    assert mod.parse_frontmatter("# no fm\n") == {}


def test_inventory_sees_exports():
    mod = _load()
    items = mod.inventory()
    assert len(items) >= 5
    names = {i.name for i in items}
    assert any("bridge" in n for n in names)


def test_build_report_has_plant_sync():
    mod = _load()
    report = mod.build_report(mod.inventory())
    assert report["count"] >= 5
    assert "monorepo_script" in report["plant_sync"]
    assert "missing_required_hints" in report
