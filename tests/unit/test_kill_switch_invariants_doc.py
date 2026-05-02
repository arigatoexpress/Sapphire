"""Sanity checks for live-ramp and kill-switch diligence docs."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from lib.core import provenance

ROOT = Path(__file__).resolve().parents[2]
DOCS = (
    ROOT / "docs" / "products" / "live-trading-ramp-memo.md",
    ROOT / "docs" / "security" / "kill-switch-invariants.md",
)
CODE_REF_RE = re.compile(r"`([^`]+)`")


def _symbol_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _backtick_refs() -> list[str]:
    refs: list[str] = []
    for doc in DOCS:
        refs.extend(CODE_REF_RE.findall(doc.read_text(encoding="utf-8")))
    return refs


def test_required_docs_exist():
    for doc in DOCS:
        assert doc.exists(), doc
        assert doc.read_text(encoding="utf-8").startswith("# ")


def test_lib_core_references_point_to_real_files_and_symbols():
    refs = [ref for ref in _backtick_refs() if ref.startswith("lib/core/")]

    assert refs
    for ref in refs:
        path_text, _, symbol = ref.partition("::")
        path = ROOT / path_text
        assert path.exists(), ref
        if symbol:
            assert path.is_file(), ref
            assert symbol in _symbol_names(path), ref


def test_referenced_test_files_exist():
    refs = [
        ref
        for ref in _backtick_refs()
        if ref.startswith("tests/") or ref.startswith("plugins/claw-sapphire/tests/")
    ]

    assert refs
    for ref in refs:
        path = ROOT / ref
        assert path.is_file(), ref


def test_docs_keep_live_stock_automation_blocked():
    ramp = (ROOT / "docs" / "products" / "live-trading-ramp-memo.md").read_text(encoding="utf-8")

    assert "Stock live trading is blocked" in ramp
    assert "TRADINGVIEW_EXECUTION_ENABLED=false" in ramp
    assert "$5" in ramp
    assert "$50" in ramp
    assert "$500" in ramp


def test_kill_switch_doc_names_all_layers():
    text = (ROOT / "docs" / "security" / "kill-switch-invariants.md").read_text(encoding="utf-8")

    for phrase in (
        "Trade-Time Invariants",
        "Confirmation Firewall",
        "Operator Manual Halt",
        "Security Kill Switch",
        "Heartbeat And Supervisor",
        "Witness And Audit",
    ):
        assert phrase in text


def test_provenance_sidecars_verify():
    for doc in DOCS:
        sidecar = provenance.sidecar_path(doc)
        assert sidecar.exists(), sidecar
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert provenance.verify(payload)


def test_ramp_doc_links_to_current_robinhood_posture():
    text = (ROOT / "docs" / "products" / "live-trading-ramp-memo.md").read_text(encoding="utf-8")

    assert "docs/ops/robinhood-real-funds-readiness.md" in text
    assert (ROOT / "docs" / "ops" / "robinhood-real-funds-readiness.md").exists()


def test_kill_switch_doc_is_honest_about_latency_gap():
    text = (ROOT / "docs" / "security" / "kill-switch-invariants.md").read_text(encoding="utf-8")

    assert 'There is no single universal "latency kill switch"' in text
