"""
vault_client — Semantic-search client for Ari's self-sovereign Obsidian vault.

Sapphire writes to `~/Knowledge` today (see ``services/pipeline/tdr_pro_sync.py``)
but never reads. This module closes that loop: consumers (daily brief, thesis
engine, content pipeline) can ask the vault for supporting evidence with a single
call.

Isolation model
---------------

The vault engine lives in its own Python 3.11 venv at
``~/Knowledge/7-Visual-Graphs/.venv`` with heavy numpy state; Sapphire runs on a
newer Python and cannot import that engine directly. We invoke ``knowledge_lib.py
query-json`` as a subprocess so the two runtimes stay independent — a broken
vault venv can never crash a Sapphire service.

Failure model — every call returns a ``VaultResult``, never raises
------------------------------------------------------------------

Any of: vault missing, venv missing, Ollama down, subprocess timeout, malformed
JSON — all collapse to ``verdict="unavailable"`` with an ``error`` string. Callers
should treat "unavailable" as "no vault context this call" and continue; they must
NOT fall back to fabricated content. This matches the vault's own tri-state
confidence rule: it must be possible for retrieval to say "I don't know."
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_VAULT_ROOT = Path.home() / "Knowledge"
KNOWLEDGE_LIB_REL = Path("7-Visual-Graphs") / "knowledge_lib.py"
VENV_PY_REL = Path("7-Visual-Graphs") / ".venv" / "bin" / "python"

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_N_RESULTS = 5


@dataclass
class VaultHit:
    """One retrieved chunk. Fields mirror the vault engine's shape verbatim."""

    title: str
    path: str
    note_id: str
    group: str
    score: float
    chunk: str
    chunk_index: int
    total_chunks: int

    @classmethod
    def from_dict(cls, d: dict) -> VaultHit:
        return cls(
            title=str(d.get("title", "Untitled")),
            path=str(d.get("path", "")),
            note_id=str(d.get("note_id", "")),
            group=str(d.get("group", "")),
            score=float(d.get("score", 0.0)),
            chunk=str(d.get("chunk", "")),
            chunk_index=int(d.get("chunk_index", 0)),
            total_chunks=int(d.get("total_chunks", 1)),
        )


@dataclass
class VaultResult:
    """Full response from one vault query.

    ``verdict`` mirrors the vault's calibrated confidence bands:
      * ``confident`` — top1 >= 0.62; safe to cite as vault knowledge
      * ``weak``      — top1 in [0.595, 0.62); topically adjacent, verify
      * ``none``      — top1 < 0.595; a knowledge gap, do not cite
      * ``unavailable`` — the vault could not be reached; do not cite anything
    """

    query: str
    verdict: str
    top1: float
    results: list[VaultHit] = field(default_factory=list)
    error: str | None = None
    confident_floor: float = 0.62
    weak_floor: float = 0.595

    @property
    def is_citable(self) -> bool:
        """True only when the top hit crossed the calibrated confident floor."""
        return self.verdict == "confident"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_citable"] = self.is_citable
        return d


def _vault_root() -> Path:
    return Path(os.environ.get("SAPPHIRE_VAULT_ROOT", str(DEFAULT_VAULT_ROOT)))


def _unavailable(query: str, error: str) -> VaultResult:
    log.warning("vault_client unavailable: %s", error)
    return VaultResult(query=query, verdict="unavailable", top1=0.0, error=error)


def _validate_query(query: str) -> str | None:
    if not isinstance(query, str):
        return f"query must be str, got {type(query).__name__}"
    if not query.strip():
        return "empty query"
    if len(query) > 4000:
        # Cheap upper bound so a runaway caller does not hand the embedder 1MB.
        # 4KB is >> any reasonable single-turn question.
        return f"query too long ({len(query)} chars, max 4000)"
    return None


