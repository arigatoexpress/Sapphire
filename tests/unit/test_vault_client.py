"""Contract + failure-mode tests for ``lib.vault_client``.

The vault client's core promise is that it NEVER raises — every failure mode
returns a ``VaultResult`` with ``verdict='unavailable'`` so a caller can log,
degrade, and move on. That promise is the load-bearing property, so the failure
paths get more tests than the happy path.

The live-integration test at the bottom only runs when ``~/Knowledge/`` exists
AND the venv is installed; otherwise it skips (Sapphire CI does not carry the
vault).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lib.vault_client import (
    VaultHit,
    VaultResult,
    format_context_block,
    query_vault,
)

# ── happy-path parsing ──────────────────────────────────────────────────────


def _mkproc(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _mkpayload(verdict: str = "confident", top1: float = 0.75, n_results: int = 2) -> str:
    return json.dumps(
        {
            "query": "test",
            "verdict": verdict,
            "top1": top1,
            "confident_floor": 0.62,
            "weak_floor": 0.595,
            "results": [
                {
                    "title": f"note-{i}",
                    "path": f"2-Areas/foo/note-{i}.md",
                    "note_id": f"note-{i}",
                    "group": "2-Areas",
                    "score": top1 - i * 0.01,
                    "chunk": f"chunk content {i} " * 10,
                    "chunk_index": 0,
                    "total_chunks": 1,
                }
                for i in range(n_results)
            ],
        }
    )


def _make_vault(tmp_path: Path) -> Path:
    """Create a fake vault layout that passes existence checks."""
    root = tmp_path / "Knowledge"
    (root / "7-Visual-Graphs" / ".venv" / "bin").mkdir(parents=True)
    (root / "7-Visual-Graphs" / ".venv" / "bin" / "python").touch()
    (root / "7-Visual-Graphs" / "knowledge_lib.py").touch()
    return root


def test_confident_query_parses(tmp_path):
    root = _make_vault(tmp_path)
    with patch(
        "lib.vault_client.subprocess.run", return_value=_mkproc(_mkpayload("confident", 0.75, 3))
    ):
        r = query_vault("what is RH-Chain?", vault_root=root)
    assert r.verdict == "confident"
    assert r.top1 == 0.75
    assert r.is_citable is True
    assert len(r.results) == 3
    assert isinstance(r.results[0], VaultHit)
    assert r.results[0].title == "note-0"
    assert r.error is None


def test_weak_verdict_not_citable(tmp_path):
    root = _make_vault(tmp_path)
    with patch(
        "lib.vault_client.subprocess.run", return_value=_mkproc(_mkpayload("weak", 0.61, 1))
    ):
        r = query_vault("edge case", vault_root=root)
    assert r.verdict == "weak"
    assert r.is_citable is False


def test_none_verdict_not_citable(tmp_path):
    root = _make_vault(tmp_path)
    with patch("lib.vault_client.subprocess.run", return_value=_mkproc(_mkpayload("none", 0.4, 1))):
        r = query_vault("gibberish query", vault_root=root)
    assert r.verdict == "none"
    assert r.is_citable is False


def test_unknown_verdict_returns_unavailable(tmp_path):
    root = _make_vault(tmp_path)
    with patch(
        "lib.vault_client.subprocess.run", return_value=_mkproc(_mkpayload("bogus", 0.9, 1))
    ):
        r = query_vault("anything", vault_root=root)
    assert r.verdict == "unavailable"
    assert "unknown verdict" in (r.error or "")


# ── input validation ────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["", "   ", "\n\t"])
def test_empty_query_returns_unavailable(bad, tmp_path):
    # No subprocess call — validation runs first.
    with patch("lib.vault_client.subprocess.run") as mrun:
        r = query_vault(bad, vault_root=_make_vault(tmp_path))
    mrun.assert_not_called()
    assert r.verdict == "unavailable"
    assert "empty query" in (r.error or "")


def test_non_string_query_returns_unavailable(tmp_path):
    r = query_vault(123, vault_root=_make_vault(tmp_path))  # type: ignore[arg-type]
    assert r.verdict == "unavailable"
    assert "must be str" in (r.error or "")


def test_overlong_query_returns_unavailable(tmp_path):
    r = query_vault("x" * 5000, vault_root=_make_vault(tmp_path))
    assert r.verdict == "unavailable"
    assert "too long" in (r.error or "")


def test_n_results_clamped(tmp_path):
    root = _make_vault(tmp_path)
    with patch(
        "lib.vault_client.subprocess.run", return_value=_mkproc(_mkpayload("confident", 0.75, 1))
    ) as mrun:
        query_vault("q", n_results=999, vault_root=root)
        cmd = mrun.call_args.args[0]
        assert "--n=50" in cmd

    with patch(
        "lib.vault_client.subprocess.run", return_value=_mkproc(_mkpayload("confident", 0.75, 1))
    ) as mrun:
        query_vault("q", n_results=0, vault_root=root)
        cmd = mrun.call_args.args[0]
        assert "--n=1" in cmd


# ── environmental failure paths ─────────────────────────────────────────────


def test_missing_vault_root_returns_unavailable(tmp_path):
    r = query_vault("q", vault_root=tmp_path / "does-not-exist")
    assert r.verdict == "unavailable"
    assert "does not exist" in (r.error or "")


def test_missing_venv_returns_unavailable(tmp_path):
    root = tmp_path / "Knowledge"
    (root / "7-Visual-Graphs").mkdir(parents=True)
    (root / "7-Visual-Graphs" / "knowledge_lib.py").touch()
    r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "venv python missing" in (r.error or "")


def test_missing_knowledge_lib_returns_unavailable(tmp_path):
    root = tmp_path / "Knowledge"
    (root / "7-Visual-Graphs" / ".venv" / "bin").mkdir(parents=True)
    (root / "7-Visual-Graphs" / ".venv" / "bin" / "python").touch()
    r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "knowledge_lib.py missing" in (r.error or "")


def test_subprocess_timeout_returns_unavailable(tmp_path):
    root = _make_vault(tmp_path)
    with patch(
        "lib.vault_client.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1.0),
    ):
        r = query_vault("q", vault_root=root, timeout=1.0)
    assert r.verdict == "unavailable"
    assert "timed out" in (r.error or "")


def test_subprocess_oserror_returns_unavailable(tmp_path):
    root = _make_vault(tmp_path)
    with patch("lib.vault_client.subprocess.run", side_effect=OSError("fork failed")):
        r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "launch failed" in (r.error or "")


def test_nonzero_exit_returns_unavailable(tmp_path):
    root = _make_vault(tmp_path)
    with patch(
        "lib.vault_client.subprocess.run",
        return_value=_mkproc("", returncode=42, stderr="ollama not reachable"),
    ):
        r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "exited 42" in (r.error or "")
    assert "ollama" in (r.error or "")


def test_exit_code_3_empty_store_returns_unavailable(tmp_path):
    # The engine returns 3 with a JSON body carrying error+empty results.
    # The client should surface the error, not pretend to have found nothing.
    root = _make_vault(tmp_path)
    body = json.dumps(
        {"error": "empty vector store", "query": "q", "results": [], "verdict": "none", "top1": 0.0}
    )
    with patch("lib.vault_client.subprocess.run", return_value=_mkproc(body, returncode=3)):
        r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "empty vector store" in (r.error or "")


def test_empty_stdout_returns_unavailable(tmp_path):
    root = _make_vault(tmp_path)
    with patch("lib.vault_client.subprocess.run", return_value=_mkproc("")):
        r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "no output" in (r.error or "")


def test_malformed_json_returns_unavailable(tmp_path):
    root = _make_vault(tmp_path)
    with patch("lib.vault_client.subprocess.run", return_value=_mkproc("not{ json")):
        r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "non-JSON" in (r.error or "")


def test_json_array_instead_of_object_returns_unavailable(tmp_path):
    root = _make_vault(tmp_path)
    with patch("lib.vault_client.subprocess.run", return_value=_mkproc("[1,2,3]")):
        r = query_vault("q", vault_root=root)
    assert r.verdict == "unavailable"
    assert "non-object" in (r.error or "")


# ── format helper ───────────────────────────────────────────────────────────


def test_format_context_unavailable():
    r = VaultResult(query="q", verdict="unavailable", top1=0.0, error="vault down")
    out = format_context_block(r)
    assert "vault unavailable" in out
    assert "vault down" in out


def test_format_context_none():
    r = VaultResult(query="obscure topic", verdict="none", top1=0.3)
    out = format_context_block(r)
    assert "no confident evidence" in out
    assert "obscure topic" in out


def test_format_context_weak_marks_verify():
    r = VaultResult(
        query="edge case",
        verdict="weak",
        top1=0.6,
        results=[VaultHit("t", "p", "id", "g", 0.6, "chunk text", 0, 1)],
    )
    out = format_context_block(r)
    assert "WEAK" in out
    assert "verify before citing" in out


def test_format_context_confident_omits_verify():
    r = VaultResult(
        query="q",
        verdict="confident",
        top1=0.8,
        results=[VaultHit("t", "p", "id", "g", 0.8, "chunk", 0, 1)],
    )
    out = format_context_block(r)
    assert "confident evidence" in out
    assert "WEAK" not in out


def test_format_context_respects_max_hits():
    hits = [VaultHit(f"t{i}", f"p{i}", f"id{i}", "g", 0.8, "c", 0, 1) for i in range(5)]
    r = VaultResult(query="q", verdict="confident", top1=0.8, results=hits)
    out = format_context_block(r, max_hits=2)
    assert out.count("\n- ") == 2  # only 2 hits rendered


# ── live integration (opt-in) ───────────────────────────────────────────────

_LIVE_VAULT = Path.home() / "Knowledge" / "7-Visual-Graphs" / ".venv" / "bin" / "python"


@pytest.mark.skipif(not _LIVE_VAULT.exists(), reason="live vault not installed on this host")
def test_live_query_returns_a_verdict():
    """If the real vault is on this host, prove the round-trip works.

    Deliberately does NOT assert on 'confident' — some environments have a cold
    store or a query that legitimately has no evidence. What matters is that
    the client returns a valid verdict and never raises.
    """
    r = query_vault("what is the sapphire content engine", n_results=3, timeout=45.0)
    assert r.verdict in {"confident", "weak", "none", "unavailable"}
    # If we got a real answer, it must be structurally sound.
    if r.verdict in {"confident", "weak"}:
        assert r.results
        assert all(isinstance(h, VaultHit) for h in r.results)
        assert all(h.path for h in r.results)