def query_vault(
    query: str,
    n_results: int = DEFAULT_N_RESULTS,
    timeout: float = DEFAULT_TIMEOUT_S,
    vault_root: Path | None = None,
) -> VaultResult:
    """Ask the vault for chunks matching ``query``. Always returns; never raises.

    Args:
        query: the natural-language question. Trimmed and length-capped.
        n_results: how many hits to request. 1..50; values outside clamp.
        timeout: subprocess wall-clock cap in seconds. Includes cold-start
            embedding via Ollama, so allow at least a few seconds.
        vault_root: override the vault directory. Defaults to $SAPPHIRE_VAULT_ROOT
            or ``~/Knowledge``.

    Returns:
        VaultResult — inspect .verdict and .is_citable before using .results.
    """
    err = _validate_query(query)
    if err:
        return _unavailable(query if isinstance(query, str) else "", err)

    n = max(1, min(50, int(n_results)))
    root = Path(vault_root) if vault_root is not None else _vault_root()
    kl = root / KNOWLEDGE_LIB_REL
    py = root / VENV_PY_REL

    if not root.exists():
        return _unavailable(query, f"vault root does not exist: {root}")
    if not py.exists():
        return _unavailable(query, f"vault venv python missing: {py}")
    if not kl.exists():
        return _unavailable(query, f"knowledge_lib.py missing: {kl}")

    cmd = [str(py), str(kl), "query-json", f"--n={n}", query.strip()]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _unavailable(query, f"vault subprocess timed out after {timeout}s")
    except (OSError, ValueError) as e:
        # OSError = fork/exec failed; ValueError = bad cmd shape (defense-in-depth).
        return _unavailable(query, f"vault subprocess launch failed: {e}")

    # Exit codes from knowledge_lib.run_query_json:
    #   0 — normal response (any verdict)
    #   2 — empty query (we already validated, so this shouldn't fire)
    #   3 — empty vector store (fresh install / wipe)
    # Any other non-zero = engine crash — surface stderr in the error field.
    if proc.returncode not in (0, 2, 3):
        stderr_tail = (proc.stderr or "").strip().splitlines()[-3:]
        return _unavailable(
            query,
            f"vault engine exited {proc.returncode}: {' | '.join(stderr_tail)[:400]}",
        )

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return _unavailable(query, "vault engine returned no output")

    try:
        payload = json.loads(stdout.splitlines()[-1])  # last line is the JSON blob
    except json.JSONDecodeError as e:
        return _unavailable(query, f"vault engine returned non-JSON: {e}")

    if not isinstance(payload, dict):
        return _unavailable(query, f"vault engine returned non-object: {type(payload).__name__}")

    if payload.get("error") and not payload.get("results"):
        return _unavailable(query, f"vault engine: {payload['error']}")

    try:
        hits = [VaultHit.from_dict(r) for r in payload.get("results", []) if isinstance(r, dict)]
    except (TypeError, ValueError) as e:
        return _unavailable(query, f"vault engine returned malformed hit: {e}")

    verdict = str(payload.get("verdict", "none"))
    if verdict not in {"confident", "weak", "none"}:
        return _unavailable(query, f"vault engine returned unknown verdict: {verdict!r}")

    return VaultResult(
        query=query,
        verdict=verdict,
        top1=float(payload.get("top1", 0.0)),
        results=hits,
        error=None,
        confident_floor=float(payload.get("confident_floor", 0.62)),
        weak_floor=float(payload.get("weak_floor", 0.595)),
    )


def format_context_block(result: VaultResult, max_hits: int = 3, max_chunk_chars: int = 400) -> str:
    """Render a compact, honest context block for LLM consumption.

    Skips fabrication risk by rendering the verdict explicitly. A ``none`` or
    ``unavailable`` result becomes a one-line "no vault evidence" statement, NOT
    a stripped-down list of weak hits pretending to be evidence.
    """
    if result.verdict == "unavailable":
        return f"[vault unavailable: {result.error or 'unknown error'}]"
    if result.verdict == "none":
        return f"[vault has no confident evidence for: {result.query}]"

    header = (
        "[vault: confident evidence]"
        if result.verdict == "confident"
        else f"[vault: WEAK evidence (top {result.top1:.3f} < {result.confident_floor:.2f}) — verify before citing]"
    )
    lines = [header]
    for h in result.results[:max_hits]:
        snippet = h.chunk.strip().replace("\n", " ")[:max_chunk_chars]
        lines.append(f"- {h.title} ({h.path}) [{h.score:.3f}]: {snippet}")
    return "\n".join(lines)
